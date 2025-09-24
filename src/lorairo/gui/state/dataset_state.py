# src/lorairo/gui/state/dataset_state.py

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from ...utils.log import logger


class DatasetStateManager(QObject):
    """
    全Widget間で共有される単一状態管理システム。
    データセット情報、画像リスト、選択状態などを一元管理。
    """

    # === コアデータセット状態シグナル ===
    dataset_changed = Signal(str)  # dataset_path
    dataset_loaded = Signal(int)  # total_image_count
    dataset_loading_started = Signal()
    dataset_loading_failed = Signal(str)  # error_message

    # === 画像リスト・フィルター状態シグナル ===
    images_filtered = Signal(list)  # List[Dict[str, Any]] - filtered image metadata
    images_loaded = Signal(list)  # List[Dict[str, Any]] - all image metadata
    filter_applied = Signal(dict)  # filter_conditions
    filter_cleared = Signal()

    # === 選択状態シグナル ===
    selection_changed = Signal(list)  # List[int] - selected image IDs
    current_image_changed = Signal(int)  # current_image_id
    current_image_data_changed = Signal(dict)  # current_image_data (complete metadata)
    current_image_cleared = Signal()

    # === UI状態シグナル ===
    ui_state_changed = Signal(str, object)  # state_key, state_value
    thumbnail_size_changed = Signal(int)  # thumbnail_size
    layout_mode_changed = Signal(str)  # layout_mode

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        # === プライベート状態 ===
        self._dataset_path: Path | None = None
        self._selected_image_ids: list[int] = []
        self._current_image_id: int | None = None
        self._filter_conditions: dict[str, Any] = {}

        # === UI状態 ===
        self._thumbnail_size: int = 150
        self._layout_mode: str = "grid"  # "grid" | "list"
        self._ui_state: dict[str, Any] = {}

        logger.debug("DatasetStateManager initialized")

    # === Public Properties (Read-Only) ===

    @property
    def dataset_path(self) -> Path | None:
        return self._dataset_path



    @property
    def selected_image_ids(self) -> list[int]:
        return self._selected_image_ids.copy()

    @property
    def current_image_id(self) -> int | None:
        return self._current_image_id

    @property
    def filter_conditions(self) -> dict[str, Any]:
        return self._filter_conditions.copy()

    @property
    def thumbnail_size(self) -> int:
        return self._thumbnail_size

    @property
    def layout_mode(self) -> str:
        return self._layout_mode

    # === Dataset Management ===

    def set_dataset_path(self, dataset_path: Path) -> None:
        """データセットパスを設定"""
        if self._dataset_path != dataset_path:
            self._dataset_path = dataset_path
            logger.info(f"データセットパス変更: {dataset_path}")
            self.dataset_changed.emit(str(dataset_path))

    def set_dataset_images(self, images: list[dict[str, Any]]) -> None:
        """
        データセットの全画像リスト設定（Phase 3: シグナル発信のみ）
        
        キャッシュ機能を完全削除し、シグナル発信のみに責任を集中。
        実際のデータ管理はThumbnailSelectorWidgetで行う。
        
        Args:
            images: 画像メタデータリスト（シグナル発信用）
        """
        logger.info(f"データセット画像設定: {len(images)}件 - シグナル発信のみ")
        
        # シグナル発信（UI状態管理のみ）
        self.images_loaded.emit(images)
        self.images_filtered.emit(images)  # 初期状態はフィルターなし
        self.dataset_loaded.emit(len(images))
        
        # 選択状態をクリア
        self.clear_selection()

    def clear_dataset(self) -> None:
        """
        データセット状態をクリア（Phase 3: UI状態管理のみ）
        
        データキャッシュ機能を完全削除し、UI状態管理のみに責任を集中。
        実際のデータクリアはThumbnailSelectorWidgetで行う。
        """
        self._dataset_path = None
        self._filter_conditions = {}
        
        # 選択状態をクリア（UI状態管理）
        self.clear_selection()
        self._current_image_id = None
        
        # シグナル発信（UI状態管理のみ）
        self.filter_cleared.emit()
        
        logger.info("データセット状態をクリア - UI状態管理のみ")

    # === Filter Management ===

    def apply_filter_results(
        self, filtered_images: list[dict[str, Any]], filter_conditions: dict[str, Any]
    ) -> None:
        """
        フィルター結果適用（Phase 3: シグナル発信のみ）
        
        データキャッシュ機能を完全削除し、シグナル発信のみに責任を集中。
        実際のデータ管理はThumbnailSelectorWidgetで行う。
        
        Args:
            filtered_images: フィルター済み画像リスト（シグナル発信用）
            filter_conditions: フィルター条件（シグナル発信用）
        """
        self._filter_conditions = filter_conditions.copy()
        
        logger.info(f"フィルター結果適用: {len(filtered_images)}件 - シグナル発信のみ")
        
        # シグナル発信（UI状態管理のみ）
        self.filter_applied.emit(filter_conditions)
        self.images_filtered.emit(filtered_images)
        
        # 選択状態をクリア（フィルター適用時は通常選択をリセット）
        self.clear_selection()

    def update_from_search_results(self, search_results: list[dict[str, Any]]) -> None:
        """
        検索結果による完全データ更新（Phase 3: シグナル発信のみ）
        
        データキャッシュ機能を完全削除し、シグナル発信のみに責任を集中。
        実際のデータ管理はThumbnailSelectorWidgetで行う。
        
        Args:
            search_results: 検索結果の画像メタデータリスト（シグナル発信用）
        """
        logger.info(f"検索結果による完全データ更新: {len(search_results)}件 - シグナル発信のみ")
        
        # フィルター条件はクリア（検索結果が新しい基準）
        self._filter_conditions = {}
        
        # シグナル発信（UI状態管理のみ）
        self.images_loaded.emit(search_results)
        self.images_filtered.emit(search_results)  # 検索結果は初期状態でフィルターなし
        
        # 選択状態をクリア（新しい検索結果では従前の選択は無効）
        self.clear_selection()

    def clear_filter(self) -> None:
        """
        フィルターをクリア（Phase 3: シグナル発信のみ）
        
        データキャッシュ機能を完全削除し、シグナル発信のみに責任を集中。
        実際のフィルター状態管理はThumbnailSelectorWidgetで行う。
        """
        self._filter_conditions = {}
        
        logger.info("フィルターをクリア - シグナル発信のみ")
        
        # シグナル発信（UI状態管理のみ）
        self.filter_cleared.emit()

    # === Selection Management ===

    def set_selected_images(self, image_ids: list[int]) -> None:
        """選択画像IDリストを設定"""
        if self._selected_image_ids != image_ids:
            self._selected_image_ids = image_ids.copy()
            self.selection_changed.emit(self._selected_image_ids)
            logger.debug(f"画像選択変更: {len(image_ids)}件選択")

    def add_to_selection(self, image_id: int) -> None:
        """選択に画像IDを追加"""
        if image_id not in self._selected_image_ids:
            self._selected_image_ids.append(image_id)
            self.selection_changed.emit(self._selected_image_ids)

    def remove_from_selection(self, image_id: int) -> None:
        """選択から画像IDを削除"""
        if image_id in self._selected_image_ids:
            self._selected_image_ids.remove(image_id)
            self.selection_changed.emit(self._selected_image_ids)

    def toggle_selection(self, image_id: int) -> None:
        """画像IDの選択状態をトグル"""
        if image_id in self._selected_image_ids:
            self.remove_from_selection(image_id)
        else:
            self.add_to_selection(image_id)

    def clear_selection(self) -> None:
        """全選択をクリア"""
        if self._selected_image_ids:
            self._selected_image_ids = []
            self.selection_changed.emit(self._selected_image_ids)

    def set_current_image(self, image_id: int) -> None:
        """
        現在の画像IDを設定（Phase 3: シンプル版）
        
        データキャッシュ機能削除により、IDシグナル発信のみ実行。
        実際のメタデータ管理はThumbnailSelectorWidgetで行う。
        """
        if self._current_image_id != image_id:
            self._current_image_id = image_id
            
            # UI状態管理のみ - IDシグナル発信
            self.current_image_changed.emit(image_id)
            
            logger.debug(f"現在画像ID設定: {image_id} - UI状態管理のみ")

    def clear_current_image(self) -> None:
        """現在の画像選択をクリア"""
        if self._current_image_id is not None:
            self._current_image_id = None
            self.current_image_cleared.emit()

    # === UI State Management ===

    def set_thumbnail_size(self, size: int) -> None:
        """サムネイルサイズを設定"""
        if self._thumbnail_size != size:
            self._thumbnail_size = size
            self.thumbnail_size_changed.emit(size)

    def set_layout_mode(self, mode: str) -> None:
        """レイアウトモードを設定"""
        if mode in ["grid", "list"] and self._layout_mode != mode:
            self._layout_mode = mode
            self.layout_mode_changed.emit(mode)

    def set_ui_state(self, key: str, value: Any) -> None:
        """任意のUI状態を設定"""
        if self._ui_state.get(key) != value:
            self._ui_state[key] = value
            self.ui_state_changed.emit(key, value)

    def get_ui_state(self, key: str, default: Any = None) -> Any:
        """UI状態を取得"""
        return self._ui_state.get(key, default)

    # === Utility Methods ===






    def is_image_selected(self, image_id: int) -> bool:
        """指定画像IDが選択されているかチェック"""
        return image_id in self._selected_image_ids

    # === Debug Methods ===

    def get_state_summary(self) -> dict[str, Any]:
        """状態サマリーを取得（デバッグ用）"""
        return {
            "dataset_path": str(self._dataset_path) if self._dataset_path else None,
            "selected_images": len(self._selected_image_ids),
            "current_image_id": self._current_image_id,
            "has_filter": bool(self._filter_conditions),
            "thumbnail_size": self._thumbnail_size,
            "layout_mode": self._layout_mode,
        }
