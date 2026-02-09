"""
Batch Tag Add Widget - バッチタグ追加ウィジェット

複数画像に対して1つのタグを一括追加するための専用ウィジェット。
MainWindow右パネルのタブとして配置され、バッチ操作を担当。

主要機能:
- ステージングリストへの画像追加（最大500枚）
- タグの正規化とバリデーション
- バッチタグ追加操作

アーキテクチャ:
- QTabWidget のタブ3（バッチタグ追加）に配置
- DatasetStateManager から選択画像IDを取得
- 保存時に tag_add_requested シグナルを発行
- MainWindow が ImageDBWriteService 経由で一括保存処理を実行
"""

from collections import OrderedDict
from typing import TYPE_CHECKING

from genai_tag_db_tools.utils.cleanup_str import TagCleaner
from PySide6.QtCore import QSize, Qt, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsView, QMessageBox, QVBoxLayout, QWidget

from ...gui.designer.BatchTagAddWidget_ui import Ui_BatchTagAddWidget
from ...utils.log import logger

if TYPE_CHECKING:
    from ..state.dataset_state import DatasetStateManager
    from .thumbnail import ThumbnailSelectorWidget


def normalize_tag(tag: str) -> str:
    """タグを正規化する（TagCleaner.clean_format() + lower + strip）。

    Args:
        tag: 入力タグ文字列

    Returns:
        正規化されたタグ。TagCleaner.clean_format() が None を返す場合は空文字列。
    """
    cleaned: str | None = TagCleaner.clean_format(tag)
    if cleaned is None:
        return ""
    return cleaned.strip().lower()


