"""
Selected Image Details Widget - 選択画像詳細表示ウィジェット

DatasetStateManagerからの画像データを受信し、選択された画像の詳細情報を表示するウィジェット。
DatasetStateManager.current_image_data_changedを正規経路としてUI更新を実装。

主要機能:
- 画像メタデータの詳細表示（ファイル名、サイズ、作成日時等）
- Rating/Score の読み取り専用表示
- アノテーションデータ（タグ・キャプション）の読み取り専用表示

アーキテクチャ:
- DatasetStateManagerを選択画像メタデータの正規ソースとして使用
- DatasetStateManager.current_image_data_changedシグナル受信
- ImageDetails構造体による型安全なデータ管理
- AnnotationDataDisplayWidget統合による表示機能
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPoint, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...gui.designer.SelectedImageDetailsWidget_ui import Ui_SelectedImageDetailsWidget
from ...services.date_formatter import format_datetime_for_display
from ...utils.log import logger
from .annotation_data_display_widget import (
    AnnotationData,
    AnnotationDataDisplayWidget,
    ImageDetails,
)
from .rating_score_edit_widget import RatingScoreEditWidget

if TYPE_CHECKING:
    from genai_tag_db_tools.db.repository import MergedTagReader

    from ..state.dataset_state import DatasetStateManager


class SelectedImageDetailsWidget(QWidget):
    """
    選択画像詳細情報表示ウィジェット

    DatasetStateManagerから送信される画像メタデータを受信し、選択画像の詳細情報を表示。
    DatasetStateManager.current_image_data_changedを正規経路として非同期データ更新を実装。

    データフロー:
    1. DatasetStateManager.current_image_data_changed -> _on_image_data_received()
    2. メタデータ解析 -> _build_image_details_from_metadata()
    3. UI更新 -> _update_details_display()

    View-only mode:
    - 編集機能なし（read-only ラベルのみ）
    - データ表示のみ

    UI構成:
    - groupBoxImageInfo: ファイル名、サイズ、作成日時表示
    - groupBoxRatingScore: Rating/Score 表示（read-only ラベル）
    - annotationDataDisplay: タグ・キャプション表示（AnnotationDataDisplayWidget）

    型安全性:
    - ImageDetails dataclassによる構造化データ管理
    - 全メタデータフィールドの型チェック・デフォルト値処理
    - None安全なデータアクセスパターン実装
    """

    # シグナル
    image_details_loaded = Signal(ImageDetails)  # 画像詳細読み込み完了
    rating_changed = Signal(int, str)  # (image_id, rating) - 単一選択時
    score_changed = Signal(int, int)  # (image_id, score) - 単一選択時
    batch_rating_changed = Signal(list, str)  # (image_ids, rating) - 複数選択時
    batch_score_changed = Signal(list, int)  # (image_ids, score) - 複数選択時

    def __init__(
        self,
        parent: QWidget | None = None,
    ):
        """
        SelectedImageDetailsWidget初期化

        UIコンポーネントの初期化、内部状態の設定、シグナル接続を実行。
        Qt Designer UIファイルからの自動生成UIと手動制御UIコンポーネントを統合。

        Args:
            parent: 親ウィジェット

        初期状態:
            - current_details: None（未選択状態）
            - current_image_id: None
            - UI: 空表示状態
        """
        super().__init__(parent)
        logger.debug("SelectedImageDetailsWidget.__init__() called")

        # DatasetStateManagerへの参照（後でconnect_to_dataset_state_managerで設定）
        self._dataset_state_manager: DatasetStateManager | None = None

        # タグ翻訳用（後でset_merged_readerで設定）
        self._merged_reader: MergedTagReader | None = None
        self._available_languages: list[str] = []

        # 内部状態
        self.current_details: ImageDetails | None = None
        self.current_image_id: int | None = None
        self._summary_layout: QVBoxLayout | None = None
        self._image_info_toggle: QToolButton | None = None
        self._copy_details_button: QToolButton | None = None

        # UI設定
        self.ui = Ui_SelectedImageDetailsWidget()
        self.ui.setupUi(self)
        self.annotation_display: AnnotationDataDisplayWidget = self.ui.annotationDataDisplay
        self.annotation_display.set_group_box_visibility(scores=False)

        # RatingScoreEditWidget統合（モックアップの実装パターン）
        self._rating_score_widget = RatingScoreEditWidget()
        self._integrate_rating_score_widget()

        self._setup_connections()
        self._remove_duplicate_detail_tabs()
        self._setup_original_meta_rows()
        self._apply_readable_layout()
        self._clear_display()

        logger.debug("SelectedImageDetailsWidget initialized")

    def _setup_original_meta_rows(self) -> None:
        """画像情報グリッドにオリジナルメタ行 (拡張子/アスペクト比/アルファ) を追加する。

        登録時にリサイズ・拡張子変換されるため、オリジナル画像のメタデータを表示する
        (Issue #813)。.ui は再生成せず、既存 gridLayoutImageInfo に行を増設する。
        """
        grid = self.ui.gridLayoutImageInfo
        group = self.ui.groupBoxImageInfo
        next_row = grid.rowCount()
        self.labelExtensionValue = QLabel("-", group)
        self.labelAspectValue = QLabel("-", group)
        self.labelAlphaValue = QLabel("-", group)
        rows = (
            ("拡張子", self.labelExtensionValue),
            ("アスペクト比", self.labelAspectValue),
            ("アルファ", self.labelAlphaValue),
        )
        for offset, (caption, value_label) in enumerate(rows):
            key_label = QLabel(caption, group)
            grid.addWidget(key_label, next_row + offset, 0, 1, 1)
            grid.addWidget(value_label, next_row + offset, 1, 1, 1)

    def _remove_duplicate_detail_tabs(self) -> None:
        """重複表示になるタブを削除する。"""
        tab_widget = self.ui.tabWidgetDetails
        for tab in (self.ui.tabTags, self.ui.tabCaptions):
            index = tab_widget.indexOf(tab)
            if index != -1:
                tab_widget.removeTab(index)

    def _integrate_rating_score_widget(self) -> None:
        """RatingScoreEditWidgetをAnnotationDataDisplayの直後に配置（モックアップパターン）

        Note: 実際のレイアウト配置は _apply_readable_layout() で行われます
        """
        logger.debug("RatingScoreEditWidget will be integrated in _apply_readable_layout()")

    def _apply_readable_layout(self) -> None:
        """読みやすさ優先のレイアウトに調整する。"""
        self._align_summary_labels()
        self._setup_copyable_summary_labels()

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(4)

        self._image_info_toggle = QToolButton(container)
        self._image_info_toggle.setText("画像情報")
        self._image_info_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._image_info_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._image_info_toggle.setCheckable(True)
        self._image_info_toggle.setChecked(False)
        self._image_info_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._image_info_toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._image_info_toggle.setStyleSheet("text-align: left;")
        self._image_info_toggle.toggled.connect(self._toggle_image_info_section)

        self._copy_details_button = QToolButton(container)
        self._copy_details_button.setText("詳細をコピー")
        self._copy_details_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._copy_details_button.setEnabled(False)
        self._copy_details_button.clicked.connect(self.copy_current_details_to_clipboard)

        self.ui.groupBoxImageInfo.setTitle("")
        self.ui.groupBoxImageInfo.setVisible(False)

        layout.addWidget(self._image_info_toggle)
        layout.addWidget(self._copy_details_button)
        layout.addWidget(self.ui.groupBoxImageInfo)
        # annotationDataDisplay は内容相応の高さに収め、余剰を末尾 spacer に渡す (#827)。
        # 既定の Expanding だと stretch=0 でも余剰を一部吸い込み、レーティング詳細と
        # 評価スコア編集の間に隙間が残るため、縦は Preferred に固定する。
        self.ui.annotationDataDisplay.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.ui.annotationDataDisplay)
        layout.addWidget(self._rating_score_widget)
        # 全 widget をトップ詰めにし、余剰高さは最下部 (評価スコア編集の下) へ逃がす (#827)。
        # annotationDataDisplay に stretch を与えると、その余白がレーティング詳細と
        # 評価スコア編集の間に出てしまうため、stretch は末尾 spacer に集約する。
        layout.addStretch(1)
        layout.setStretch(0, 0)  # _image_info_toggle
        layout.setStretch(1, 0)  # _copy_details_button
        layout.setStretch(2, 0)  # groupBoxImageInfo
        layout.setStretch(3, 0)  # annotationDataDisplay
        layout.setStretch(4, 0)  # _rating_score_widget
        layout.setStretch(5, 1)  # 末尾 spacer (余剰を吸収)

        scroll_area = QScrollArea(self)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(container)

        self.ui.verticalLayoutMain.removeWidget(self.ui.tabWidgetDetails)
        self.ui.tabWidgetDetails.setVisible(False)
        self.ui.verticalLayoutMain.addWidget(scroll_area)
        self._summary_layout = layout

    def _align_summary_labels(self) -> None:
        """概要表示のラベル位置を揃えて視認性を上げる。"""
        align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for label in (
            self.ui.labelFileName,
            self.ui.labelImageSize,
            self.ui.labelFileSize,
            self.ui.labelCreatedDate,
        ):
            label.setAlignment(align)

        label_width = max(
            label.fontMetrics().horizontalAdvance(label.text())
            for label in (
                self.ui.labelFileName,
                self.ui.labelImageSize,
                self.ui.labelFileSize,
                self.ui.labelCreatedDate,
            )
        )
        label_width += 8

        for label in (
            self.ui.labelFileName,
            self.ui.labelImageSize,
            self.ui.labelFileSize,
            self.ui.labelCreatedDate,
        ):
            label.setMinimumWidth(label_width)

        self.ui.gridLayoutImageInfo.setColumnStretch(0, 0)
        self.ui.gridLayoutImageInfo.setColumnStretch(1, 1)
        self.ui.gridLayoutImageInfo.setHorizontalSpacing(12)
        self.ui.gridLayoutImageInfo.setVerticalSpacing(6)

        if hasattr(self.annotation_display, "verticalLayoutMain"):
            self.annotation_display.verticalLayoutMain.setContentsMargins(0, 0, 0, 0)
            self.annotation_display.verticalLayoutMain.setSpacing(4)

    def _setup_copyable_summary_labels(self) -> None:
        for label in (
            self.ui.labelFileNameValue,
            self.ui.labelImageSizeValue,
            self.ui.labelFileSizeValue,
            self.ui.labelCreatedDateValue,
            self.ui.labelTagsContent,
        ):
            self._make_label_copyable(label)

        self.ui.textEditCaptionsContent.setReadOnly(True)

    def _make_label_copyable(self, label: QLabel) -> None:
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        label.customContextMenuRequested.connect(
            lambda position, target=label: self._show_label_context_menu(target, position)
        )

    def _show_label_context_menu(self, label: QLabel, position: QPoint) -> None:
        menu = QMenu(label)
        copy_action = menu.addAction("コピー")
        copy_action.setEnabled(bool(self._label_clipboard_text(label)))
        copy_action.triggered.connect(
            lambda: QApplication.clipboard().setText(self._label_clipboard_text(label))
        )
        menu.exec(label.mapToGlobal(position))

    @staticmethod
    def _label_clipboard_text(label: QLabel) -> str:
        """QLabel の選択テキストを優先し、未選択時は全テキストを返す。"""
        selected_text = label.selectedText()
        return selected_text if selected_text else label.text()

    def _toggle_image_info_section(self, expanded: bool) -> None:
        if self._image_info_toggle:
            arrow = Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
            self._image_info_toggle.setArrowType(arrow)
        self.ui.groupBoxImageInfo.setVisible(expanded)

    def _setup_connections(self) -> None:
        """
        UIコンポーネントのシグナル接続設定

        Qt Designerで設定されていないシグナルを追加接続。
        Rating/Score関連のハンドラは .ui 側の接続定義を使用。
        """
        # AnnotationDataDisplayWidgetからのシグナル接続
        self.annotation_display.data_loaded.connect(self._on_annotation_data_loaded)

        # RatingScoreEditWidgetのシグナルを外部に転送
        self._rating_score_widget.rating_changed.connect(self.rating_changed.emit)
        self._rating_score_widget.score_changed.connect(self.score_changed.emit)
        self._rating_score_widget.batch_rating_changed.connect(self.batch_rating_changed.emit)
        self._rating_score_widget.batch_score_changed.connect(self.batch_score_changed.emit)

        logger.debug("SelectedImageDetailsWidget signals connected")

    @Slot()
    def _on_annotation_data_loaded(self) -> None:
        """
        AnnotationDataDisplayWidgetからのデータ読み込み完了通知ハンドラ

        AnnotationDataDisplayWidgetの内部処理完了を受けて追加処理を実行可能。
        現在は特別な処理なし。
        """
        logger.debug("Annotation data loaded in AnnotationDataDisplayWidget")

    def set_merged_reader(self, reader: "MergedTagReader | None") -> None:
        """MergedTagReaderを設定し、言語セレクターを初期化する。

        Args:
            reader: タグ翻訳取得用のMergedTagReader。Noneの場合は翻訳機能無効。
        """
        self._merged_reader = reader
        self._available_languages = reader.get_tag_languages() if reader is not None else []
        self.annotation_display.initialize_language_selector(self._available_languages)
        logger.debug(f"MergedTagReader設定完了: 利用可能言語={self._available_languages}")

    def set_db_manager(self, db_manager: Any) -> None:
        """soft-reject 導線用に ImageDatabaseManager を設定し編集モードを有効化する (Issue #792)。

        Args:
            db_manager: タグ soft-reject / 復活 / 手動追加を実行する Manager。
        """
        self._db_manager = db_manager
        self.annotation_display.set_tag_edit_enabled(True)
        self.annotation_display.tag_reject_requested.connect(self._on_tag_reject)
        self.annotation_display.tag_restore_requested.connect(self._on_tag_restore)
        self.annotation_display.tag_add_requested.connect(self._on_tag_add)
        logger.debug("SelectedImageDetailsWidget: soft-reject 編集モードを有効化")

    def _populate_rejected_tags(self) -> None:
        """現在画像の soft-rejected タグを取得して復活セクションへ反映する (Issue #792)。"""
        db_manager = getattr(self, "_db_manager", None)
        if db_manager is None or self.current_image_id is None:
            return
        rejected = [row["tag"] for row in db_manager.get_rejected_tags(self.current_image_id)]
        self.annotation_display.set_rejected_tags(rejected)

    def _reload_current_image(self) -> None:
        """編集後に現在画像のメタデータを再取得して表示を更新する (Issue #792)。"""
        db_manager = getattr(self, "_db_manager", None)
        if db_manager is None or self.current_image_id is None:
            return
        metadata = db_manager.image_repo.get_image_metadata(self.current_image_id)
        if metadata:
            self._on_image_data_received(metadata)

    @Slot(str)
    def _on_tag_reject(self, tag: str) -> None:
        """タグ soft-reject 要求を Manager に委譲し再描画する。"""
        if self.current_image_id is None:
            return
        self._db_manager.soft_reject_tag(self.current_image_id, tag)
        self._reload_current_image()

    @Slot(str)
    def _on_tag_restore(self, tag: str) -> None:
        """タグ復活要求を Manager に委譲し再描画する。"""
        if self.current_image_id is None:
            return
        self._db_manager.restore_tag(self.current_image_id, tag)
        self._reload_current_image()

    @Slot(str)
    def _on_tag_add(self, tag: str) -> None:
        """手動タグ追加要求を Manager に委譲し再描画する。"""
        if self.current_image_id is None:
            return
        self._db_manager.add_manual_tag(self.current_image_id, tag)
        self._reload_current_image()

    def connect_to_dataset_state_manager(self, state_manager: "DatasetStateManager") -> None:
        """DatasetStateManagerの選択画像メタデータシグナルに接続する。

        接続経路の詳細をログに記録し、問題診断を可能にする。
        connect()の戻り値を検証し、接続失敗を検出する。

        Args:
            state_manager: DatasetStateManagerインスタンス
        """
        logger.info(
            f"🔌 connect_to_dataset_state_manager() 呼び出し開始 - "
            f"widget instance: {id(self)}, state_manager: {id(state_manager)}"
        )

        if not state_manager:
            logger.error("❌ DatasetStateManager is None - 接続中止")
            return

        self._dataset_state_manager = state_manager

        # シグナル接続（戻り値を確認）
        connection = state_manager.current_image_data_changed.connect(self._on_image_data_received)
        connection_valid = bool(connection)

        logger.info(f"📊 connect()戻り値: valid={connection_valid}, type={type(connection)}")

        if not connection_valid:
            logger.error("❌ Qt接続失敗 - connect()が無効なConnectionを返しました")
            return

        logger.info(
            f"✅ current_image_data_changed シグナル接続完了 - from {id(state_manager)} to {id(self)}"
        )

    @Slot(dict)
    def _on_image_data_received(self, image_data: dict[str, Any]) -> None:
        """
        DatasetStateManagerからの画像データ受信ハンドラ。

        Args:
            image_data: 画像メタデータ辞書

        処理:
        1. 空データチェック（選択解除時）
        2. ImageDetails構造体への変換
        3. UI更新処理の実行

        Notes:
            - DatasetStateManager.current_image_data_changedが正規経路
            - ImageDetails dataclass による型安全な処理
        """
        if not image_data:
            logger.info("SelectedImageDetailsWidget: 空データ受信 - 表示をクリア")
            self._clear_display()
            return

        image_id = image_data.get("id")
        self.current_image_id = image_id
        logger.info(
            f"📨 SelectedImageDetailsWidget(instance={id(self)}): current_image_data_changed シグナル受信 - image_id: {image_id}"
        )

        details = self._build_image_details_from_metadata(image_data)
        self._update_details_display(details)
        self._populate_rejected_tags()

    def _build_image_details_from_metadata(self, metadata: dict[str, Any]) -> ImageDetails:
        """
        メタデータ辞書からImageDetails構造体を構築

        Args:
            metadata: データベースから取得した画像メタデータ辞書
                     metadata["annotations"]["tags"] = list[dict] 形式

        Returns:
            ImageDetails: 型安全な画像詳細情報構造体

        処理:
        1. 必須フィールドの抽出と型変換
        2. オプショナルフィールドのNone安全な処理
        3. Repository層で変換済みのアノテーション情報を使用
        4. AnnotationData構造体の構築
        5. ImageDetails構造体の組み立て

        型安全性:
        - 全フィールドの型チェック
        - デフォルト値の適用
        - None値の適切な処理
        """
        # 基本情報
        image_id = metadata.get("id")
        file_path_str = self._get_display_file_path(metadata)
        file_name = Path(file_path_str).name if file_path_str else ""

        # オリジナル画像の解像度 (Image テーブル = original。登録時にリサイズ/変換されるため
        # ここでは必ずオリジナル値を表示する。Issue #813)
        width = metadata.get("width", 0)
        height = metadata.get("height", 0)
        image_size = f"{width} × {height} px" if width and height else ""
        aspect_ratio = self._format_aspect_ratio(width, height)
        original_extension = self._format_original_extension(metadata)
        alpha_text = self._format_alpha(metadata)

        file_size = self._get_file_size_bytes(metadata, image_id)
        if file_size is not None and file_size > 0:
            size_kb = file_size / 1024
            file_size_str = f"{size_kb / 1024:.2f} MB" if size_kb >= 1024 else f"{size_kb:.2f} KB"
        else:
            file_size_str = ""

        created_at = metadata.get("created_at")
        created_date = format_datetime_for_display(created_at) if created_at else ""

        # Rating / Score（Issue #4: Repository側で整形済みの値を使用）
        rating_value = metadata.get("rating_value", "")
        score_value = metadata.get("score_value", 0)
        # Issue #825: AI/手動を分離した値 (スコアカードの AI セクションは純粋 AI 値、
        # 人間セクションは手動値のみを表示する)。
        ai_rating_value = metadata.get("ai_rating_value", "")
        manual_rating_value = metadata.get("manual_rating_value", "")
        ai_score_value = metadata.get("ai_score_value")
        manual_score_value = metadata.get("manual_score_value")

        # アノテーション情報（Repository層で変換済み・直接キーアクセス）
        # Repository層は metadata に直接 tags, captions などのキーを追加
        # ADR 0068 (改訂): Tag.tag は保存時に danbooru canonical へ焼き込み済みのため
        # 表示は verbatim で行う (表示時の変換コストを排除)。
        tags_list = metadata.get("tags", [])
        caption_text = metadata.get("caption_text", "")
        tags_text = metadata.get("tags_text", "")

        # ADR 0028: canonical scorer の score_labels を AnnotationData に渡す
        score_labels_list = metadata.get("score_labels", [])
        # Issue #334: model 別 rating record を詳細表示へ渡す
        ratings_list = metadata.get("ratings", [])
        # ADR 0029: 統一品質 tier (derived view) を AnnotationData に渡す
        quality_summary = metadata.get("quality_summary", {})

        # 翻訳データ取得（N+1回避のためバッチ取得）
        tag_translations: dict[int, dict[str, str]] = {}
        if self._merged_reader is not None:
            valid_tag_ids = [
                tag_dict["tag_id"] for tag_dict in tags_list if tag_dict.get("tag_id") is not None
            ]
            if valid_tag_ids:
                for tag_id, trs in self._merged_reader.get_translations_batch(valid_tag_ids).items():
                    for tr in trs:
                        if tr.language and tr.translation:
                            tag_translations.setdefault(tag_id, {})[tr.language] = tr.translation

        annotation_data = AnnotationData(
            tags=tags_list,  # ← list[dict] をそのまま渡す
            caption=caption_text,
            aesthetic_score=score_value,
            overall_score=0,  # Rating値は文字列なのでoverall_scoreには使用しない
            score_labels=score_labels_list,
            ratings=ratings_list,
            quality_summary=quality_summary,
            tag_translations=tag_translations,
            available_languages=self._available_languages,
        )

        details = ImageDetails(
            image_id=image_id,
            file_name=file_name,
            file_path=file_path_str,
            image_size=image_size,
            file_size=file_size_str,
            created_date=created_date,
            rating_value=rating_value,
            score_value=score_value,
            ai_rating_value=ai_rating_value,
            manual_rating_value=manual_rating_value,
            ai_score_value=ai_score_value,
            manual_score_value=manual_score_value,
            caption=caption_text,
            tags=tags_text,
            original_extension=original_extension,
            aspect_ratio=aspect_ratio,
            alpha_text=alpha_text,
            annotation_data=annotation_data,
        )

        logger.debug(
            f"Built ImageDetails: id={details.image_id}, tags={len(annotation_data.tags)}, "
            f"caption_len={len(caption_text)}"
        )

        return details

    @staticmethod
    def _format_aspect_ratio(width: Any, height: Any) -> str:
        """オリジナル解像度から既約アスペクト比 (例 "16:9") を返す (Issue #813)。"""
        try:
            w = int(width)
            h = int(height)
        except (TypeError, ValueError):
            return ""
        if w <= 0 or h <= 0:
            return ""
        from math import gcd

        g = gcd(w, h)
        return f"{w // g}:{h // g}"

    @staticmethod
    def _format_original_extension(metadata: dict[str, Any]) -> str:
        """オリジナル画像の拡張子表示 (Image.extension / format 由来、Issue #813)。"""
        ext = metadata.get("extension")
        if isinstance(ext, str) and ext.strip():
            normalized = ext.strip()
            return normalized if normalized.startswith(".") else f".{normalized}"
        fmt = metadata.get("format")
        if isinstance(fmt, str) and fmt.strip():
            return fmt.strip().upper()
        return ""

    @staticmethod
    def _format_alpha(metadata: dict[str, Any]) -> str:
        """アルファチャンネル有無の表示 (Image.has_alpha / mode 由来、Issue #813)。"""
        has_alpha = metadata.get("has_alpha")
        mode = metadata.get("mode")
        mode_text = f" ({mode})" if isinstance(mode, str) and mode.strip() else ""
        if has_alpha is True:
            return f"あり{mode_text or ' (RGBA)'}"
        if has_alpha is False:
            return f"なし{mode_text or ' (RGB)'}"
        return "不明"

    @staticmethod
    def _get_display_file_path(metadata: dict[str, Any]) -> str:
        """表示用ファイルパスを metadata から取得する。

        DatasetStateManager の正規キーは stored_image_path。file_path は旧経路との
        互換 fallback として扱う。
        """
        stored_path = metadata.get("stored_image_path")
        if stored_path:
            return str(stored_path).replace("\\", "/")

        file_path = metadata.get("file_path")
        if file_path:
            logger.debug(
                "metadata に stored_image_path が無いため file_path を使用: "
                f"image_id={metadata.get('id')}, file_path={file_path}"
            )
            return str(file_path).replace("\\", "/")

        logger.debug(
            "metadata に表示可能な画像パスがありません: "
            f"image_id={metadata.get('id')}, keys={list(metadata.keys())}"
        )
        return ""

    @staticmethod
    def _get_file_size_bytes(metadata: dict[str, Any], image_id: Any) -> int | None:
        """metadata または stored_image_path の実ファイルからファイルサイズを取得する。"""
        raw_file_size = metadata.get("file_size")
        if isinstance(raw_file_size, int | float) and raw_file_size > 0:
            return int(raw_file_size)

        stored_path = metadata.get("stored_image_path")
        if not stored_path:
            logger.debug(
                "file_size 補完不可: stored_image_path がありません: "
                f"image_id={image_id}, keys={list(metadata.keys())}"
            )
            return None

        try:
            from ...database.db_core import resolve_stored_path

            resolved_path = resolve_stored_path(str(stored_path))
            if resolved_path.exists():
                return resolved_path.stat().st_size
            logger.debug(
                f"file_size 補完不可: ファイルが存在しません: image_id={image_id}, path={resolved_path}"
            )
        except OSError as e:
            logger.debug(
                f"file_size 補完不可: stat 失敗: image_id={image_id}, path={stored_path}, error={e}"
            )

        return None

    def _update_details_display(self, details: ImageDetails) -> None:
        """
        ImageDetails構造体に基づいてUI表示を更新

        Args:
            details: 表示する画像詳細情報

        UI更新対象:
        - labelFileNameValue: ファイル名
        - labelImageSizeValue: 解像度（幅x高さ）
        - labelFileSizeValue: ファイルサイズ（KB/MB）
        - labelCreatedDateValue: 登録日時
        - comboBoxRating: Rating選択
        - sliderScore: Score調整
        - annotationDataDisplay: タグ・キャプション
        """
        self.current_details = details
        self.current_image_id = details.image_id

        # ファイル名
        file_name = details.file_name if details.file_name else "-"
        self.ui.labelFileNameValue.setText(file_name)

        # 解像度
        resolution_text = details.image_size if details.image_size else "-"
        self.ui.labelImageSizeValue.setText(resolution_text)

        # ファイルサイズ (already formatted as string)
        size_text = details.file_size if details.file_size else "-"
        self.ui.labelFileSizeValue.setText(size_text)

        # 作成日時
        created_date_text = details.created_date if details.created_date else "-"
        self.ui.labelCreatedDateValue.setText(created_date_text)

        # オリジナル画像メタ (Issue #813)
        self.labelExtensionValue.setText(details.original_extension or "-")
        self.labelAspectValue.setText(details.aspect_ratio or "-")
        self.labelAlphaValue.setText(details.alpha_text or "-")

        # Rating / Score
        self._update_rating_score_display(details)

        # タグ/キャプション（プレーン表示用）
        tags_text = details.tags if details.tags else "-"
        if self.ui.tabWidgetDetails.indexOf(self.ui.tabTags) != -1:
            self.ui.labelTagsContent.setText(tags_text)

        caption_text = details.caption if details.caption else ""
        if self.ui.tabWidgetDetails.indexOf(self.ui.tabCaptions) != -1:
            self.ui.textEditCaptionsContent.setPlainText(caption_text)

        # アノテーションデータ（リッチ表示用）
        if details.annotation_data:
            self.annotation_display.update_data(details.annotation_data)

        logger.info(f"✅ SelectedImageDetailsWidget表示更新完了: image_id={details.image_id}")
        if self._copy_details_button:
            self._copy_details_button.setEnabled(True)
        self.image_details_loaded.emit(details)

    def _update_rating_score_display(self, details: ImageDetails) -> None:
        """
        Rating/Scoreの表示更新（RatingScoreEditWidget使用）

        Args:
            details: 画像詳細情報

        処理:
        1. RatingScoreEditWidgetのデータ更新

        Notes:
            - モックアップパターン: RatingScoreEditWidgetで編集可能
            - score_value: DB値（0.0-10.0）をそのまま渡す
        """
        # RatingScoreEditWidgetにデータを設定 (Issue #825)。
        # AI セクション (read-only) は純粋な AI 値 (ai_rating_value / ai_score_value) を、
        # 人間セクション (手動編集) は手動値 (manual_rating_value / manual_score_value) を表示する。
        # 手動値が無ければ未設定 (rating は "----"、score は "--") で表示し、AI 値とは独立させる。
        self._rating_score_widget.populate_from_image_data(
            {
                "id": details.image_id,
                "rating": details.manual_rating_value or "----",
                "score_value": details.manual_score_value,
                "ai_rating": details.ai_rating_value or "----",
                "ai_score_value": details.ai_score_value,
            }
        )

        logger.debug(
            f"Rating/Score updated: manual_rating={details.manual_rating_value!r}, "
            f"manual_score={details.manual_score_value}, ai_rating={details.ai_rating_value!r}, "
            f"ai_score={details.ai_score_value}"
        )

    def _clear_display(self) -> None:
        """
        表示内容をクリア（未選択状態）

        処理:
        1. 内部状態のリセット
        2. 全UI要素を初期状態に戻す

        UI初期化対象:
        - labelFileNameValue: "-"
        - labelImageSizeValue: "-"
        - labelFileSizeValue: "-"
        - labelCreatedDateValue: "-"
        - RatingScoreEditWidget: クリア
        - annotationDataDisplay: クリア
        """
        self.current_details = None
        self.current_image_id = None

        self.ui.labelFileNameValue.setText("-")
        self.ui.labelImageSizeValue.setText("-")
        self.ui.labelFileSizeValue.setText("-")
        self.labelExtensionValue.setText("-")
        self.labelAspectValue.setText("-")
        self.labelAlphaValue.setText("-")
        self.ui.labelCreatedDateValue.setText("-")
        if self.ui.tabWidgetDetails.indexOf(self.ui.tabTags) != -1:
            self.ui.labelTagsContent.setText("-")
        if self.ui.tabWidgetDetails.indexOf(self.ui.tabCaptions) != -1:
            self.ui.textEditCaptionsContent.clear()

        # RatingScoreEditWidgetをリセット
        self._rating_score_widget.populate_from_image_data(
            {
                "id": None,
                "rating": "----",
                "score": 0,
            }
        )

        # AnnotationDataDisplayWidgetのクリア
        self.annotation_display.clear_data()
        if self._copy_details_button:
            self._copy_details_button.setEnabled(False)

        logger.debug("SelectedImageDetailsWidget display cleared")

    def get_current_details(self) -> ImageDetails | None:
        """現在表示中の画像詳細情報を返す"""
        return self.current_details

    @Slot()
    def copy_current_details_to_clipboard(self) -> bool:
        """現在表示中の画像詳細全体をクリップボードへコピーする。"""
        if self.current_details is None:
            logger.debug("詳細コピー要求: current_details がありません")
            return False

        rating_value, score_value = self._get_live_rating_score_for_clipboard()
        QApplication.clipboard().setText(
            self._format_current_details_for_clipboard(
                self.current_details,
                rating_value=rating_value,
                score_value=score_value,
                tags_value=self.annotation_display.displayed_tags_text(),
            )
        )
        logger.debug(f"画像詳細をクリップボードへコピー: image_id={self.current_details.image_id}")
        return True

    def _get_live_rating_score_for_clipboard(self) -> tuple[str, str]:
        """現在表示中のRating/Score編集ウィジェット値をコピー用に取得する。"""
        rating = self._rating_score_widget.ui.comboBoxRating.currentText()
        if rating == RatingScoreEditWidget._NO_RATING_TEXT:
            rating = ""
        return rating, self._rating_score_widget.ui.labelScoreValue.text()

    @staticmethod
    def _format_current_details_for_clipboard(
        details: ImageDetails,
        *,
        rating_value: str | None = None,
        score_value: str | int | float | None = None,
        tags_value: str | None = None,
    ) -> str:
        display_rating = details.rating_value if rating_value is None else rating_value
        display_score = details.score_value if score_value is None else score_value
        display_tags = details.tags if tags_value is None else tags_value
        lines = [
            f"Image ID: {details.image_id if details.image_id is not None else '-'}",
            f"File name: {details.file_name or '-'}",
            f"File path: {details.file_path or '-'}",
            f"Resolution: {details.image_size or '-'}",
            f"File size: {details.file_size or '-'}",
            f"Created date: {details.created_date or '-'}",
            f"Rating: {display_rating or '-'}",
            f"Score: {display_score if display_score is not None else '-'}",
        ]

        if details.annotation_data is not None:
            quality_tier = details.annotation_data.quality_summary.get("tier")
            if quality_tier:
                lines.append(f"Quality tier: {quality_tier}")

            if details.annotation_data.score_labels:
                score_labels = [
                    f"{entry.get('model', 'Unknown')}: {entry.get('label', '-')}"
                    for entry in details.annotation_data.score_labels
                ]
                lines.append(f"Score labels: {', '.join(score_labels)}")

            if details.annotation_data.ratings:
                ratings = []
                for entry in details.annotation_data.ratings:
                    model = entry.get("model") or entry.get("model_name") or "Unknown"
                    normalized = entry.get("normalized_rating", "-")
                    raw = entry.get("raw_rating_value", "-")
                    confidence = entry.get("confidence_score")
                    confidence_text = f"{confidence:.2f}" if confidence is not None else "-"
                    source = entry.get("source", "AI")
                    ratings.append(
                        f"{model}: {normalized} (raw={raw}, confidence={confidence_text}, source={source})"
                    )
                lines.append(f"Ratings: {', '.join(ratings)}")

        lines.extend(
            [
                f"Tags: {display_tags or '-'}",
                f"Caption: {details.caption or '-'}",
            ]
        )
        return "\n".join(lines)


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    # アプリケーションのエントリポイント
    def main() -> None:
        """アプリケーションのメイン実行関数"""
        app = QApplication(sys.argv)

        # ウィジェットのインスタンスを作成
        widget = SelectedImageDetailsWidget()

        # --- テスト用のダミーデータ ---
        dummy_annotation = AnnotationData(
            tags=[
                {
                    "tag": "1girl",
                    "model_name": "wd-v1-4",
                    "source": "AI",
                    "confidence_score": 0.95,
                    "is_edited_manually": False,
                },
                {
                    "tag": "solo",
                    "model_name": "wd-v1-4",
                    "source": "AI",
                    "confidence_score": 0.90,
                    "is_edited_manually": False,
                },
            ],
            caption="A beautiful illustration of a girl.",
            aesthetic_score=6.5,
            overall_score=850,
            score_type="Aesthetic",
        )

        dummy_details = ImageDetails(
            image_id=1,
            file_name="example_image_01.png",
            image_size="512x768",
            file_size="850 KB",
            created_date="2024-05-20 14:30:00",
            rating_value="PG",
            score_value=850,
            annotation_data=dummy_annotation,
        )
        # --- ここまでダミーデータ ---

        # データをウィジェットにロード
        # 本来は image_db_write_service 経由でロードされるが、
        # 単体テストのため、内部メソッドを直接呼び出してUIを更新する
        widget.current_image_id = dummy_details.image_id
        widget.current_details = dummy_details
        widget._update_details_display(dummy_details)

        # ウィジェットを表示
        widget.setWindowTitle("Selected Image Details - Test")
        widget.show()

        sys.exit(app.exec())

    main()
