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

        # バッチタグタブのメインスプリッター（左:ステージング一覧、右:操作パネル）
        if hasattr(main_window, "splitterBatchTagMain") and main_window.splitterBatchTagMain:
            # 初期サイズ設定（左: 50%, 右: 50%）
            main_window.splitterBatchTagMain.setSizes([560, 560])
            main_window.splitterBatchTagMain.setStretchFactor(0, 5)  # 左: ステージング一覧
            main_window.splitterBatchTagMain.setStretchFactor(1, 5)  # 右: 操作パネル
            logger.info("✅ splitterBatchTagMain 初期化完了（ステージング/操作比率50/50）")

        # バッチタグ操作パネル内のスプリッター（タグ追加/表示/アノテーション）
        if hasattr(main_window, "splitterBatchTagOperations") and main_window.splitterBatchTagOperations:
            # 初期サイズ設定（上: 40%, 下: 60%）- タブ(操作) + 表示
            main_window.splitterBatchTagOperations.setSizes([280, 420])
            main_window.splitterBatchTagOperations.setStretchFactor(0, 4)  # 操作タブ
            main_window.splitterBatchTagOperations.setStretchFactor(1, 6)  # AnnotationDisplay
            logger.info("✅ splitterBatchTagOperations 初期化完了（操作タブ/表示比率4/6）")

    @staticmethod
    def setup_batch_tag_tab_widgets(main_window: Any) -> None:
        """バッチタグタブウィジェット統合

        バッチタグタブにBatchTagAddWidget、AnnotationDataDisplayWidget、
        AnnotationFilterWidget、ModelSelectionWidgetを配置する。

        Args:
            main_window: MainWindowインスタンス
        """
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

        # バッチタグタブのメインスプリッター取得（左右2カラム）
        main_splitter = batch_tag_tab.findChild(object, "splitterBatchTagMain")
        if not main_splitter:
            logger.error("❌ splitterBatchTagMain が見つかりません")
            return

        # BatchTagAddWidget（左カラムのプレースホルダーを置換）
        WidgetSetupService._setup_batch_tag_add_widget(main_window, main_splitter)

        # タグ追加入力を右カラムのタブへ移動
        tag_input_placeholder = batch_tag_tab.findChild(object, "batchTagInputPlaceholder")
        if not tag_input_placeholder:
            logger.warning("⚠️ batchTagInputPlaceholder が見つかりません")
        else:
            batch_tag_widget = getattr(main_window, "batchTagAddWidget", None)
            if batch_tag_widget:
                batch_tag_widget.attach_tag_input_to(tag_input_placeholder)
            else:
                logger.warning("⚠️ BatchTagAddWidget が見つかりません")

        # 操作パネル内のスプリッター取得（右カラム）
        operations_splitter = batch_tag_tab.findChild(object, "splitterBatchTagOperations")
        if not operations_splitter:
            logger.error("❌ splitterBatchTagOperations が見つかりません")
            return

        # AnnotationDataDisplayWidget
        WidgetSetupService._setup_annotation_display_widget(main_window, operations_splitter)

        # アノテーショングループ内のウィジェット
        annotation_group = batch_tag_tab.findChild(object, "groupBoxAnnotation")
        if annotation_group:
            WidgetSetupService._setup_annotation_group_widgets(main_window, annotation_group)
        else:
            logger.warning("⚠️ groupBoxAnnotation が見つかりません")

        logger.info("✅ setup_batch_tag_tab_widgets() 完了")

    @staticmethod
    def _setup_batch_tag_add_widget(main_window: Any, splitter: Any) -> None:
        """BatchTagAddWidgetの設定（スプリッター内のプレースホルダーを置換）"""
        if hasattr(main_window, "batchTagAddWidget") and main_window.batchTagAddWidget:
            logger.debug("BatchTagAddWidget は既に作成済み、スキップ")
            return

        from ..widgets.batch_tag_add_widget import BatchTagAddWidget

        # プレースホルダーを取得
        placeholder = splitter.findChild(object, "batchTagWidgetPlaceholder")
        if not placeholder:
            logger.warning("⚠️ batchTagWidgetPlaceholder が見つかりません")
            return

        # BatchTagAddWidget新規作成してプレースホルダーを置換
        widget = BatchTagAddWidget()
        widget.setObjectName("batchTagAddWidget")
        index = splitter.indexOf(placeholder)
        if index != -1:
            splitter.replaceWidget(index, widget)
        else:
            parent = placeholder.parentWidget()
            if parent and parent.layout():
                parent.layout().replaceWidget(placeholder, widget)
                widget.setParent(parent)
            else:
                logger.warning("⚠️ batchTagWidgetPlaceholder の置換に失敗しました")
                return

        placeholder.deleteLater()
        logger.debug("🗑️ batchTagWidgetPlaceholder を置換")

        main_window.batchTagAddWidget = widget
        logger.info("✅ BatchTagAddWidget を新規作成してバッチタグタブに追加完了")

    @staticmethod
    def _setup_annotation_display_widget(main_window: Any, splitter: Any) -> None:
        """AnnotationDataDisplayWidgetの設定（スプリッター内のプレースホルダーを置換）"""
        if hasattr(main_window, "batchTagAnnotationDisplay") and main_window.batchTagAnnotationDisplay:
            logger.debug("AnnotationDataDisplayWidget は既に作成済み、スキップ")
            return

        from ..widgets.annotation_data_display_widget import AnnotationDataDisplayWidget

        # プレースホルダーを取得
        placeholder = splitter.findChild(object, "annotationDisplayPlaceholder")
        if not placeholder:
            logger.warning("⚠️ annotationDisplayPlaceholder が見つかりません")
            return

        # AnnotationDataDisplayWidget新規作成してプレースホルダーを置換
        widget = AnnotationDataDisplayWidget()
        widget.setObjectName("batchTagAnnotationDisplay")
        index = splitter.indexOf(placeholder)
        if index != -1:
            splitter.replaceWidget(index, widget)
        else:
            parent = placeholder.parentWidget()
            if parent and parent.layout():
                parent.layout().replaceWidget(placeholder, widget)
                widget.setParent(parent)
            else:
                logger.warning("⚠️ annotationDisplayPlaceholder の置換に失敗しました")
                return

        placeholder.deleteLater()
        logger.debug("🗑️ annotationDisplayPlaceholder を置換")

        main_window.batchTagAnnotationDisplay = widget
        logger.info("✅ AnnotationDataDisplayWidget を追加完了")

    @staticmethod
    def _setup_annotation_group_widgets(main_window: Any, annotation_group: Any) -> None:
        """アノテーショングループ内ウィジェットの設定"""
        # AnnotationFilterWidget
        if not (hasattr(main_window, "batchAnnotationFilter") and main_window.batchAnnotationFilter):
            from ..widgets.annotation_filter_widget import AnnotationFilterWidget

            placeholder = annotation_group.findChild(object, "annotationFilterPlaceholder")
            if placeholder:
                annotation_group.layout().removeWidget(placeholder)
                placeholder.setParent(None)
                placeholder.deleteLater()
                logger.debug("🗑️ annotationFilterPlaceholder を削除")

            widget = AnnotationFilterWidget()
            widget.setObjectName("batchAnnotationFilter")
            widget.setParent(annotation_group)
            annotation_group.layout().insertWidget(1, widget)

            main_window.batchAnnotationFilter = widget
            logger.info("✅ AnnotationFilterWidget を追加完了")

        # ModelSelectionWidget
        if not (hasattr(main_window, "batchModelSelection") and main_window.batchModelSelection):
            from ..widgets.model_selection_widget import ModelSelectionWidget

            placeholder = annotation_group.findChild(object, "modelSelectionPlaceholder")
            if placeholder:
                annotation_group.layout().removeWidget(placeholder)
                placeholder.setParent(None)
                placeholder.deleteLater()
                logger.debug("🗑️ modelSelectionPlaceholder を削除")

            widget = ModelSelectionWidget(mode="advanced")
            widget.setObjectName("batchModelSelection")
            widget.setParent(annotation_group)
            annotation_group.layout().insertWidget(2, widget)

            main_window.batchModelSelection = widget
            logger.info("✅ ModelSelectionWidget を追加完了 (mode=advanced)")

        # Signal接続
        if (
            hasattr(main_window, "batchAnnotationFilter")
            and hasattr(main_window, "batchModelSelection")
            and main_window.batchAnnotationFilter
            and main_window.batchModelSelection
            and not getattr(main_window, "_annotation_filter_connected", False)
        ):
            main_window.batchAnnotationFilter.filter_changed.connect(
                lambda filters: main_window.batchModelSelection.apply_filters(
                    provider="local" if filters.get("environment") == "local" else None,
                    capabilities=filters.get("capabilities", []) or ["caption", "tags", "scores"],
                    exclude_local=filters.get("environment") == "api",
                )
            )
            # アノテーション走査用デフォルトフィルター（upscaler除外）
            # 初期状態でアップスケーラーモデルを表示しない
            main_window.batchModelSelection.apply_filters(
                capabilities=["caption", "tags", "scores"]
            )
            main_window._annotation_filter_connected = True
            logger.info("✅ フィルター → モデル選択 Signal接続完了")

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
