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

        接続経路の詳細をログに記録し、問題診断を可能にする。
        DatasetStateManagerのインスタンス一致を確認する。

        Args:
            main_window: MainWindowインスタンス
            dataset_state_manager: DatasetStateManager（Noneも可）
        """
        logger.info("🔧 setup_selected_image_details() 呼び出し開始")

        # 属性存在確認
        if not hasattr(main_window, "selectedImageDetailsWidget"):
            logger.error("❌ selectedImageDetailsWidget 属性が存在しません")
            return

        if not main_window.selectedImageDetailsWidget:
            logger.error("❌ selectedImageDetailsWidget が None です")
            return

        # インスタンス確認
        widget = main_window.selectedImageDetailsWidget
        logger.info(f"🔍 selectedImageDetailsWidget インスタンス確認: {id(widget)}")

        # エイリアス設定
        main_window.selected_image_details_widget = widget
        logger.info(f"📝 エイリアス設定完了: selected_image_details_widget = {id(widget)}")

        # DatasetStateManager確認とシグナル接続
        if dataset_state_manager:
            logger.info(f"🔌 DatasetStateManager 渡されたインスタンス: {id(dataset_state_manager)}")
            logger.info(f"🔌 DatasetStateManager type: {type(dataset_state_manager)}")

            # MainWindow.dataset_state_managerとの一致確認
            if hasattr(main_window, "dataset_state_manager"):
                main_window_dsm_id = id(main_window.dataset_state_manager)
                logger.info(f"🔍 MainWindow.dataset_state_manager: {main_window_dsm_id}")

                if dataset_state_manager is not main_window.dataset_state_manager:
                    logger.error(
                        f"❌ DatasetStateManager インスタンス不一致！ "
                        f"渡された: {id(dataset_state_manager)}, "
                        f"MainWindow: {main_window_dsm_id}"
                    )
                else:
                    logger.info("✅ DatasetStateManager インスタンス一致確認完了")

            widget.connect_to_data_signals(dataset_state_manager)
            logger.info("✅ シグナル接続処理完了")
        else:
            logger.warning("⚠️ DatasetStateManager が None - 接続スキップ")

        logger.info("✅ SelectedImageDetailsWidget設定完了")

    @staticmethod
    def setup_splitter(main_window: Any) -> None:
        """スプリッター初期化（Qt標準機能使用）

        Args:
            main_window: MainWindowインスタンス
        """
        if hasattr(main_window, "splitterMainWorkArea") and main_window.splitterMainWorkArea:
            # 初期サイズ設定（左: 216px, 中央: 504px, 右: 480px）- 右パネル（詳細）を広めに
            main_window.splitterMainWorkArea.setSizes([216, 504, 480])

            # ストレッチファクター設定（左:18%, 中央:42%, 右:40%）
            main_window.splitterMainWorkArea.setStretchFactor(0, 18)  # 左パネル
            main_window.splitterMainWorkArea.setStretchFactor(1, 42)  # 中央パネル（サムネイル）
            main_window.splitterMainWorkArea.setStretchFactor(2, 40)  # 右パネル（プレビュー＋詳細）

            logger.info("✅ スプリッター初期化完了（Qt標準機能使用）")

        # 右カラム内のプレビュー/詳細スプリッター
        if hasattr(main_window, "splitterPreviewDetails") and main_window.splitterPreviewDetails:
            # 上:プレビュー、下:詳細（初期55/45）編集パネルのスペースを広めに確保
            main_window.splitterPreviewDetails.setSizes([550, 450])
            main_window.splitterPreviewDetails.setStretchFactor(0, 1)
            main_window.splitterPreviewDetails.setStretchFactor(1, 1)
            logger.info("✅ splitterPreviewDetails 初期化完了（プレビュー/詳細比率55/45）")

    @staticmethod
    def setup_batch_tag_tab_widgets(main_window: Any) -> None:
        """バッチタグタブウィジェット統合

        既存のBatchTagAddWidgetを新しいバッチタグタブに再配置し、
        AnnotationDataDisplayWidgetを追加する。

        Args:
            main_window: MainWindowインスタンス

        重要:
            - BatchTagAddWidgetは新規作成せず、既存インスタンスを移動
            - AnnotationDataDisplayWidgetは新規作成してバッチタグタブに追加
            - 3ステップ再親子化: removeWidget → setParent → addWidget
            - 再呼び出し時は既存ウィジェットを再利用（重複作成防止）
        """
        from ..widgets.annotation_data_display_widget import AnnotationDataDisplayWidget

        logger.info("🔧 setup_batch_tag_tab_widgets() 開始")

        # tabWidgetMainMode存在確認
        if not hasattr(main_window, "tabWidgetMainMode") or not main_window.tabWidgetMainMode:
            logger.error("❌ tabWidgetMainMode が存在しません")
            return

        # バッチタグタブ取得（タブインデックス1）
        batch_tag_tab = main_window.tabWidgetMainMode.widget(1)
        if not batch_tag_tab:
            logger.error("❌ バッチタグタブ（インデックス1）が存在しません")
            return

        # 右カラム（操作パネル）取得
        right_column = batch_tag_tab.findChild(object, "groupBoxBatchOperations")
        if not right_column:
            logger.error("❌ groupBoxBatchOperations が見つかりません")
            return

        # BatchTagAddWidget取得と再配置
        if hasattr(main_window, "batchTagAddWidget") and main_window.batchTagAddWidget:
            batch_tag_widget = main_window.batchTagAddWidget

            # 既にバッチタグタブに配置済みの場合はスキップ
            current_parent = batch_tag_widget.parent()
            if current_parent == right_column:
                logger.debug("BatchTagAddWidget は既にバッチタグタブに配置済み、スキップ")
            else:
                logger.info(f"🔍 BatchTagAddWidget インスタンス: {id(batch_tag_widget)}")

                # 元の親から取り外し
                if current_parent and hasattr(current_parent, "layout") and current_parent.layout():
                    old_layout = current_parent.layout()
                    old_layout.removeWidget(batch_tag_widget)
                    logger.debug(f"📤 BatchTagAddWidget を元の親 {current_parent.objectName()} から取り外し")

                # プレースホルダーを削除
                placeholder = right_column.findChild(object, "batchTagWidgetPlaceholder")
                if placeholder:
                    right_column.layout().removeWidget(placeholder)
                    placeholder.setParent(None)
                    placeholder.deleteLater()
                    logger.debug("🗑️ batchTagWidgetPlaceholder を削除")

                # 新しい親に再配置（3ステップ）
                batch_tag_widget.setParent(right_column)
                right_column.layout().insertWidget(0, batch_tag_widget)  # 最上部に配置
                logger.info("✅ BatchTagAddWidget を新しいバッチタグタブに再配置完了")
        else:
            logger.warning("⚠️ batchTagAddWidget が存在しません")

        # AnnotationDataDisplayWidget追加（タグテーブル）
        # 既に作成済みの場合はスキップ（重複作成防止）
        # Note: 早期returnではなく条件分岐で制御（BatchTagAddWidget処理に影響を与えないため）
        if hasattr(main_window, "batchTagAnnotationDisplay") and main_window.batchTagAnnotationDisplay:
            logger.debug("AnnotationDataDisplayWidget は既に作成済み、スキップ")
        else:
            annotation_placeholder = right_column.findChild(object, "annotationDisplayPlaceholder")
            if annotation_placeholder:
                right_column.layout().removeWidget(annotation_placeholder)
                annotation_placeholder.setParent(None)
                annotation_placeholder.deleteLater()
                logger.debug("🗑️ annotationDisplayPlaceholder を削除")

            # AnnotationDataDisplayWidget新規作成
            annotation_display = AnnotationDataDisplayWidget()
            annotation_display.setObjectName("batchTagAnnotationDisplay")
            annotation_display.setParent(right_column)
            right_column.layout().addWidget(annotation_display)

            # MainWindowに参照を保持
            main_window.batchTagAnnotationDisplay = annotation_display
            logger.info("✅ AnnotationDataDisplayWidget を新しいバッチタグタブに追加完了")

        logger.info("✅ setup_batch_tag_tab_widgets() 完了")

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
