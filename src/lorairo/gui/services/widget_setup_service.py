# src/lorairo/gui/services/widget_setup_service.py
"""Widget初期化設定Service

MainWindowの_setup_other_custom_widgets()から抽出。
各種カスタムウィジェットの初期化と状態管理接続を担当。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...utils.log import logger

if TYPE_CHECKING:
    from ...state.dataset_state import DatasetStateManager


class WidgetSetupService:
    """Widget初期化設定Service

    カスタムウィジェットの初期化、DatasetStateManager接続、
    スプリッター設定などを担当。
    """

    @staticmethod
    def setup_thumbnail_selector(
        main_window: Any, dataset_state_manager: DatasetStateManager | None
    ) -> None:
        """ThumbnailSelectorWidget設定

        Args:
            main_window: MainWindowインスタンス
            dataset_state_manager: DatasetStateManager（Noneも可）
        """
        if hasattr(main_window, "thumbnailSelectorWidget") and main_window.thumbnailSelectorWidget:
            main_window.thumbnail_selector = main_window.thumbnailSelectorWidget

            if dataset_state_manager:
                main_window.thumbnail_selector.set_dataset_state(dataset_state_manager)
                logger.info("✅ ThumbnailSelectorWidget DatasetStateManager接続完了")
            else:
                logger.warning(
                    "⚠️ DatasetStateManagerが初期化されていません - ThumbnailSelectorWidget接続をスキップ"
                )

            logger.info("✅ ThumbnailSelectorWidget設定完了")

    @staticmethod
    def setup_image_preview(main_window: Any, dataset_state_manager: DatasetStateManager | None) -> None:
        """ImagePreviewWidget設定

        Args:
            main_window: MainWindowインスタンス
            dataset_state_manager: DatasetStateManager（Noneも可）
        """
        if hasattr(main_window, "imagePreviewWidget") and main_window.imagePreviewWidget:
            main_window.image_preview_widget = main_window.imagePreviewWidget

            if dataset_state_manager:
                main_window.image_preview_widget.connect_to_data_signals(dataset_state_manager)
                logger.info("✅ ImagePreviewWidget データシグナル接続完了")
            else:
                logger.warning(
                    "⚠️ DatasetStateManagerが初期化されていません - ImagePreviewWidget接続をスキップ"
                )

            logger.info("✅ ImagePreviewWidget設定完了")

    @staticmethod
    def setup_selected_image_details(
        main_window: Any, dataset_state_manager: DatasetStateManager | None
    ) -> None:
        """SelectedImageDetailsWidget設定

        Args:
            main_window: MainWindowインスタンス
            dataset_state_manager: DatasetStateManager（Noneも可）
        """
        if hasattr(main_window, "selectedImageDetailsWidget") and main_window.selectedImageDetailsWidget:
            main_window.selected_image_details_widget = main_window.selectedImageDetailsWidget

            logger.info(f"🔍 SelectedImageDetailsWidget instance: {id(main_window.selected_image_details_widget)}")

            if dataset_state_manager:
                main_window.selected_image_details_widget.connect_to_data_signals(dataset_state_manager)
                logger.info(f"✅ SelectedImageDetailsWidget データシグナル接続完了 (instance: {id(main_window.selected_image_details_widget)})")
            else:
                logger.warning(
                    "⚠️ DatasetStateManagerが初期化されていません - SelectedImageDetailsWidget接続をスキップ"
                )

            logger.info("✅ SelectedImageDetailsWidget設定完了")

    @staticmethod
    def setup_splitter(main_window: Any) -> None:
        """スプリッター初期化（Qt標準機能使用）

        Args:
            main_window: MainWindowインスタンス
        """
        if hasattr(main_window, "splitterMainWorkArea") and main_window.splitterMainWorkArea:
            # 初期サイズ設定（左: 280px, 中央: 770px, 右: 350px）
            main_window.splitterMainWorkArea.setSizes([280, 770, 350])

            # ストレッチファクター設定（比率: 20%, 55%, 25%）
            main_window.splitterMainWorkArea.setStretchFactor(0, 20)  # 左パネル
            main_window.splitterMainWorkArea.setStretchFactor(1, 55)  # 中央パネル（サムネイル）
            main_window.splitterMainWorkArea.setStretchFactor(2, 25)  # 右パネル

            logger.info("✅ スプリッター初期化完了（Qt標準機能使用）")

    @classmethod
    def setup_all_widgets(cls, main_window: Any, dataset_state_manager: DatasetStateManager | None) -> None:
        """全カスタムウィジェット設定（統合メソッド）

        Args:
            main_window: MainWindowインスタンス
            dataset_state_manager: DatasetStateManager（Noneも可）
        """
        cls.setup_thumbnail_selector(main_window, dataset_state_manager)
        cls.setup_image_preview(main_window, dataset_state_manager)
        cls.setup_selected_image_details(main_window, dataset_state_manager)
        cls.setup_splitter(main_window)
