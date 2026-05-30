"""
Staging Widget - サムネイルステージングウィジェット

複数画像を個別実行フローや Provider Batch 実行フローで共通利用するための
サムネイル表示付きステージングコンポーネント。

主要機能:
- ステージングリストへの画像追加（最大500枚）
- 重複排除・追加順保持（OrderedDict）
- サムネイル表示（ThumbnailSelectorWidget）
- staged_images_changed / staging_cleared シグナル

アーキテクチャ:
- ADR 0036: Compound Widget 分割方針に従いステージング責務を分離
- ADR 0041: BatchTagAddWidget / ProviderBatchJobWidget の共通コンポーネント
"""

from collections import OrderedDict
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QSize, Qt, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsView, QWidget

from ...gui.designer.StagingWidget_ui import Ui_StagingWidget
from ...utils.log import logger

if TYPE_CHECKING:
    from ..state.dataset_state import DatasetStateManager
    from .thumbnail import ThumbnailSelectorWidget


class StagingWidget(QWidget):
    """
    サムネイルステージングウィジェット

    複数画像のステージング管理（追加・削除・クリア）とサムネイル表示を担当する
    共有コンポーネント。BatchTagAddWidget と ProviderBatchJobWidget の両方から
    利用される。

    データフロー:
    1. add_image_ids() / add_selected_images() -> ステージングリストに追加
    2. staged_images_changed シグナル発行（追加後）
    3. clear() -> ステージングリストを全削除
    4. staging_cleared / staged_images_changed([]) シグナル発行（クリア後）

    UI 構成:
    - groupBoxStagingList: ステージング一覧グループボックス
    - labelStagingCount: N / 500 枚 カウントラベル
    - listWidgetStaging (非表示, ThumbnailSelectorWidget に置換)
    - pushButtonClearStaging: クリアボタン

    ステージングリスト仕様:
    - 最大500枚まで
    - 重複なし（OrderedDict キー存在確認）
    - 追加順を保持（OrderedDict）
    """

    # シグナル
    staged_images_changed = Signal(list)  # list[int] - ステージング画像IDリスト
    staging_cleared = Signal()  # ステージングリストクリア

    # 定数
    MAX_STAGING_IMAGES = 500

    def __init__(self, parent: QWidget | None = None):
        """
        StagingWidget 初期化

        UIコンポーネントの初期化、内部状態の設定、サムネイルウィジェット設定を実行。

        Args:
            parent: 親ウィジェット

        初期状態:
            - _staged_images: 空の OrderedDict
            - _dataset_state_manager: None
        """
        super().__init__(parent)
        logger.debug("StagingWidget.__init__() called")

        # 内部状態: ステージング画像管理（OrderedDict で順序保持 + 重複排除）
        # {image_id: (filename, stored_path)}
        self._staged_images: OrderedDict[int, tuple[str, str]] = OrderedDict()

        # サムネイルキャッシュ（表示用の縮小Pixmap）
        self._thumbnail_cache: dict[int, QPixmap] = {}

        # DatasetStateManager への参照（後で set_dataset_state_manager() で設定）
        self._dataset_state_manager: DatasetStateManager | None = None

        # UI 設定
        self.ui = Ui_StagingWidget()
        setup_ui = cast(Callable[[QWidget], None], self.ui.setupUi)
        setup_ui(self)

        self._staging_thumbnail_widget: ThumbnailSelectorWidget | None = None
        self._setup_staging_thumbnail_widget()

        # 初期状態更新
        self._update_staging_count_label()

        logger.debug("StagingWidget initialized")

    def set_dataset_state_manager(self, dataset_state_manager: "DatasetStateManager") -> None:
        """DatasetStateManager への参照を設定する。

        Args:
            dataset_state_manager: DatasetStateManager インスタンス
        """
        self._dataset_state_manager = dataset_state_manager
        logger.debug("DatasetStateManager reference set in StagingWidget")

    def connect_shared_staging(self, source: "StagingWidget") -> None:
        """別 StagingWidget と同じステージング状態を共有する。

        Provider Batch タブは通常アノテーションと同じ対象集合を扱うため、
        class だけでなく OrderedDict 実体も共有する。
        """
        if source is self:
            return
        self._staged_images = source.get_staged_items()
        self._thumbnail_cache = source._thumbnail_cache
        source.staged_images_changed.connect(self._sync_from_shared_staging)
        source.staging_cleared.connect(self._sync_from_shared_staging)
        self.staged_images_changed.connect(source._sync_from_shared_staging)
        self.staging_cleared.connect(source._sync_from_shared_staging)
        self._refresh_staging_list_ui()

    @Slot()
    @Slot(list)
    def _sync_from_shared_staging(self, _image_ids: list[int] | None = None) -> None:
        """共有ステージングの変更を自分の表示へ反映する。"""
        self._refresh_staging_list_ui()

    def _setup_staging_thumbnail_widget(self) -> None:
        """ステージング一覧を ThumbnailSelectorWidget で表示するセットアップ。"""
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
        """ステージング数ラベルを更新する。

        現在のステージング画像数 / 最大数 を表示。
        """
        count = len(self._staged_images)
        self.ui.labelStagingCount.setText(f"{count} / {self.MAX_STAGING_IMAGES} 枚")

    def add_image_ids(self, image_ids: list[int]) -> None:
        """指定した画像 ID リストをステージングに追加する。

        最大 MAX_STAGING_IMAGES 枚の上限と重複排除を適用。
        追加後に staged_images_changed シグナルを発行する。

        Args:
            image_ids: 追加する画像 ID リスト
        """
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

    def add_selected_images(self) -> None:
        """DatasetStateManager.selected_image_ids をステージングに追加する。

        DatasetStateManager が未設定の場合、または選択画像がない場合は何もしない。
        """
        if self._dataset_state_manager is None:
            logger.warning("DatasetStateManager not set")
            return

        selected_ids = self._dataset_state_manager.selected_image_ids
        if not selected_ids:
            logger.info("No images selected")
            return

        self.add_image_ids(selected_ids)

    def clear(self) -> None:
        """ステージングリストを全削除する。

        staging_cleared と staged_images_changed([]) シグナルを発行する。
        """
        self._staged_images.clear()
        self._thumbnail_cache.clear()
        self._refresh_staging_list_ui()
        logger.info("Staging list cleared")

        # シグナル発行
        self.staging_cleared.emit()
        self.staged_images_changed.emit([])

    def get_image_ids(self) -> list[int]:
        """ステージング中の画像 ID リストを返す。

        Returns:
            追加順の画像 ID リスト
        """
        return list(self._staged_images.keys())

    def count(self) -> int:
        """ステージング中の画像数を返す。

        Returns:
            ステージング画像数
        """
        return len(self._staged_images)

    def get_staged_items(self) -> "OrderedDict[int, tuple[str, str]]":
        """ステージング中の画像メタデータを返す。

        Returns:
            {image_id: (filename, stored_path)} の OrderedDict（追加順）
        """
        return self._staged_images

    def _refresh_staging_list_ui(self) -> None:
        """ステージングリスト UI を再描画する。

        OrderedDict の内容をサムネイルウィジェットに反映。
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

    @Slot()
    def _on_clear_staging_clicked(self) -> None:
        """「クリア」ボタンクリックハンドラ。

        ステージングリストを全削除する。
        """
        self.clear()
