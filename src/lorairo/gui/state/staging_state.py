"""ステージング集合の状態マネージャ (Epic #867 / #876)。

ステージング集合 (送信・エクスポート・トリアージの共通対象集合) の SSoT。
従来 ``StagingWidget`` が保持していた OrderedDict をここへ hoist し、複数タブの
``StagingWidget`` は本マネージャを共有する view へ降格する (ADR 0074、ADR 0041/0055 を一部改訂)。

重複排除・追加順保持 (OrderedDict)・最大件数上限・``DatasetStateManager`` 経由の
メタデータ解決を担い、変更を Signal で通知する。
"""

from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from ...utils.log import logger

if TYPE_CHECKING:
    from .dataset_state import DatasetStateManager


class StagingStateManager(QObject):
    """ステージング集合の単一信頼源 (SSoT)。

    ``{image_id: (filename, stored_path)}`` の OrderedDict を保持し、追加・削除・
    クリアを提供する。複数の ``StagingWidget`` が同一インスタンスを共有することで、
    タブ間のステージング状態を自動同期する (従来の ``connect_shared_staging`` を置換)。

    Signals:
        staged_images_changed: ステージング画像 ID リストが変化したとき (list[int])。
        staging_cleared: ステージングが全クリアされたとき。
    """

    staged_images_changed = Signal(list)  # list[int] - ステージング画像IDリスト
    staging_cleared = Signal()  # ステージングリストクリア

    MAX_STAGING_IMAGES = 500

    def __init__(self, parent: QObject | None = None) -> None:
        """ステージング状態マネージャを初期化する。

        Args:
            parent: 親 QObject。
        """
        super().__init__(parent)
        # {image_id: (filename, stored_path)} の OrderedDict (順序保持 + 重複排除)
        self._staged_images: OrderedDict[int, tuple[str, str]] = OrderedDict()
        self._dataset_state_manager: DatasetStateManager | None = None

    def set_dataset_state_manager(self, dataset_state_manager: "DatasetStateManager") -> None:
        """メタデータ解決用の DatasetStateManager 参照を設定する。

        Args:
            dataset_state_manager: DatasetStateManager インスタンス。
        """
        self._dataset_state_manager = dataset_state_manager

    def add_image_ids(self, image_ids: list[int]) -> None:
        """指定した画像 ID をステージングへ追加する (上限・重複排除を適用)。

        変更があった場合のみ staged_images_changed を発行する。

        Args:
            image_ids: 追加する画像 ID リスト。
        """
        if self._dataset_state_manager is None:
            logger.warning("DatasetStateManager not set in StagingStateManager")
            return

        added_count = 0
        for image_id in image_ids:
            if len(self._staged_images) >= self.MAX_STAGING_IMAGES:
                logger.warning(f"Staging limit reached ({self.MAX_STAGING_IMAGES}), cannot add more images")
                break
            if image_id in self._staged_images:
                continue
            image_metadata = self._dataset_state_manager.get_image_by_id(image_id)
            if image_metadata:
                stored_path = image_metadata.get("stored_image_path", "") or ""
                filename = Path(stored_path).name if stored_path else f"ID:{image_id}"
                self._staged_images[image_id] = (filename, stored_path)
                added_count += 1

        if added_count == 0:
            return
        logger.info(f"Added {added_count} images to staging (total: {len(self._staged_images)})")
        self.staged_images_changed.emit(self.get_image_ids())

    def add_selected_images(self) -> None:
        """DatasetStateManager.selected_image_ids をステージングへ追加する。"""
        if self._dataset_state_manager is None:
            logger.warning("DatasetStateManager not set in StagingStateManager")
            return
        selected_ids = self._dataset_state_manager.selected_image_ids
        if not selected_ids:
            logger.info("No images selected")
            return
        self.add_image_ids(selected_ids)

    def remove_image_ids(self, image_ids: list[int]) -> None:
        """指定した画像 ID のみをステージングから除外する (Issue #571)。

        変更があった場合のみ staged_images_changed を発行する。

        Args:
            image_ids: 除外する画像 ID リスト。
        """
        removed = False
        for image_id in image_ids:
            if image_id in self._staged_images:
                del self._staged_images[image_id]
                removed = True
        if not removed:
            return
        self.staged_images_changed.emit(self.get_image_ids())

    def clear(self) -> None:
        """ステージングを全削除し、staging_cleared と staged_images_changed([]) を発行する。"""
        self._staged_images.clear()
        logger.info("Staging list cleared")
        self.staging_cleared.emit()
        self.staged_images_changed.emit([])

    def get_image_ids(self) -> list[int]:
        """ステージング中の画像 ID リスト (追加順) を返す。"""
        return list(self._staged_images.keys())

    def count(self) -> int:
        """ステージング中の画像数を返す。"""
        return len(self._staged_images)

    def get_staged_items(self) -> "OrderedDict[int, tuple[str, str]]":
        """ステージング中の画像メタデータ ``{image_id: (filename, stored_path)}`` を返す。"""
        return self._staged_images
