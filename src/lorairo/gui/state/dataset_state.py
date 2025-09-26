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
        self._all_images: list[dict[str, Any]] = []
        self._filtered_images: list[dict[str, Any]] = []
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
    def all_images(self) -> list[dict[str, Any]]:
        return self._all_images.copy()

    @property
    def filtered_images(self) -> list[dict[str, Any]]:
        return self._filtered_images.copy()

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
        """データセットの全画像リストを設定"""
        self._all_images = images.copy()
        self._filtered_images = images.copy()  # 初期状態はフィルターなし

        logger.info(f"データセット画像読み込み: {len(images)}件")
        self.images_loaded.emit(self._all_images)
        self.images_filtered.emit(self._filtered_images)
        self.dataset_loaded.emit(len(images))

        # 選択状態をクリア
        self.clear_selection()

    def clear_dataset(self) -> None:
        """データセット状態をクリア"""
        self._dataset_path = None
        self._all_images = []
        self._filtered_images = []
        self._filter_conditions = {}

        self.clear_selection()
        self._current_image_id = None
        self.filter_cleared.emit()
        logger.info("データセット状態をクリアしました")

    # === Filter Management ===

    def apply_filter_results(
        self, filtered_images: list[dict[str, Any]], filter_conditions: dict[str, Any]
    ) -> None:
        """
        データベースからのフィルター結果を適用し、状態を更新します。

        このメソッドは検索・フィルター処理の結果を受け取り、DatasetStateManagerの
        内部状態を更新します。フィルター適用後、関連するシグナルを発行して
        UI コンポーネントに変更を通知します。

        Args:
            filtered_images (list[dict[str, Any]]): フィルター処理後の画像メタデータリスト。
                各辞書は以下のキーを含む必要があります:
                - "id": 画像ID (int)
                - "stored_image_path": 画像ファイルパス (str)
                - その他の画像メタデータ (width, height, etc.)

            filter_conditions (dict[str, Any]): 適用されたフィルター条件。
                以下のようなキーを含むことがあります:
                - "tags": タグフィルター条件 (list[str])
                - "caption": キャプション検索条件 (str)
                - "resolution": 解像度フィルター条件 (int)
                - "use_and": AND/OR検索ロジック (bool)
                - "date_range": 日付範囲フィルター (tuple)
                - "include_untagged": 未タグ画像を含むか (bool)

        Returns:
            None

        Side Effects:
            - 内部状態 (_filtered_images, _filter_conditions) を更新
            - filter_applied シグナルを発行 (フィルター条件を通知)
            - images_filtered シグナルを発行 (フィルター済み画像リストを通知)
            - 現在選択中の画像がフィルター結果に含まれない場合、選択をクリア

        Example:
            >>> filtered_images = [
            ...     {"id": 1, "stored_image_path": "/path/to/image1.jpg", "width": 1024, "height": 768},
            ...     {"id": 2, "stored_image_path": "/path/to/image2.jpg", "width": 800, "height": 600}
            ... ]
            >>> filter_conditions = {
            ...     "tags": ["landscape", "nature"],
            ...     "resolution": 1024,
            ...     "use_and": True
            ... }
            >>> state_manager.apply_filter_results(filtered_images, filter_conditions)
        """
        self._filter_conditions = filter_conditions.copy()
        self._filtered_images = filtered_images.copy()

        logger.info(f"フィルター結果適用: {len(self._all_images)}件 → {len(self._filtered_images)}件")

        self.filter_applied.emit(filter_conditions)
        self.images_filtered.emit(self._filtered_images)

        # 現在の選択が有効でない場合はクリア
        if self._current_image_id:
            current_valid = any(img.get("id") == self._current_image_id for img in self._filtered_images)
            if not current_valid:
                self.clear_current_image()

    def update_from_search_results(self, search_results: list[dict[str, Any]]) -> None:
        """
        検索結果による完全データ更新（クリーンなデータフロー）

        従来のapply_filter_results()とは異なり、検索結果でマスターデータを完全置換し、
        単一データソースとしての信頼性を確保します。

        Args:
            search_results: 検索結果の画像メタデータリスト
                各辞書は以下のキーを含む必要があります:
                - "id": 画像ID (int)
                - "stored_image_path": 画像ファイルパス (str)
                - その他の画像メタデータ (width, height, etc.)

        Side Effects:
            - _all_images と _filtered_images を同時更新（同期保証）
            - images_loaded と images_filtered シグナルを発行
            - 現在選択中の画像が結果に含まれない場合、選択をクリア
        """
        logger.info(f"検索結果によるデータ完全更新: {len(search_results)}件")

        # 完全データ置換（Single Source of Truth）
        self._all_images = search_results.copy()
        self._filtered_images = search_results.copy()

        # フィルター条件はクリア（検索結果が新しい基準）
        self._filter_conditions = {}

        # シグナル発行で UI コンポーネントに通知
        self.images_loaded.emit(self._all_images)
        self.images_filtered.emit(self._filtered_images)

        # 現在の選択状態を検証・クリア
        if self._current_image_id:
            current_valid = any(img.get("id") == self._current_image_id for img in self._all_images)
            if not current_valid:
                logger.debug(
                    f"現在の画像ID {self._current_image_id} が検索結果に含まれていないため選択をクリア"
                )
                self.clear_current_image()

        logger.debug(
            f"データ同期完了: all_images={len(self._all_images)}, filtered_images={len(self._filtered_images)}"
        )

    def clear_filter(self) -> None:
        """フィルターをクリア"""
        self._filter_conditions = {}
        self._filtered_images = self._all_images.copy()

        self.filter_cleared.emit()
        self.images_filtered.emit(self._filtered_images)
        logger.info("フィルターをクリアしました")

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
        """現在の画像IDを設定"""
        if self._current_image_id != image_id:
            self._current_image_id = image_id

            # 後方互換性のためIDシグナルを維持
            self.current_image_changed.emit(image_id)

            # 新しいデータシグナルで完全な画像メタデータを送信
            image_data = self.get_image_by_id(image_id)
            if image_data:
                self.current_image_data_changed.emit(image_data)
                logger.info(f"✅ 画像選択成功: ID {image_id} - current_image_data_changed シグナル発行")
            else:
                # デバッグ情報を詳細化
                state_summary = self.get_state_summary()
                logger.warning(
                    f"画像データ取得失敗: ID {image_id} | "
                    f"all_images={state_summary['total_images']}, "
                    f"filtered_images={state_summary['filtered_images']} | "
                    f"検索対象: _all_images 優先検索に変更が必要な可能性"
                )

                # フィルター済み画像からも検索を試行
                filtered_image_data = self._get_image_from_filtered(image_id)
                if filtered_image_data:
                    logger.info(f"フィルター済み画像で発見: ID {image_id} - データを送信")
                    self.current_image_data_changed.emit(filtered_image_data)
                else:
                    # 空のデータでもシグナルを送信して一貫性を保つ
                    self.current_image_data_changed.emit({})

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

    def get_image_by_id(self, image_id: int) -> dict[str, Any] | None:
        """
        IDで画像メタデータを取得（統一データソース：all_images優先、filtered_imagesフォールバック）

        Args:
            image_id: 検索する画像ID

        Returns:
            画像メタデータ辞書、見つからない場合はNone
        """
        # 1. all_images から検索（メインデータソース）
        for img in self._all_images:
            if img.get("id") == image_id:
                logger.debug(
                    f"画像ID {image_id} をall_imagesで発見（正常な状態）- path: {img.get('stored_image_path', 'N/A')}"
                )
                return img

        # 2. filtered_images からフォールバック検索
        for img in self._filtered_images:
            if img.get("id") == image_id:
                logger.warning(
                    f"画像ID {image_id} をfiltered_imagesで発見（all_imagesとの同期問題あり）- path: {img.get('stored_image_path', 'N/A')}"
                )
                return img

        # デバッグ情報の詳細ログ
        logger.debug(
            f"画像ID {image_id} が見つかりません。"
            f"all_images: {len(self._all_images)}件, "
            f"filtered_images: {len(self._filtered_images)}件, "
            f"IDサンプル: {[img.get('id') for img in (self._all_images or self._filtered_images)[:3]]}..."
        )
        return None

    def _get_image_from_filtered(self, image_id: int) -> dict[str, Any] | None:
        """フィルター済み画像からの検索（デバッグ用）"""
        for img in self._filtered_images:
            if img.get("id") == image_id:
                return img
        return None

    def get_current_image_data(self) -> dict[str, Any] | None:
        """現在選択中の画像データを取得"""
        if self._current_image_id:
            return self.get_image_by_id(self._current_image_id)
        return None

    def has_images(self) -> bool:
        """画像が読み込まれているかチェック"""
        return len(self._all_images) > 0

    def has_filtered_images(self) -> bool:
        """フィルター済み画像があるかチェック"""
        return len(self._filtered_images) > 0

    def is_image_selected(self, image_id: int) -> bool:
        """指定画像IDが選択されているかチェック"""
        return image_id in self._selected_image_ids

    # === Debug Methods ===

    def get_state_summary(self) -> dict[str, Any]:
        """状態サマリーを取得（デバッグ用）"""
        return {
            "dataset_path": str(self._dataset_path) if self._dataset_path else None,
            "total_images": len(self._all_images),
            "filtered_images": len(self._filtered_images),
            "selected_images": len(self._selected_image_ids),
            "current_image_id": self._current_image_id,
            "has_filter": bool(self._filter_conditions),
            "thumbnail_size": self._thumbnail_size,
            "layout_mode": self._layout_mode,
        }