class BatchTagAddWidget(QWidget):
    """
    バッチタグ追加ウィジェット

    複数画像に対して1つのタグを一括追加。
    ステージングリスト管理とタグ正規化を担当。

    データフロー:
    1. "選択中の画像を追加" -> DatasetStateManager.selected_image_ids を取得
    2. ステージングリストに追加（最大500枚、重複なし）
    3. タグ入力 -> 正規化（lower + strip）
    4. "追加" -> tag_add_requested シグナル発行
    5. MainWindow が ImageDBWriteService.add_tag_batch() で DB 更新

    UI構成:
    - stagingThumbnailWidget: ステージング画像サムネイル（ThumbnailSelectorWidget）
    - lineEditTag: タグ入力フィールド
    - pushButtonClearStaging: ステージングリストをクリア
    - pushButtonAddTag: タグを追加

    ステージングリスト仕様:
    - 最大500枚まで
    - 重複なし（set管理）
    - 追加順を保持（OrderedDict）
    - 個別削除: Delete キー
    """

    # シグナル
    staged_images_changed = Signal(list)  # List[int] - ステージング画像IDリスト
    tag_add_requested = Signal(list, str)  # (image_ids, tag) - タグ追加要求
    staging_cleared = Signal()  # ステージングリストクリア

    # 定数
    MAX_STAGING_IMAGES = 500

    def __init__(self, parent: QWidget | None = None):
        """
        BatchTagAddWidget 初期化

        UIコンポーネントの初期化、内部状態の設定、シグナル接続を実行。

        Args:
            parent: 親ウィジェット

        初期状態:
            - _staged_images: 空の OrderedDict
            - _dataset_state_manager: None
            - UI: 空表示状態
        """
        super().__init__(parent)
        logger.debug("BatchTagAddWidget.__init__() called")

        # 内部状態: ステージング画像管理（OrderedDict で順序保持 + 重複排除）
        # {image_id: (filename, stored_path)}
        self._staged_images: OrderedDict[int, tuple[str, str]] = OrderedDict()

        # サムネイルキャッシュ（表示用の縮小Pixmap）
        self._thumbnail_cache: dict[int, QPixmap] = {}

        # DatasetStateManagerへの参照（後でset_dataset_state_managerで設定）
        self._dataset_state_manager: DatasetStateManager | None = None

        # UI設定
        self.ui = Ui_BatchTagAddWidget()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]

        self._staging_thumbnail_widget: ThumbnailSelectorWidget | None = None
        self._setup_staging_thumbnail_widget()

        # 初期状態更新
        self._update_staging_count_label()

        logger.info("BatchTagAddWidget initialized")

    def set_dataset_state_manager(self, dataset_state_manager: "DatasetStateManager") -> None:
        """
        DatasetStateManagerへの参照を設定

        Args:
            dataset_state_manager: DatasetStateManager インスタンス
        """
        self._dataset_state_manager = dataset_state_manager
        logger.debug("DatasetStateManager reference set in BatchTagAddWidget")

    def _setup_staging_thumbnail_widget(self) -> None:
        """ステージング一覧をThumbnailSelectorWidgetで表示する。"""
        from .thumbnail import ThumbnailSelectorWidget

        layout = self.ui.verticalLayoutStaging
        list_widget = self.ui.listWidgetStaging

        widget = ThumbnailSelectorWidget(parent=self.ui.groupBoxStagingList, dataset_state=None)
        widget.setObjectName("stagingThumbnailWidget")
        widget.thumbnail_size = QSize(96, 96)
        widget.sliderThumbnailSize.setValue(96)
        widget.sliderThumbnailSize.hide()
        widget.frameThumbnailHeader.hide()
        widget.graphics_view.setDragMode(QGraphicsView.DragMode.NoDrag)
        widget.graphics_view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        widget.scrollAreaThumbnails.setFrameShape(QFrame.Shape.NoFrame)
        widget.setMinimumHeight(150)

        insert_index = layout.indexOf(list_widget)
        if insert_index != -1:
            layout.insertWidget(insert_index, widget)
        else:
            layout.addWidget(widget)

        layout.removeWidget(list_widget)
        list_widget.setParent(self)
        list_widget.hide()

        self._staging_thumbnail_widget = widget

    def _update_staging_count_label(self) -> None:
        """
        ステージング数ラベルを更新

        現在のステージング画像数 / 最大数 を表示。
        """
        count = len(self._staged_images)
        self.ui.labelStagingCount.setText(f"{count} / {self.MAX_STAGING_IMAGES} 枚")

    def _normalize_tag(self, tag: str) -> str:
        """タグを正規化する（モジュールレベル normalize_tag() に委譲）。

        Args:
            tag: 入力タグ文字列

        Returns:
            正規化されたタグ（TagCleaner.clean_format() + lower + strip）
        """
        return normalize_tag(tag)

    @Slot()
    def _on_add_selected_clicked(self) -> None:
        """
        "選択中の画像を追加" ボタンクリックハンドラ

        DatasetStateManager.selected_image_ids からIDを取得し、
        ステージングリストに追加（最大500枚まで）。
        """
        if self._dataset_state_manager is None:
            logger.warning("DatasetStateManager not set")
            return

        selected_ids = self._dataset_state_manager.selected_image_ids
        if not selected_ids:
            logger.info("No images selected")
            return

        self._add_image_ids_to_staging(selected_ids)

    def _add_image_ids_to_staging(self, image_ids: list[int]) -> None:
        """指定した画像IDリストをステージングに追加する。"""
        if self._dataset_state_manager is None:
            logger.warning("DatasetStateManager not set")
            return

        added_count = 0
        for image_id in image_ids:
            # 上限チェック
            if len(self._staged_images) >= self.MAX_STAGING_IMAGES:
                logger.warning(f"Staging limit reached ({self.MAX_STAGING_IMAGES}), cannot add more images")
                break

            # 重複チェック（OrderedDict のキー存在確認）
            if image_id in self._staged_images:
                continue

            # 画像情報取得
            image_metadata = self._dataset_state_manager.get_image_by_id(image_id)
            if image_metadata:
                # stored_image_path からファイル名を抽出、またはIDをフォールバック
                from pathlib import Path

                stored_path = image_metadata.get("stored_image_path", "") if image_metadata else ""
                filename = Path(stored_path).name if stored_path else f"ID:{image_id}"
                self._staged_images[image_id] = (filename, stored_path)
                added_count += 1

        # UI 更新
        self._refresh_staging_list_ui()
        logger.info(f"Added {added_count} images to staging (total: {len(self._staged_images)})")

        # シグナル発行
        self.staged_images_changed.emit(list(self._staged_images.keys()))

    def add_selected_images_to_staging(self) -> None:
        """外部から選択画像をステージングに追加するための公開API"""
        self._on_add_selected_clicked()

    def add_image_ids_to_staging(self, image_ids: list[int]) -> None:
        """外部から指定画像IDをステージングに追加する公開API。"""
        if not image_ids:
            logger.info("No visible image ids provided for staging")
            return
        self._add_image_ids_to_staging(image_ids)

    def attach_tag_input_to(self, container: QWidget) -> None:
        """タグ入力UIを外部コンテナへ移動してステージング一覧と分離する。"""
        tag_input = self.ui.groupBoxTagInput
        if tag_input.parent() is not container:
            tag_input.setParent(container)
            if container.layout() is None:
                layout = QVBoxLayout(container)
                layout.setContentsMargins(0, 0, 0, 0)
            container.layout().addWidget(tag_input)

        splitter = getattr(self.ui, "splitterBatchTagStaging", None)
        if splitter:
            idx = splitter.indexOf(tag_input)
            if idx != -1:
                splitter.widget(idx).hide()
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 0)

    @Slot()
    def _on_clear_staging_clicked(self) -> None:
        """
        "クリア" ボタンクリックハンドラ

        ステージングリストを全削除。
        """
        self._staged_images.clear()
        self._thumbnail_cache.clear()
        self._refresh_staging_list_ui()
        logger.info("Staging list cleared")

        # シグナル発行
        self.staging_cleared.emit()
        self.staged_images_changed.emit([])

    @Slot()
    def _on_add_tag_clicked(self) -> None:
        """
        "追加" ボタンクリックハンドラ

        タグを正規化し、tag_add_requested シグナルを発行。

        バリデーション:
        - 空タグチェック
        - ステージング画像数チェック
        """
        # ステージング画像チェック
        if not self._staged_images:
            logger.warning("No images in staging list")
            QMessageBox.warning(
                self,
                "タグ追加エラー",
                "ステージングリストに画像がありません。\n画像を選択してからタグを追加してください。",
            )
            return

        # タグ入力取得
        tag_input = self.ui.lineEditTag.text()

        # 空タグチェック
        if not tag_input.strip():
            logger.warning("Empty tag input")
            QMessageBox.warning(self, "タグ追加エラー", "タグを入力してください。")
            return

        # タグ正規化
        normalized_tag = self._normalize_tag(tag_input)

        if not normalized_tag:
            logger.warning("Tag normalization resulted in empty string")
            QMessageBox.warning(
                self,
                "タグ追加エラー",
                f"タグ '{tag_input.strip()}' の正規化に失敗しました。",
            )
            return

        # シグナル発行
        image_ids = list(self._staged_images.keys())
        logger.info(f"Tag add requested: {normalized_tag} for {len(image_ids)} images")
        self.tag_add_requested.emit(image_ids, normalized_tag)

        # 成功後: タグ入力フィールドをクリア
        self.ui.lineEditTag.clear()

    def _refresh_staging_list_ui(self) -> None:
        """
        ステージングリストUIを再描画

        OrderedDict の内容をリストウィジェットに反映。
        stored_image_path は相対パスの場合があるため、resolve_stored_path で解決する。
        """
        from lorairo.database.db_core import resolve_stored_path

        staging_paths: list[tuple[str, int]] = []

        for image_id, (_, stored_path) in self._staged_images.items():
            path = stored_path
            if not path and self._dataset_state_manager:
                metadata = self._dataset_state_manager.get_image_by_id(image_id)
                if metadata:
                    path = metadata.get("stored_image_path", "") or ""

            # 相対パスを絶対パスに解決
            if path:
                path = str(resolve_stored_path(path))

            staging_paths.append((path, image_id))

        if self._staging_thumbnail_widget:
            self._staging_thumbnail_widget.load_thumbnails_from_paths(staging_paths)

        self._update_staging_count_label()
