"""
Selected Image Details Widget - 選択画像詳細表示ウィジェット

DatasetStateManagerからの画像データを受信し、選択された画像の詳細情報を表示するウィジェット。
Enhanced Event-Driven Patternによる直接データ受信とUI更新を実装。

主要機能:
- 画像メタデータの詳細表示（ファイル名、サイズ、作成日時等）
- Rating/Scoreのインライン編集（コンボボックス・スライダー）
- アノテーションデータ（タグ・キャプション）の表示
- データベース保存操作の中継

アーキテクチャ:
- Direct Widget Communication Pattern準拠
- DatasetStateManager.current_image_data_changedシグナル受信
- ImageDetails構造体による型安全なデータ管理
- AnnotationDataDisplayWidget統合による表示機能
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QScrollArea, QWidget

from ...gui.designer.SelectedImageDetailsWidget_ui import Ui_SelectedImageDetailsWidget
from ...services.date_formatter import format_datetime_for_display
from ...utils.log import logger
from .annotation_data_display_widget import (
    AnnotationData,
    AnnotationDataDisplayWidget,
    ImageDetails,
)

if TYPE_CHECKING:
    from ..state.dataset_state import DatasetStateManager


class SelectedImageDetailsWidget(QScrollArea):
    """
    選択画像詳細情報表示ウィジェット

    DatasetStateManagerから送信される画像メタデータを受信し、選択画像の詳細情報を表示。
    Enhanced Event-Driven Patternによる非同期データ更新とユーザー操作の双方向処理を実装。

    データフロー:
    1. DatasetStateManager.current_image_data_changed -> _on_image_data_received()
    2. メタデータ解析 -> _build_image_details_from_metadata()
    3. UI更新 -> _update_details_display()
    4. ユーザー編集 -> Rating/Score変更シグナル発行
    5. 保存要求 -> save_requested シグナル発行

    UI構成:
    - groupBoxImageInfo: ファイル名、サイズ、作成日時表示
    - groupBoxRatingScore: Rating選択、Score調整スライダー
    - annotationDataDisplay: タグ・キャプション表示（AnnotationDataDisplayWidget）
    - pushButtonSave: 変更内容の保存ボタン

    型安全性:
    - ImageDetails dataclassによる構造化データ管理
    - 全メタデータフィールドの型チェック・デフォルト値処理
    - None安全なデータアクセスパターン実装
    """

    # シグナル
    image_details_loaded = Signal(ImageDetails)  # 画像詳細読み込み完了
    rating_updated = Signal(int, str)  # Rating 更新 (image_id, rating_value)
    score_updated = Signal(int, int)  # Score 更新 (image_id, score_value)
    save_requested = Signal(dict)  # 保存要求 {image_id, rating, score}

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

        # DatasetStateManagerへの参照（後でset_dataset_state_managerで設定）
        self._dataset_state_manager: DatasetStateManager | None = None

        # 内部状態
        self.current_details: ImageDetails | None = None
        self.current_image_id: int | None = None

        # UI設定
        self.ui = Ui_SelectedImageDetailsWidget()
        self.ui.setupUi(self)
        self.annotation_display: AnnotationDataDisplayWidget = self.ui.annotationDataDisplay
        self._setup_connections()
        self._clear_display()

        logger.debug("SelectedImageDetailsWidget initialized")

    def _setup_connections(self) -> None:
        """
        UIコンポーネントのシグナル接続設定

        Qt Designerで設定されていないシグナルを追加接続。
        - Rating/Scoreの変更監視
        - 保存ボタンのクリック処理
        """
        # 自動接続されるシグナル（Qt Designerで設定済み）:
        # - comboBoxRating.currentTextChanged -> _on_rating_changed
        # - sliderScore.valueChanged -> _on_score_changed
        # - pushButtonSaveRating.clicked -> _on_save_clicked
        # - pushButtonSaveScore.clicked -> _on_save_clicked

        # AnnotationDataDisplayWidgetからのシグナル接続
        self.annotation_display.data_loaded.connect(self._on_annotation_data_loaded)

        logger.debug("SelectedImageDetailsWidget signals connected")

    @Slot(str)
    def _on_rating_changed(self, rating_value: str) -> None:
        """
        Ratingコンボボックス変更ハンドラ

        Args:
            rating_value: 選択されたRating値（PG, PG-13, R, X, XXX）

        処理:
        1. 現在の画像IDチェック
        2. rating_updated シグナル発行
        3. ログ記録

        Notes:
            - Qt Designerで自動接続
            - 保存は別途保存ボタンクリックで実行
        """
        if self.current_image_id is None:
            logger.warning("Rating changed but no image selected")
            return

        logger.debug(f"Rating changed: image_id={self.current_image_id}, rating={rating_value}")
        self.rating_updated.emit(self.current_image_id, rating_value)

    @Slot(int)
    def _on_score_changed(self, score_value: int) -> None:
        """
        Scoreスライダー変更ハンドラ

        Args:
            score_value: スライダー値（0-1000）

        処理:
        1. 現在の画像IDチェック
        2. 表示値の更新（0.1単位で表示）
        3. score_updated シグナル発行
        4. ログ記録

        Notes:
            - Qt Designerで自動接続
            - 保存は別途保存ボタンクリックで実行
            - スライダー値を10で割って小数点1桁表示
        """
        if self.current_image_id is None:
            logger.warning("Score changed but no image selected")
            return

        # スライダー値を0.1単位に変換して表示
        display_value = score_value / 10.0
        logger.debug(f"Score changed: image_id={self.current_image_id}, score={display_value}")

        self.score_updated.emit(self.current_image_id, score_value)

    @Slot()
    def _on_save_clicked(self) -> None:
        """
        保存ボタンクリックハンドラ

        処理:
        1. 現在の画像IDチェック
        2. Rating/Scoreの現在値を取得
        3. save_requested シグナル発行
        4. ログ記録

        シグナルデータ形式:
            {
                "image_id": int,
                "rating": str,
                "score": int
            }

        Notes:
            - Qt Designerで自動接続
            - pushButtonSaveRating/pushButtonSaveScore両方から接続
            - 実際の保存処理はMainWindowで実行
        """
        if self.current_image_id is None:
            logger.warning("Save requested but no image selected")
            return

        current_rating = self.ui.comboBoxRating.currentText()
        current_score = self.ui.sliderScore.value()

        save_data = {
            "image_id": self.current_image_id,
            "rating": current_rating,
            "score": current_score,
        }

        logger.debug(f"Save requested: {save_data}")
        self.save_requested.emit(save_data)

    @Slot()
    def _on_annotation_data_loaded(self) -> None:
        """
        AnnotationDataDisplayWidgetからのデータ読み込み完了通知ハンドラ

        AnnotationDataDisplayWidgetの内部処理完了を受けて追加処理を実行可能。
        現在は特別な処理なし。
        """
        logger.debug("Annotation data loaded in AnnotationDataDisplayWidget")

    # Phase 3: Direct Widget Communication Pattern
    def connect_to_data_signals(self, state_manager: "DatasetStateManager") -> None:
        """データシグナル接続（Phase 2互換）"""
        state_manager.current_image_data_changed.connect(self._on_image_data_received)
        logger.debug("SelectedImageDetailsWidget connected to current_image_data_changed signal")

    def connect_to_thumbnail_widget(self, thumbnail_widget: Any) -> None:
        """
        ThumbnailSelectorWidgetと直接接続（Phase 3パターン）

        Args:
            thumbnail_widget: 接続先のThumbnailSelectorWidgetインスタンス

        接続するシグナル:
            - thumbnail_widget.image_metadata_selected -> _on_direct_metadata_received

        Notes:
            - DatasetStateManager経由の接続に代わる直接接続パターン
            - より高速で明示的なデータフロー
        """
        thumbnail_widget.image_metadata_selected.connect(self._on_direct_metadata_received)
        logger.debug("Connected SelectedImageDetailsWidget to ThumbnailSelectorWidget directly")

    @Slot(dict)
    def _on_direct_metadata_received(self, metadata: dict[str, Any]) -> None:
        """
        ThumbnailSelectorWidgetからの直接メタデータ受信（Phase 3パターン）

        Args:
            metadata: 画像メタデータ辞書

        処理:
        1. メタデータからImageDetailsを構築
        2. UI更新
        """
        logger.debug(f"Direct metadata received: image_id={metadata.get('id')}")
        details = self._build_image_details_from_metadata(metadata)
        self._update_details_display(details)

    @Slot(dict)
    def _on_image_data_received(self, image_data: dict[str, Any]) -> None:
        """
        DatasetStateManagerからの画像データ受信ハンドラ（Phase 2互換）

        Args:
            image_data: 画像メタデータ辞書

        処理:
        1. 空データチェック（選択解除時）
        2. ImageDetails構造体への変換
        3. UI更新処理の実行

        Notes:
            - Enhanced Event-Driven Pattern実装
            - ImageDetails dataclass による型安全な処理
            - Phase 3では direct_metadata_received が推奨
        """
        if not image_data:
            logger.info("SelectedImageDetailsWidget: 空データ受信 - 表示をクリア")
            self._clear_display()
            return

        image_id = image_data.get("id")
        logger.info(f"📨 SelectedImageDetailsWidget(instance={id(self)}): current_image_data_changed シグナル受信 - image_id: {image_id}")

        details = self._build_image_details_from_metadata(image_data)
        self._update_details_display(details)

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
        file_path_str = metadata.get("file_path", "")
        file_name = Path(file_path_str).name if file_path_str else ""

        width = metadata.get("width", 0)
        height = metadata.get("height", 0)
        image_size = f"{width} x {height}" if width and height else ""

        file_size = metadata.get("file_size", 0)
        if file_size:
            size_kb = file_size / 1024
            file_size_str = f"{size_kb / 1024:.2f} MB" if size_kb >= 1024 else f"{size_kb:.2f} KB"
        else:
            file_size_str = ""

        created_at = metadata.get("created_at")
        created_date = format_datetime_for_display(created_at) if created_at else ""

        # Rating / Score
        rating_value = metadata.get("rating", "")
        score_value = metadata.get("score", 0)

        # アノテーション情報（Repository層で変換済み）
        annotations = metadata.get("annotations", {})

        # Repository層で変換済みのlist[dict]をそのまま使用
        tags_list = annotations.get("tags", [])

        # caption: Repository層で提供される caption_text を使用
        caption_text = annotations.get("caption_text", "")

        # tags_text: Repository層で提供される tags_text を使用
        tags_text = annotations.get("tags_text", "")

        annotation_data = AnnotationData(
            tags=tags_list,  # ← list[dict] をそのまま渡す
            caption=caption_text,
            aesthetic_score=annotations.get("score_value"),
            overall_score=int(annotations.get("rating_value", 0)),
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
            caption=caption_text,
            tags=tags_text,
            annotation_data=annotation_data,
        )

        logger.debug(
            f"Built ImageDetails: id={details.image_id}, tags={len(annotation_data.tags)}, "
            f"caption_len={len(caption_text)}"
        )

        return details

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

        # Rating / Score
        self._update_rating_score_display(details)

        # アノテーションデータ
        if details.annotation_data:
            self.annotation_display.update_data(details.annotation_data)

        logger.info(f"✅ SelectedImageDetailsWidget表示更新完了: image_id={details.image_id}")
        self.image_details_loaded.emit(details)

    def _update_rating_score_display(self, details: ImageDetails) -> None:
        """
        Rating/Scoreの表示更新

        Args:
            details: 画像詳細情報

        処理:
        1. Rating コンボボックスの選択
        2. Score スライダーの値設定

        Notes:
            - シグナル発火を抑制して内部更新のみ実行
            - blockSignals() で一時的にシグナルを無効化
        """
        # Rating設定（シグナル発火を抑制）
        self.ui.comboBoxRating.blockSignals(True)
        rating_index = self.ui.comboBoxRating.findText(details.rating_value)
        if rating_index >= 0:
            self.ui.comboBoxRating.setCurrentIndex(rating_index)
        else:
            self.ui.comboBoxRating.setCurrentIndex(0)  # 空の選択肢
        self.ui.comboBoxRating.blockSignals(False)

        # Score設定（シグナル発火を抑制）
        self.ui.sliderScore.blockSignals(True)
        self.ui.sliderScore.setValue(details.score_value)
        self.ui.sliderScore.blockSignals(False)

        logger.debug(f"Rating/Score updated: {details.rating_value}, {details.score_value}")

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
        - comboBoxRating: 空選択
        - sliderScore: 0
        - annotationDataDisplay: クリア
        """
        self.current_details = None
        self.current_image_id = None

        self.ui.labelFileNameValue.setText("-")
        self.ui.labelImageSizeValue.setText("-")
        self.ui.labelFileSizeValue.setText("-")
        self.ui.labelCreatedDateValue.setText("-")

        # Rating/Scoreをリセット（シグナル発火抑制）
        self.ui.comboBoxRating.blockSignals(True)
        self.ui.comboBoxRating.setCurrentIndex(0)
        self.ui.comboBoxRating.blockSignals(False)

        self.ui.sliderScore.blockSignals(True)
        self.ui.sliderScore.setValue(0)
        self.ui.sliderScore.blockSignals(False)

        # AnnotationDataDisplayWidgetのクリア
        self.annotation_display.clear_data()

        logger.debug("SelectedImageDetailsWidget display cleared")

    def get_current_details(self) -> ImageDetails | None:
        """現在表示中の画像詳細情報を返す"""
        return self.current_details

    def set_enabled_state(self, enabled: bool) -> None:
        """
        ウィジェット全体の有効/無効状態を設定

        Args:
            enabled: True=有効, False=無効

        処理:
        - Rating/Score編集の有効/無効切り替え
        - 保存ボタンの有効/無効切り替え
        """
        self.ui.comboBoxRating.setEnabled(enabled)
        self.ui.sliderScore.setEnabled(enabled)
        self.ui.pushButtonSaveRating.setEnabled(enabled)
        self.ui.pushButtonSaveScore.setEnabled(enabled)
        logger.debug(f"SelectedImageDetailsWidget enabled state set to {enabled}")


if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    # アプリケーションのエントリポイント
    def main():
        """アプリケーションのメイン実行関数"""
        app = QApplication(sys.argv)

        # ウィジェットのインスタンスを作成
        widget = SelectedImageDetailsWidget()

        # --- テスト用のダミーデータ ---
        dummy_annotation = AnnotationData(
            tags=[
                {"tag": "1girl", "model_name": "wd-v1-4", "source": "AI", "confidence_score": 0.95, "is_edited_manually": False},
                {"tag": "solo", "model_name": "wd-v1-4", "source": "AI", "confidence_score": 0.90, "is_edited_manually": False},
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
        widget._update_details_display(dummy_details)  # type: ignore
        widget.set_enabled_state(True)  # 最初から操作可能にする

        # ウィジェットを表示
        widget.setWindowTitle("Selected Image Details - Test")
        widget.show()

        sys.exit(app.exec())

    main()
