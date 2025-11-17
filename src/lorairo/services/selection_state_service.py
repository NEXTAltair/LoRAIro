"""画像選択状態管理サービス

DatasetStateManagerのラッパーサービス。
複雑な選択ロジック（フォールバック戦略）を隠蔽し、シンプルなAPIを提供。

Phase 2.3で作成。MainWindow.start_annotation()から画像選択ロジック（45行）を抽出。
"""

from typing import Protocol, runtime_checkable

from loguru import logger

from lorairo.database.db_repository import ImageRepository
from lorairo.gui.state.dataset_state import DatasetStateManager


@runtime_checkable
class StateConnectableWidget(Protocol):
    """状態管理接続可能なウィジェットのプロトコル

    MainWindowで状態管理接続を検証する際に使用。
    最低限のインターフェース要件を定義。
    """

    def __repr__(self) -> str:
        """ウィジェット名を返す（ログ出力用）"""
        ...


class SelectionStateService:
    """画像選択状態管理サービス

    DatasetStateManagerから画像選択状態を取得し、
    アノテーション処理などで使いやすい形式で提供する。

    フォールバック戦略:
    1. 選択画像（selected_image_ids）
    2. フィルタ済み画像（filtered_images）- 表示中の全画像
    """

    def __init__(
        self,
        dataset_state_manager: DatasetStateManager | None,
        db_repository: ImageRepository | None = None,
    ):
        """初期化

        Args:
            dataset_state_manager: データセット状態管理
            db_repository: データベースリポジトリ（将来の拡張用、現在未使用）
        """
        self.dataset_state_manager = dataset_state_manager
        self.db_repository = db_repository

    def get_selected_images_for_annotation(self) -> list[dict]:
        """アノテーション対象画像取得

        フォールバック戦略で画像を取得:
        1. 選択画像（selected_image_ids）
        2. フィルタ済み画像（filtered_images）- 表示中の全画像

        Returns:
            ImageRecordリスト（dict形式）
            各要素は {"id": int, "stored_image_path": str, ...} を含む

        Raises:
            ValueError: DatasetStateManagerが未設定、または画像が選択されていない場合
        """
        if not self.dataset_state_manager:
            raise ValueError("DatasetStateManagerが設定されていません。")

        # 第1優先: selected_image_ids から取得
        selected_image_ids = self.dataset_state_manager.selected_image_ids
        if selected_image_ids:
            logger.debug(
                f"DatasetStateManager.selected_image_idsから選択画像を取得: {len(selected_image_ids)}件"
            )
            return self._get_images_by_ids(selected_image_ids)

        # 第2優先（最終）: filtered_images（表示中の全画像）から取得
        if self.dataset_state_manager.has_filtered_images():
            filtered_images = self.dataset_state_manager.filtered_images
            logger.info(f"画像未選択のため、表示中の全画像を使用: {len(filtered_images)}件")
            return self._extract_valid_images(filtered_images)

        # 画像が見つからない
        raise ValueError(
            "アノテーション対象の画像が選択されていません。\n"
            "フィルタリング条件を設定して画像を表示するか、\n"
            "サムネイル表示で画像を選択してください。"
        )

    def get_selected_image_paths(self) -> list[str]:
        """選択画像のパスリスト取得（便利メソッド）

        Returns:
            画像パスのリスト

        Raises:
            ValueError: 画像が選択されていない場合
        """
        images = self.get_selected_images_for_annotation()
        paths = []
        for image in images:
            path = image.get("stored_image_path")
            if path:
                paths.append(str(path))
        return paths

    def _get_images_by_ids(self, image_ids: list[int]) -> list[dict]:
        """画像IDリストから画像データを取得

        Args:
            image_ids: 画像IDリスト

        Returns:
            画像データリスト（stored_image_pathを持つもののみ）
        """
        images = []
        for image_id in image_ids:
            image_data = self.dataset_state_manager.get_image_by_id(image_id)
            if image_data and image_data.get("stored_image_path"):
                images.append(image_data)
            elif not image_data:
                logger.warning(f"画像ID {image_id} のデータが取得できませんでした（スキップ）")
            else:
                logger.warning(f"画像ID {image_id} に stored_image_path がありません（スキップ）")
        return images

    def _extract_valid_images(self, images: list[dict]) -> list[dict]:
        """画像リストから有効な画像を抽出

        Args:
            images: 画像データリスト

        Returns:
            id と stored_image_path を持つ画像のみ
        """
        valid_images = []
        for image in images:
            if image.get("id") is not None and image.get("stored_image_path"):
                valid_images.append(image)
            else:
                logger.warning(f"無効な画像データをスキップ: {image.get('id', 'N/A')}")
        return valid_images

    def verify_state_management_connections(
        self,
        thumbnail_selector: StateConnectableWidget | None,
        image_preview_widget: StateConnectableWidget | None,
        selected_image_details_widget: StateConnectableWidget | None,
    ) -> None:
        """状態管理接続の検証

        MainWindow初期化時に呼び出され、UI コンポーネントと SelectionStateService の
        接続状態を検証する。接続が欠けている場合はログで警告を出す。

        Args:
            thumbnail_selector: ThumbnailSelectorWidget（最重要）
            image_preview_widget: ImagePreviewWidget
            selected_image_details_widget: SelectedImageDetailsWidget
        """
        if not self.dataset_state_manager:
            logger.info("DatasetStateManager未初期化 - 状態管理接続検証をスキップ")
            return

        # 各ウィジェットの接続状態を検証
        widgets_status = {
            "thumbnail_selector": thumbnail_selector is not None,
            "image_preview_widget": image_preview_widget is not None,
            "selected_image_details_widget": selected_image_details_widget is not None,
        }

        connected_count = sum(widgets_status.values())
        logger.info(f"状態管理接続検証: {connected_count}/3 ウィジェット接続済み")

        # 各ウィジェットの状態をログ出力
        for widget_name, is_connected in widgets_status.items():
            status = "✅" if is_connected else "⚠️"
            logger.debug(f"  {status} {widget_name}: {'接続済み' if is_connected else '未接続'}")

        # thumbnail_selector が無い場合は DatasetStateManager 連携が機能しないため警告
        if not thumbnail_selector:
            logger.warning(
                "thumbnail_selector が未設定です。DatasetStateManager との状態同期が機能しません。"
            )
