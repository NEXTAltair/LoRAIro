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
from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QListWidgetItem, QWidget

from ...gui.designer.BatchTagAddWidget_ui import Ui_BatchTagAddWidget
from ...utils.log import logger

if TYPE_CHECKING:
    from ..state.dataset_state import DatasetStateManager


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
    - listWidgetStaging: ステージング画像リスト
    - lineEditTag: タグ入力フィールド
    - pushButtonAddSelected: 選択画像をステージングに追加
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
        self._staged_images: OrderedDict[int, str] = OrderedDict()  # {image_id: filename}

        # DatasetStateManagerへの参照（後でset_dataset_state_managerで設定）
        self._dataset_state_manager: DatasetStateManager | None = None

        # UI設定
        self.ui = Ui_BatchTagAddWidget()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]

        # キー入力ハンドリング
        self.ui.listWidgetStaging.keyPressEvent = self._on_list_key_press  # type: ignore[method-assign]

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

    def _update_staging_count_label(self) -> None:
        """
        ステージング数ラベルを更新

        現在のステージング画像数 / 最大数 を表示。
        """
        count = len(self._staged_images)
        self.ui.labelStagingCount.setText(f"{count} / {self.MAX_STAGING_IMAGES} 枚")

    def _normalize_tag(self, tag: str) -> str:
        """
        タグを正規化（TagDBtools 統合）

        Args:
            tag: 入力タグ文字列

        Returns:
            str: 正規化されたタグ（TagCleaner.clean_format() + lower + strip）

        Note:
            TagCleaner.clean_format() は genai-tag-db-tools の標準正規化処理を使用。
            ExistingFileReader や ImageDatabaseRepository と同一のロジック。
            小文字変換を追加して重複チェックの一貫性を保証。
        """
        return TagCleaner.clean_format(tag).strip().lower()

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

        added_count = 0
        for image_id in selected_ids:
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

                stored_path = image_metadata.get("stored_image_path", "")
                filename = Path(stored_path).name if stored_path else f"ID:{image_id}"
                self._staged_images[image_id] = filename
                added_count += 1

        # UI 更新
        self._refresh_staging_list_ui()
        logger.info(f"Added {added_count} images to staging (total: {len(self._staged_images)})")

        # シグナル発行
        self.staged_images_changed.emit(list(self._staged_images.keys()))

    @Slot()
    def _on_clear_staging_clicked(self) -> None:
        """
        "クリア" ボタンクリックハンドラ

        ステージングリストを全削除。
        """
        self._staged_images.clear()
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
            # TODO: QMessageBox でエラー表示
            return

        # タグ入力取得
        tag_input = self.ui.lineEditTag.text()

        # 空タグチェック
        if not tag_input.strip():
            logger.warning("Empty tag input")
            # TODO: QMessageBox でエラー表示
            return

        # タグ正規化
        normalized_tag = self._normalize_tag(tag_input)

        if not normalized_tag:
            logger.warning("Tag normalization resulted in empty string")
            # TODO: QMessageBox でエラー表示
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
        """
        self.ui.listWidgetStaging.clear()

        for image_id, filename in self._staged_images.items():
            item = QListWidgetItem(f"{filename} (ID: {image_id})")
            item.setData(1, image_id)  # Qt::UserRole + 1 に image_id を保存
            self.ui.listWidgetStaging.addItem(item)

        self._update_staging_count_label()

    def _on_list_key_press(self, event) -> None:  # type: ignore[no-untyped-def]
        """
        リストウィジェットのキー入力ハンドラ

        Delete/Backspace キーで選択項目を削除。

        Args:
            event: QKeyEvent
        """
        from PySide6.QtCore import Qt

        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            current_item = self.ui.listWidgetStaging.currentItem()
            if current_item:
                image_id = current_item.data(1)  # Qt::UserRole + 1 から image_id 取得
                if image_id in self._staged_images:
                    del self._staged_images[image_id]
                    self._refresh_staging_list_ui()
                    logger.info(f"Removed image_id {image_id} from staging")

                    # シグナル発行
                    self.staged_images_changed.emit(list(self._staged_images.keys()))
        else:
            # デフォルトのキー処理に委譲
            QWidget.keyPressEvent(self.ui.listWidgetStaging, event)
