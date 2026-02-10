# src/lorairo/gui/window/main_window.py

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSettings, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsOpacityEffect,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QWidget,
)

from ...database.db_core import IMG_DB_PATH, USER_TAG_DB_PATH, get_current_project_root
from ...database.db_manager import ImageDatabaseManager
from ...gui.designer.MainWindow_ui import Ui_MainWindow
from ...services import get_service_container
from ...services.configuration_service import ConfigurationService
from ...services.model_selection_service import ModelSelectionService
from ...services.selection_state_service import SelectionStateService
from ...services.service_container import ServiceContainer
from ...storage.file_system import FileSystemManager
from ...utils.log import logger
from ..controllers.annotation_workflow_controller import AnnotationWorkflowController
from ..controllers.dataset_controller import DatasetController
from ..controllers.export_controller import ExportController
from ..controllers.settings_controller import SettingsController
from ..services.image_db_write_service import ImageDBWriteService
from ..services.pipeline_control_service import PipelineControlService
from ..services.progress_state_service import ProgressStateService
from ..services.result_handler_service import ResultHandlerService
from ..services.search_filter_service import SearchFilterService
from ..services.tab_reorganization_service import TabReorganizationService
from ..services.widget_setup_service import WidgetSetupService
from ..services.worker_service import WorkerService
from ..state.dataset_state import DatasetStateManager
from ..widgets.error_log_viewer_dialog import ErrorLogViewerDialog
from ..widgets.error_notification_widget import ErrorNotificationWidget
from ..widgets.filter_search_panel import FilterSearchPanel
from ..widgets.image_preview import ImagePreviewWidget
from ..widgets.quick_tag_dialog import QuickTagDialog
from ..widgets.selected_image_details_widget import SelectedImageDetailsWidget
from ..widgets.tag_management_dialog import TagManagementDialog
from ..widgets.thumbnail import ThumbnailSelectorWidget


class MainWindow(QMainWindow, Ui_MainWindow):
    """
    メインワークスペースウィンドウ。
    データベース中心の設計で、画像の管理・検索・処理を統合的に提供。
    """

    # QSettings バージョン（UI構造変更時にインクリメント）
    SETTINGS_VERSION = 1

    # シグナル
    dataset_loaded = Signal(str)  # dataset_path
    database_registration_completed = Signal(int)  # registered_count

    # サービス属性の型定義（初期化で設定）
    config_service: ConfigurationService | None
    file_system_manager: FileSystemManager | None
    db_manager: ImageDatabaseManager | None
    worker_service: WorkerService | None
    dataset_state_manager: DatasetStateManager | None

    # Service/Controller層属性
    selection_state_service: SelectionStateService | None
    dataset_controller: DatasetController | None
    annotation_workflow_controller: AnnotationWorkflowController | None
    settings_controller: SettingsController | None
    export_controller: ExportController | None
    result_handler_service: ResultHandlerService | None
    pipeline_control_service: PipelineControlService | None
    progress_state_service: ProgressStateService | None

    @property
    def service_container(self) -> ServiceContainer:
        """ServiceContainer singleton instance"""
        return ServiceContainer()

    # ウィジェット属性の型定義（Qt Designerで生成）
    filterSearchPanel: FilterSearchPanel  # Qt Designer生成
    thumbnail_selector: ThumbnailSelectorWidget | None
    image_preview_widget: ImagePreviewWidget | None
    selected_image_details_widget: SelectedImageDetailsWidget | None

    # Tab widget (programmatically created)
    tabWidgetMainMode: QTabWidget

    # Error handling UI components
    error_notification_widget: ErrorNotificationWidget | None
    error_log_dialog: ErrorLogViewerDialog | None

    # Tag management UI components
    tag_management_dialog: TagManagementDialog | None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # 初期化失敗フラグ
        self._initialization_failed = False
        self._initialization_error: str | None = None

        try:
            # Phase 1: 基本UI設定（最優先）
            logger.info("MainWindow初期化開始 - Phase 1: UI設定")
            setup_ui = cast(Callable[[QWidget], None], self.setupUi)
            setup_ui(self)
            logger.info("UI設定完了")

            # エラーログメニューアクション接続（UI生成後に接続）
            if hasattr(self, "actionErrorLog"):
                self.actionErrorLog.triggered.connect(self._show_error_log_dialog)
                logger.debug("Error log menu action connected")

            # タグ管理メニューアクション追加（プログラム的に追加）
            if hasattr(self, "menuView"):
                from PySide6.QtGui import QAction

                self.actionTagManagement = QAction("タグタイプ管理", self)
                self.actionTagManagement.setShortcut("Ctrl+Shift+T")
                self.actionTagManagement.triggered.connect(self._show_tag_management_dialog)
                self.menuView.addAction(self.actionTagManagement)
                logger.debug("Tag management menu action added")

            # サービス初期化（例外を個別にキャッチ）
            logger.info("サービス初期化開始")
            self._initialize_services()

            # タブ構造のSignal接続（UIで定義済みのタブを使用）
            logger.info("タブ構造のSignal接続開始")
            self._setup_main_tab_connections()

            # Phase 3: UI カスタマイズ（サービス依存）
            logger.info("Phase 3: UI カスタマイズ開始")
            self.setup_custom_widgets()

            # Phase 3.5: サービス統合（新規）
            logger.info("Phase 3.5: SearchFilterService統合開始")
            self._setup_search_filter_integration()

            # Service統合（DataTransform/ResultHandler/PipelineControl）
            logger.info("Service層統合開始")
            self._setup_phase24_services()

            # Phase 4: イベント接続（最終段階）
            logger.info("Phase 4: イベント接続開始")
            self._connect_events()

            # Phase 5: ウィンドウ状態の復元（QSettings）
            logger.info("Phase 5: ウィンドウ状態復元開始")
            self._restore_window_state()

            logger.info("MainWindow初期化完了")

        except Exception as e:
            self._initialization_failed = True
            self._initialization_error = f"初期化エラー: {e}"
            logger.error(f"MainWindow初期化失敗: {e}", exc_info=True)

    def _initialize_services(self) -> None:
        """サービスを段階的に初期化し、致命的コンポーネントは強制終了"""

        # 致命的サービス初期化
        try:
            service_container = get_service_container()
            self.db_manager = service_container.db_manager
            if not self.db_manager:
                raise RuntimeError("ImageDatabaseManagerを取得できません")
            logger.info("✅ ImageDatabaseManager初期化成功")
        except Exception as e:
            self._handle_critical_initialization_failure("ImageDatabaseManager", e)
            return

        try:
            self.config_service = ConfigurationService()
            logger.info("✅ ConfigurationService初期化成功")
        except Exception as e:
            self._handle_critical_initialization_failure("ConfigurationService", e)
            return

        try:
            self.file_system_manager = FileSystemManager()
            logger.info("✅ FileSystemManager初期化成功")
        except Exception as e:
            logger.error(f"❌ FileSystemManager初期化失敗: {e}")
            self.file_system_manager = None

        try:
            if self.db_manager and self.file_system_manager:
                self.worker_service = WorkerService(self.db_manager, self.file_system_manager)
                logger.info("✅ WorkerService初期化成功")
            else:
                raise RuntimeError("WorkerService依存関係が未初期化")
        except Exception as e:
            self._handle_critical_initialization_failure("WorkerService", e)
            return

        try:
            self.dataset_state_manager = DatasetStateManager()
            # DatasetStateManagerにDB Manager参照を設定（バッチ操作後のリフレッシュに使用）
            if self.db_manager:
                self.dataset_state_manager.set_db_manager(self.db_manager)
                logger.info("✅ DatasetStateManager DB Manager参照設定完了")
            logger.info("✅ DatasetStateManager初期化成功")
        except Exception as e:
            logger.error(f"❌ DatasetStateManager初期化失敗: {e}")
            self.dataset_state_manager = None

        # DBステータス表示を現在のプロジェクトディレクトリに更新
        self._update_database_status_label()

        logger.info("サービス初期化完了")

    def _update_database_status_label(self) -> None:
        """ステータスバーのDB表示を現在のプロジェクトディレクトリに合わせる"""
        if not hasattr(self, "labelDbInfo") or self.labelDbInfo is None:
            return

        try:
            project_root = get_current_project_root().resolve()
            image_db_path = IMG_DB_PATH.resolve()
            tooltip_lines = [f"画像DB: {image_db_path}"]

            if USER_TAG_DB_PATH:
                tooltip_lines.append(f"タグDB: {USER_TAG_DB_PATH.resolve()}")

            self.labelDbInfo.setText(f"データベース: {project_root}")
            self.labelDbInfo.setToolTip("\n".join(tooltip_lines))
        except Exception as e:
            logger.warning(f"データベース表示の更新に失敗: {e}")

    def _handle_critical_initialization_failure(self, component_name: str, error: Exception) -> None:
        """致命的初期化失敗時の処理

        Args:
            component_name: 失敗したコンポーネント名
            error: 発生した例外
        """
        error_message = (
            f"致命的な初期化エラーが発生しました。\n\n"
            f"コンポーネント: {component_name}\n"
            f"エラー: {error!s}\n\n"
            f"アプリケーションを終了します。\n"
            f"問題が解決しない場合は、設定ファイルの確認または再インストールをお試しください。"
        )

        logger.critical(f"Critical initialization failure - {component_name}: {error}")

        # ユーザーへの通知（GUI利用可能なら）
        try:
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Critical)
            msg_box.setWindowTitle("LoRAIro - 致命的エラー")
            msg_box.setText(error_message)
            msg_box.exec()
        except Exception:
            # GUI不可の場合はコンソール出力
            print(f"\n{'=' * 60}")
            print("LoRAIro - 致命的エラー")
            print(f"{'=' * 60}")
            print(error_message)
            print(f"{'=' * 60}\n")

        # アプリケーション終了
        import sys

        sys.exit(1)

    def setup_custom_widgets(self) -> None:
        """カスタムウィジェットを設定（Qt Designer生成ウィジェット直接使用版）"""

        logger.info("🔍 カスタムウィジェット設定開始")

        # Qt Designer生成済みウィジェットの検証
        if not hasattr(self, "filterSearchPanel"):
            logger.error("❌ filterSearchPanel not found - Qt Designer UI generation failed")
            self._handle_critical_initialization_failure(
                "FilterSearchPanel設定", RuntimeError("filterSearchPanel attribute missing from setupUi()")
            )
            return
        # filterSearchPanelは型定義により保証されているため、isinstance不要

        # FilterSearchPanel interface validation
        required_methods = ["set_search_filter_service", "set_worker_service"]
        missing_methods = [
            method for method in required_methods if not hasattr(self.filterSearchPanel, method)
        ]

        if missing_methods:
            logger.error(f"❌ filterSearchPanel missing required methods: {missing_methods}")
            self._handle_critical_initialization_failure(
                "FilterSearchPanel設定",
                RuntimeError(f"filterSearchPanel interface validation failed: missing {missing_methods}"),
            )
            return

        logger.info(
            f"✅ filterSearchPanel validation successful: {type(self.filterSearchPanel)} (ID: {id(self.filterSearchPanel)})"
        )

        # その他のカスタムウィジェット設定
        self._setup_other_custom_widgets()

        logger.info("カスタムウィジェット設定完了")

    def _setup_other_custom_widgets(self) -> None:
        """その他のカスタムウィジェット設定（WidgetSetupServiceに委譲）"""
        WidgetSetupService.setup_all_widgets(self, self.dataset_state_manager)

        # Service/Controller層初期化
        try:
            self.selection_state_service = SelectionStateService(
                dataset_state_manager=self.dataset_state_manager,
                db_repository=self.db_manager.repository if self.db_manager else None,
            )
            self._verify_state_management_connections()

            self.dataset_controller = DatasetController(
                db_manager=self.db_manager,
                file_system_manager=self.file_system_manager,
                worker_service=self.worker_service,
                parent=self,
            )

            if not self.worker_service or not self.config_service:
                raise RuntimeError("WorkerService/ConfigurationServiceが未初期化です")

            worker_service = self.worker_service
            config_service = self.config_service
            self.annotation_workflow_controller = AnnotationWorkflowController(
                worker_service=worker_service,
                selection_state_service=self.selection_state_service,
                config_service=config_service,
                parent=self,
            )

            self.settings_controller = SettingsController(config_service=self.config_service, parent=self)
            self.export_controller = ExportController(
                selection_state_service=self.selection_state_service,
                service_container=self.service_container,
                parent=self,
            )

            logger.info("✅ Service/Controller層初期化完了")
        except Exception as e:
            logger.error(f"❌ Controller初期化失敗: {e}")
            self.selection_state_service = None
            self.dataset_controller = None
            self.annotation_workflow_controller = None
            self.settings_controller = None
            self.export_controller = None

        # ErrorNotificationWidget初期化（Phase 4.5）
        self._setup_error_notification()

        # BatchTagAddWidget再配置（Phase 2.5統合、Day 2）
        WidgetSetupService.setup_batch_tag_tab_widgets(self)

        # QTabWidget初期化（タブ切り替え用）
        self._setup_tab_widget()

    def _verify_state_management_connections(self) -> None:
        """状態管理接続の検証（SelectionStateServiceに委譲）"""
        if self.selection_state_service:
            self.selection_state_service.verify_state_management_connections(
                thumbnail_selector=getattr(self, "thumbnail_selector", None),
                image_preview_widget=getattr(self, "image_preview_widget", None),
                selected_image_details_widget=getattr(self, "selected_image_details_widget", None),
            )
        else:
            logger.error("SelectionStateServiceが初期化されていません - 接続検証をスキップ")

    def _setup_error_notification(self) -> None:
        """エラー通知Widget設定（StatusBar統合）"""
        try:
            # ErrorNotificationWidget作成
            self.error_notification_widget = ErrorNotificationWidget(parent=self)

            # ImageDatabaseManager注入
            if self.db_manager:
                self.error_notification_widget.set_db_manager(self.db_manager)
                logger.info("✅ ErrorNotificationWidget初期化成功")
            else:
                logger.warning("⚠️ ImageDatabaseManager未設定")

            # StatusBarに追加（permanent widget = 右端固定）
            self.statusBar().addPermanentWidget(self.error_notification_widget)

            # クリックでダイアログ表示
            self.error_notification_widget.clicked.connect(self._show_error_log_dialog)

            # Dialog初期化（遅延生成）
            self.error_log_dialog = None
            self.tag_management_dialog = None

        except Exception as e:
            logger.error(f"❌ ErrorNotificationWidget初期化失敗: {e}", exc_info=True)
            self.error_notification_widget = None

    def _setup_tab_widget(self) -> None:
        """QTabWidget（右パネル）の初期設定"""
        # QTabWidget (画像詳細)
        self.tab_widget_right_panel = getattr(self, "tabWidgetRightPanel", None)

        if not self.tab_widget_right_panel:
            logger.warning("tabWidgetRightPanel not found - tab widget integration skipped")
            return

        # 初期表示は画像詳細タブ（インデックス0）
        self.tab_widget_right_panel.setCurrentIndex(0)
        logger.info("tabWidgetRightPanel initialized with 1 tab: 画像詳細")

    def _show_error_log_dialog(self) -> None:
        """エラーログダイアログを表示（オンデマンド）"""
        try:
            # Lazy initialization (singleton pattern)
            if self.error_log_dialog is None:
                if not self.db_manager:
                    logger.error("ImageDatabaseManager not available")
                    QMessageBox.warning(self, "エラー", "データベース接続が確立されていません")
                    return

                self.error_log_dialog = ErrorLogViewerDialog(
                    db_manager=self.db_manager,
                    parent=self,
                    auto_load=True,
                )

                # Signal接続（error_resolvedで通知Widget更新）
                self.error_log_dialog.error_resolved.connect(self._on_error_resolved)

                logger.info("ErrorLogViewerDialog created (lazy initialization)")

            # Dialog表示
            self.error_log_dialog.show()
            self.error_log_dialog.raise_()  # 前面表示
            self.error_log_dialog.activateWindow()  # アクティブ化

        except Exception as e:
            logger.error(f"Failed to show error log dialog: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"エラーログの表示に失敗しました:\n{e}")

    def _on_error_resolved(self, error_id: int) -> None:
        """エラー解決時の処理（通知Widget更新）"""
        logger.info(f"Error resolved: error_id={error_id}")
        if self.error_notification_widget:
            self.error_notification_widget.update_error_count()

    def _show_tag_management_dialog(self) -> None:
        """タグ管理ダイアログを表示（オンデマンド）"""
        try:
            # Lazy initialization (singleton pattern)
            if self.tag_management_dialog is None:
                if not self.service_container:
                    logger.error("ServiceContainer not available")
                    QMessageBox.warning(self, "エラー", "サービス接続が確立されていません")
                    return

                self.tag_management_dialog = TagManagementDialog(
                    tag_service=self.service_container.tag_management_service,
                    parent=self,
                )

                logger.info("TagManagementDialog created (lazy initialization)")

            # Dialog表示
            self.tag_management_dialog.show()
            self.tag_management_dialog.raise_()  # 前面表示
            self.tag_management_dialog.activateWindow()  # アクティブ化

        except Exception as e:
            logger.error(f"Failed to show tag management dialog: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"タグ管理の表示に失敗しました:\n{e}")

    def _connect_events(self) -> None:
        """イベント接続を設定（安全な実装）"""
        try:
            logger.info("  - イベント接続開始...")

            # ウィジェット間のイベント接続（複雑な動的接続）
            if self.thumbnail_selector and self.image_preview_widget:
                try:
                    # サムネイル選択をプレビューに反映
                    self.thumbnail_selector.image_selected.connect(self.image_preview_widget.load_image)
                    # サムネイル右クリックからバッチタグへ送る
                    if hasattr(self.thumbnail_selector, "stage_selected_requested"):
                        self.thumbnail_selector.stage_selected_requested.connect(
                            self.send_selected_to_batch_tag
                        )
                    # クイックタグ追加要求
                    if hasattr(self.thumbnail_selector, "quick_tag_requested"):
                        self.thumbnail_selector.quick_tag_requested.connect(self._show_quick_tag_dialog)
                    logger.info("    ✅ サムネイル→プレビュー接続完了")
                except Exception as e:
                    logger.error(f"    ❌ サムネイル→プレビュー接続失敗: {e}")

            # 編集メニューの全選択/選択解除アクション接続
            if self.thumbnail_selector:
                try:
                    if hasattr(self, "actionSelectAll"):
                        self.actionSelectAll.triggered.connect(self.thumbnail_selector._select_all_items)
                    if hasattr(self, "actionDeselectAll"):
                        self.actionDeselectAll.triggered.connect(
                            self.thumbnail_selector._deselect_all_items
                        )
                    logger.info("    ✅ 編集メニュー（全選択/選択解除）接続完了")
                except Exception as e:
                    logger.error(f"    ❌ 編集メニュー接続失敗: {e}")

            # Sequential Worker Pipeline 統合シグナル接続
            self._setup_worker_pipeline_signals()

            # SelectedImageDetailsWidget から転送される Rating/Score シグナル接続
            if hasattr(self, "selectedImageDetailsWidget"):
                try:
                    self.selectedImageDetailsWidget.rating_changed.connect(self._handle_rating_changed)
                    self.selectedImageDetailsWidget.score_changed.connect(self._handle_score_changed)
                    self.selectedImageDetailsWidget.batch_rating_changed.connect(
                        self._handle_batch_rating_changed
                    )
                    self.selectedImageDetailsWidget.batch_score_changed.connect(
                        self._handle_batch_score_changed
                    )
                    logger.info("    ✅ SelectedImageDetailsWidget シグナル接続完了")
                except Exception as e:
                    logger.error(f"    ❌ SelectedImageDetailsWidget シグナル接続失敗: {e}")

            # DatasetStateManager シグナル接続 - 選択変更時のRating/Score更新
            if self.dataset_state_manager:
                try:
                    self.dataset_state_manager.selection_changed.connect(
                        self._handle_selection_changed_for_rating
                    )
                    logger.info("    ✅ DatasetStateManager selection_changed シグナル接続完了")
                except Exception as e:
                    logger.error(f"    ❌ DatasetStateManager selection_changed 接続失敗: {e}")

            # BatchTagAddWidget シグナル接続（Phase 3.1）
            if hasattr(self, "batchTagAddWidget"):
                try:
                    # DatasetStateManager 参照を設定
                    self.batchTagAddWidget.set_dataset_state_manager(self.dataset_state_manager)
                    # シグナル接続
                    self.batchTagAddWidget.tag_add_requested.connect(self._handle_batch_tag_add)
                    self.batchTagAddWidget.staging_cleared.connect(self._handle_staging_cleared)
                    self.batchTagAddWidget.staged_images_changed.connect(self._on_staged_images_changed)
                    # 初期状態: アノテーションボタン無効化（ステージング画像0件）
                    self._update_annotation_target_ui(0)
                    logger.info("    ✅ BatchTagAddWidget シグナル接続完了")
                except Exception as e:
                    logger.error(f"    ❌ BatchTagAddWidget シグナル接続失敗: {e}")

            # 設定ダイアログ接続
            if hasattr(self, "actionSettings"):
                self.actionSettings.triggered.connect(self.open_settings)
            if hasattr(self, "pushButtonSettings"):
                self.pushButtonSettings.clicked.connect(self.open_settings)

            # パネル表示切替アクション接続
            self._connect_panel_toggle_actions()

            logger.info("  ✅ イベント接続完了")

        except Exception as e:
            logger.error(f"イベント接続で予期しないエラー: {e}", exc_info=True)

    def _connect_panel_toggle_actions(self) -> None:
        """パネル表示切替アクションを接続する。

        actionToggleFilterPanel と actionTogglePreviewPanel を
        対応するパネルの表示/非表示切替に接続する。
        """
        try:
            # フィルターパネル表示切替
            if hasattr(self, "actionToggleFilterPanel"):
                self.actionToggleFilterPanel.toggled.connect(self._toggle_filter_panel)
                logger.info("    ✅ actionToggleFilterPanel 接続完了")

            # プレビューパネル表示切替
            if hasattr(self, "actionTogglePreviewPanel"):
                self.actionTogglePreviewPanel.toggled.connect(self._toggle_preview_panel)
                logger.info("    ✅ actionTogglePreviewPanel 接続完了")

        except Exception as e:
            logger.error(f"    ❌ パネル表示切替接続失敗: {e}")

    def _toggle_filter_panel(self, checked: bool) -> None:
        """フィルターパネルの表示/非表示を切り替える。

        Args:
            checked: True で表示、False で非表示
        """
        panel = getattr(self, "frameFilterSearchPanel", None)
        splitter = getattr(self, "splitterMainWorkArea", None)
        if not panel or not splitter:
            return

        if not checked:
            # 非表示前にスプリッターサイズを退避
            self._main_splitter_sizes_before_filter_hide = splitter.sizes()
        panel.setVisible(checked)
        if checked and hasattr(self, "_main_splitter_sizes_before_filter_hide"):
            # 再表示時にサイズを復元
            splitter.setSizes(self._main_splitter_sizes_before_filter_hide)
        logger.debug(f"Filter panel visibility: {checked}")

    def _toggle_preview_panel(self, checked: bool) -> None:
        """プレビューパネルの表示/非表示を切り替える。

        Args:
            checked: True で表示、False で非表示
        """
        panel = getattr(self, "framePreviewDetailPanel", None)
        splitter = getattr(self, "splitterMainWorkArea", None)
        if not panel or not splitter:
            return

        if not checked:
            # 非表示前にスプリッターサイズを退避
            self._main_splitter_sizes_before_preview_hide = splitter.sizes()
        panel.setVisible(checked)
        if checked and hasattr(self, "_main_splitter_sizes_before_preview_hide"):
            # 再表示時にサイズを復元
            splitter.setSizes(self._main_splitter_sizes_before_preview_hide)
        logger.debug(f"Preview panel visibility: {checked}")

    def _setup_worker_pipeline_signals(self) -> None:
        """WorkerService pipeline signal connections setup"""
        if not self.worker_service:
            logger.warning("WorkerService not available - pipeline signals not connected")
            return

        # Verify WorkerService has required signals
        required_signals = [
            "search_finished",
            "search_started",
            "search_error",
            "thumbnail_finished",
            "thumbnail_started",
            "thumbnail_error",
            "batch_registration_started",
            "batch_registration_finished",
            "batch_registration_error",
            "enhanced_annotation_finished",
            "enhanced_annotation_error",
            "worker_progress_updated",
            "worker_batch_progress",
        ]

        missing_signals = [
            signal for signal in required_signals if not hasattr(self.worker_service, signal)
        ]

        if missing_signals:
            logger.error(f"WorkerService missing required signals: {missing_signals}")
            return

        # Core pipeline connections
        self.worker_service.search_finished.connect(self._on_search_completed_start_thumbnail)
        self.worker_service.thumbnail_finished.connect(self._on_thumbnail_completed_update_display)

        # Progress tracking connections
        self.worker_service.search_started.connect(self._on_pipeline_search_started)
        self.worker_service.thumbnail_started.connect(self._on_pipeline_thumbnail_started)

        # Error handling connections
        self.worker_service.search_error.connect(self._on_pipeline_search_error)
        self.worker_service.thumbnail_error.connect(self._on_pipeline_thumbnail_error)

        # Batch registration connections
        self.worker_service.batch_registration_started.connect(self._on_batch_registration_started)
        self.worker_service.batch_registration_finished.connect(self._on_batch_registration_finished)
        self.worker_service.batch_registration_error.connect(self._on_batch_registration_error)

        # Annotation connections
        self.worker_service.enhanced_annotation_finished.connect(self._on_annotation_finished)
        self.worker_service.enhanced_annotation_error.connect(self._on_annotation_error)

        # Progress feedback connections
        self.worker_service.worker_progress_updated.connect(self._on_worker_progress_updated)
        self.worker_service.worker_batch_progress.connect(self._on_worker_batch_progress)

        logger.info("WorkerService pipeline signals connected (15 connections)")

    def _delegate_to_pipeline_control(self, method_name: str, *args: Any) -> None:
        """PipelineControlServiceへのイベント委譲ヘルパー"""
        if self.pipeline_control_service:
            getattr(self.pipeline_control_service, method_name)(*args)
        else:
            logger.error(f"PipelineControlService未初期化 - {method_name}スキップ")

    def _on_search_completed_start_thumbnail(self, search_result: Any) -> None:
        self._delegate_to_pipeline_control("on_search_completed", search_result)

    def _on_thumbnail_completed_update_display(self, thumbnail_result: Any) -> None:
        self._delegate_to_pipeline_control("on_thumbnail_completed", thumbnail_result)

    def _on_pipeline_search_started(self, _worker_id: str) -> None:
        self._delegate_to_pipeline_control("on_search_started", _worker_id)

    def _on_pipeline_thumbnail_started(self, _worker_id: str) -> None:
        self._delegate_to_pipeline_control("on_thumbnail_started", _worker_id)

    def _on_pipeline_search_error(self, error_message: str) -> None:
        self._delegate_to_pipeline_control("on_search_error", error_message)
        # エラー通知Widget更新
        if self.error_notification_widget:
            self.error_notification_widget.update_error_count()

    def _on_pipeline_thumbnail_error(self, error_message: str) -> None:
        self._delegate_to_pipeline_control("on_thumbnail_error", error_message)
        # エラー通知Widget更新
        if self.error_notification_widget:
            self.error_notification_widget.update_error_count()

    def _delegate_to_progress_state(self, method_name: str, *args: Any) -> None:
        """ProgressStateServiceへのイベント委譲ヘルパー"""
        if self.progress_state_service:
            getattr(self.progress_state_service, method_name)(*args)
        else:
            logger.warning(f"ProgressStateService未初期化 - {method_name}スキップ")

    def _on_batch_registration_started(self, worker_id: str) -> None:
        self._delegate_to_progress_state("on_batch_registration_started", worker_id)

    def _on_batch_registration_finished(self, result: Any) -> None:
        """Batch registration finished signal handler（ResultHandlerService委譲）"""
        if self.result_handler_service:
            self.result_handler_service.handle_batch_registration_finished(
                result, status_bar=self.statusBar(), completion_signal=self.database_registration_completed
            )
        else:
            # Fallback: Service未初期化時は簡易通知のみ
            logger.info(f"バッチ登録完了: result={type(result)}")
            self.statusBar().showMessage("バッチ登録完了", 5000)

    def _on_batch_registration_error(self, error_message: str) -> None:
        """Batch registration error signal handler（ProgressStateServiceに委譲 + QMessageBox）"""
        if self.progress_state_service:
            self.progress_state_service.on_batch_registration_error(error_message)

        # QMessageBoxはMainWindowで表示（UI要素のため）
        QMessageBox.critical(
            self, "バッチ登録エラー", f"バッチ登録中にエラーが発生しました:\n\n{error_message}"
        )

        # エラー通知Widget更新
        if self.error_notification_widget:
            self.error_notification_widget.update_error_count()

    def _on_worker_progress_updated(self, worker_id: str, progress: Any) -> None:
        self._delegate_to_progress_state("on_worker_progress_updated", worker_id, progress)

    def _on_worker_batch_progress(self, worker_id: str, current: int, total: int, filename: str) -> None:
        self._delegate_to_progress_state("on_worker_batch_progress", worker_id, current, total, filename)

    def _on_batch_annotation_started(self, total_images: int) -> None:
        self._delegate_to_progress_state("on_batch_annotation_started", total_images)

    def _on_batch_annotation_progress(self, processed: int, total: int) -> None:
        self._delegate_to_progress_state("on_batch_annotation_progress", processed, total)

    def _delegate_to_result_handler(self, method_name: str, *args: Any, **kwargs: Any) -> None:
        """ResultHandlerServiceへのイベント委譲ヘルパー"""
        if self.result_handler_service:
            getattr(self.result_handler_service, method_name)(*args, **kwargs)
        else:
            logger.warning(f"ResultHandlerService未初期化 - {method_name}スキップ")

    def _on_annotation_finished(self, result: Any) -> None:
        """アノテーション完了ハンドラ（キャッシュ更新付き）

        Args:
            result: PHashAnnotationResults (phash → model_name → UnifiedResult)

        Note:
            - Phase 1: ResultHandlerService経由でステータスバー通知
            - Phase 2: 検索結果キャッシュ更新（選択中画像の詳細パネル反映）
        """
        # Phase 1: ステータスバー通知
        self._delegate_to_result_handler("handle_annotation_finished", result, status_bar=self.statusBar())

        # Phase 2: 検索結果キャッシュ更新
        # ワークスペースタブで選択中の画像がアノテーション対象に含まれていた場合、
        # 詳細パネル（SelectedImageDetailsWidget）に最新情報が反映される
        if not self.dataset_state_manager or not self.db_manager:
            return

        if result and isinstance(result, dict):
            try:
                phash_to_image_id = self.db_manager.repository.find_image_ids_by_phashes(set(result.keys()))
                image_ids = [img_id for img_id in phash_to_image_id.values() if img_id is not None]

                if image_ids:
                    self.dataset_state_manager.refresh_images(image_ids)
                    logger.info(f"アノテーション完了: {len(image_ids)}件の画像キャッシュを更新")

            except Exception as e:
                logger.error(f"アノテーション完了後のキャッシュ更新失敗: {e}", exc_info=True)

    def _on_annotation_error(self, error_msg: str) -> None:
        self._delegate_to_result_handler("handle_annotation_error", error_msg, status_bar=self.statusBar())
        # エラー通知Widget更新
        if self.error_notification_widget:
            self.error_notification_widget.update_error_count()

    def _on_batch_annotation_finished(self, result: Any) -> None:
        self._delegate_to_result_handler(
            "handle_batch_annotation_finished", result, status_bar=self.statusBar()
        )

    def _on_model_sync_completed(self, sync_result: Any) -> None:
        self._delegate_to_result_handler(
            "handle_model_sync_completed", sync_result, status_bar=self.statusBar()
        )

    def cancel_current_pipeline(self) -> None:
        """現在のPipeline全体をキャンセル（PipelineControlService委譲）"""
        if self.pipeline_control_service:
            self.pipeline_control_service.cancel_current_pipeline()
        else:
            logger.warning("PipelineControlService未初期化 - Pipeline cancellation skipped")

    # Placeholder methods for UI actions - implement these based on your requirements
    def select_dataset_directory(self) -> Path | None:
        """データセットディレクトリ選択"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "データセットディレクトリを選択してください",
            "",
            QFileDialog.Option.ShowDirsOnly,
        )
        return Path(directory) if directory else None

    def select_and_process_dataset(self) -> None:
        """データセット選択と自動処理開始（DatasetControllerに委譲）"""
        self._execute_dataset_registration()

    def _execute_dataset_registration(self) -> None:
        """データセット登録の実行（共通メソッド）"""
        if self.dataset_controller:
            self.dataset_controller.select_and_register_images(
                dialog_callback=self.select_dataset_directory
            )
        else:
            logger.error("DatasetControllerが初期化されていません")
            QMessageBox.warning(
                self,
                "エラー",
                "DatasetControllerが初期化されていないため、データセット登録を開始できません。",
            )

    def load_images_from_db(self) -> None:
        """データベースから画像を読み込み、検索パイプラインを開始"""
        self._on_search_completed_start_thumbnail(True)

    def _setup_image_db_write_service(self) -> None:
        """ImageDBWriteServiceを作成してselected_image_details_widgetのシグナルを接続

        Phase 3.4: DB操作分離パターンの実装
        Issue #4: Rating/Score更新機能統合
        """
        if self.db_manager and self.selected_image_details_widget:
            # ImageDBWriteServiceを作成
            self.image_db_write_service = ImageDBWriteService(self.db_manager)

            # SelectedImageDetailsWidgetが編集シグナルを持たない場合はスキップ（閲覧専用化対応）
            if (
                hasattr(self.selected_image_details_widget, "rating_updated")
                and hasattr(self.selected_image_details_widget, "score_updated")
                and hasattr(self.selected_image_details_widget, "save_requested")
            ):
                self.selected_image_details_widget.rating_updated.connect(self._on_rating_update_requested)
                self.selected_image_details_widget.score_updated.connect(self._on_score_update_requested)
                self.selected_image_details_widget.save_requested.connect(self._on_save_requested)
                logger.info("ImageDBWriteService created and signals connected")
            else:
                logger.info("SelectedImageDetailsWidget is view-only; edit signals not connected")
        else:
            logger.warning(
                "Cannot setup ImageDBWriteService: db_manager or selected_image_details_widget not available"
            )

    def _on_rating_update_requested(self, image_id: int, rating: str) -> None:
        """Rating更新シグナルハンドラ（Issue #4）

        Args:
            image_id: 画像ID
            rating: Rating値 ("PG", "R", "X", など)
        """
        if not self.image_db_write_service:
            logger.warning("ImageDBWriteService not initialized")
            return

        success = self.image_db_write_service.update_rating(image_id, rating)
        if success:
            logger.info(f"Rating updated: image_id={image_id}, rating={rating}")
        else:
            logger.error(f"Failed to update rating: image_id={image_id}, rating={rating}")

    def _on_score_update_requested(self, image_id: int, score: int) -> None:
        """Score更新シグナルハンドラ（Issue #4）

        Args:
            image_id: 画像ID
            score: Score値 (0-1000範囲)
        """
        if not self.image_db_write_service:
            logger.warning("ImageDBWriteService not initialized")
            return

        success = self.image_db_write_service.update_score(image_id, score)
        if success:
            logger.info(f"Score updated: image_id={image_id}, score={score}")
        else:
            logger.error(f"Failed to update score: image_id={image_id}, score={score}")

    def _handle_rating_changed(self, image_id: int, rating: str) -> None:
        """
        RatingScoreEditWidget からの Rating 変更シグナルハンドラ（Phase 3.1）

        Args:
            image_id: 画像ID
            rating: Rating値 ("PG", "PG-13", "R", "X", "XXX")

        Side Effects:
            - ImageDBWriteService.update_rating() を呼び出し
            - 成功時: DatasetStateManager.refresh_image() でキャッシュ更新
            - 失敗時: エラーログ出力
        """
        if not self.image_db_write_service:
            logger.warning("ImageDBWriteService not initialized")
            return

        success = self.image_db_write_service.update_rating(image_id, rating)
        if success:
            # キャッシュを更新
            if self.dataset_state_manager:
                self.dataset_state_manager.refresh_image(image_id)
            logger.info(f"Rating updated successfully: image_id={image_id}, rating={rating}")
        else:
            logger.error(f"Failed to update rating: image_id={image_id}, rating={rating}")

    def _handle_score_changed(self, image_id: int, score: int) -> None:
        """
        RatingScoreEditWidget からの Score 変更シグナルハンドラ（Phase 3.1）

        Args:
            image_id: 画像ID
            score: Score値 (0-1000範囲)

        Side Effects:
            - ImageDBWriteService.update_score() を呼び出し
            - 成功時: DatasetStateManager.refresh_image() でキャッシュ更新
            - 失敗時: エラーログ出力
        """
        if not self.image_db_write_service:
            logger.warning("ImageDBWriteService not initialized")
            return

        success = self.image_db_write_service.update_score(image_id, score)
        if success:
            # キャッシュを更新
            if self.dataset_state_manager:
                self.dataset_state_manager.refresh_image(image_id)
            logger.info(f"Score updated successfully: image_id={image_id}, score={score}")
        else:
            logger.error(f"Failed to update score: image_id={image_id}, score={score}")

    def _handle_selection_changed_for_rating(self, image_ids: list[int]) -> None:
        """
        DatasetStateManager からの選択変更シグナルハンドラ（バッチレーティング/スコア機能）

        選択画像数に応じて RatingScoreEditWidget を更新:
        - 0件: クリア（未実装）
        - 1件: 単一選択モード（populate_from_image_data）
        - 2件以上: バッチモード（populate_from_selection）

        Args:
            image_ids: 選択画像IDリスト
        """
        if not hasattr(self, "selectedImageDetailsWidget"):
            return

        if not hasattr(self.selectedImageDetailsWidget, "_rating_score_widget"):
            return

        rating_widget = self.selectedImageDetailsWidget._rating_score_widget

        if len(image_ids) == 0:
            # 選択なし: 詳細パネルとRating/Scoreをクリア
            self.selectedImageDetailsWidget._clear_display()
            logger.debug("No images selected - display cleared")

        elif len(image_ids) == 1:
            # 単一選択: 従来の populate_from_image_data()
            if self.dataset_state_manager:
                image_data = self.dataset_state_manager.get_image_by_id(image_ids[0])
                if image_data:
                    rating_widget.populate_from_image_data(image_data)
                    logger.debug(f"Single selection: populated rating widget for image_id={image_ids[0]}")

        else:
            # 複数選択: 新規 populate_from_selection()
            if self.db_manager:
                rating_widget.populate_from_selection(image_ids, self.db_manager)
                logger.info(f"Batch mode activated for {len(image_ids)} images")

    def _handle_batch_rating_changed(self, image_ids: list[int], rating: str) -> None:
        """
        RatingScoreEditWidget からのバッチRating変更シグナルハンドラ

        Args:
            image_ids: 画像IDリスト
            rating: Rating値 ("PG", "PG-13", "R", "X", "XXX")

        Side Effects:
            - ImageDBWriteService.update_rating_batch() を呼び出し
            - 成功時: DatasetStateManager.refresh_images() でキャッシュ一括更新
            - 失敗時: エラーログ出力
        """
        logger.info(f"Batch rating change requested: {len(image_ids)} images, rating='{rating}'")

        success = self._execute_batch_rating_write(image_ids, rating)
        if success:
            # キャッシュを一括更新
            if self.dataset_state_manager:
                self.dataset_state_manager.refresh_images(image_ids)
            logger.info("Batch rating update completed successfully")

    def _execute_batch_rating_write(self, image_ids: list[int], rating: str) -> bool:
        """バッチレーティング書き込みとキャッシュ更新を実行する。

        Args:
            image_ids: 対象画像のIDリスト
            rating: Rating値

        Returns:
            成功した場合True
        """
        if not self.image_db_write_service:
            logger.warning("ImageDBWriteService not initialized")
            return False

        success = self.image_db_write_service.update_rating_batch(image_ids, rating)
        return success

    def _handle_batch_score_changed(self, image_ids: list[int], score: int) -> None:
        """
        RatingScoreEditWidget からのバッチScore変更シグナルハンドラ

        Args:
            image_ids: 画像IDリスト
            score: Score値 (0-1000範囲)

        Side Effects:
            - ImageDBWriteService.update_score_batch() を呼び出し
            - 成功時: DatasetStateManager.refresh_images() でキャッシュ一括更新
            - 失敗時: エラーログ出力
        """
        logger.info(f"Batch score change requested: {len(image_ids)} images, score={score}")

        success = self._execute_batch_score_write(image_ids, score)
        if success:
            # キャッシュを一括更新
            if self.dataset_state_manager:
                self.dataset_state_manager.refresh_images(image_ids)
            logger.info("Batch score update completed successfully")

    def _execute_batch_score_write(self, image_ids: list[int], score: int) -> bool:
        """バッチスコア書き込みとキャッシュ更新を実行する。

        Args:
            image_ids: 対象画像のIDリスト
            score: Score値 (0-1000範囲のUI値)

        Returns:
            成功した場合True
        """
        if not self.image_db_write_service:
            logger.warning("ImageDBWriteService not initialized")
            return False

        success = self.image_db_write_service.update_score_batch(image_ids, score)
        return success

    def _execute_batch_tag_write(self, image_ids: list[int], tag: str) -> bool:
        """バッチタグ書き込みとキャッシュ更新を実行する。

        Args:
            image_ids: 対象画像のIDリスト
            tag: 追加するタグ（正規化済み）

        Returns:
            成功した場合True
        """
        if not self.image_db_write_service:
            logger.warning("ImageDBWriteService not initialized")
            return False

        success = self.image_db_write_service.add_tag_batch(image_ids, tag)
        if success and self.dataset_state_manager:
            self.dataset_state_manager.refresh_images(image_ids)
        return success

    def _handle_batch_tag_add(self, image_ids: list[int], tag: str) -> None:
        """BatchTagAddWidget からのバッチタグ追加シグナルハンドラ。

        Args:
            image_ids: 対象画像のIDリスト
            tag: 追加するタグ（正規化済み）
        """
        if not image_ids:
            logger.warning("Batch tag add requested with empty image list")
            return

        logger.info(f"Batch tag add requested: tag='{tag}' for {len(image_ids)} images")

        success = self._execute_batch_tag_write(image_ids, tag)
        if success:
            # ステージングリストをクリア
            if hasattr(self, "batchTagAddWidget"):
                self.batchTagAddWidget._on_clear_staging_clicked()

            self.statusBar().showMessage(f"タグ '{tag}' を {len(image_ids)} 件の画像に追加しました", 5000)
            logger.info(
                f"Batch tag add completed successfully: tag='{tag}', {len(image_ids)} images updated"
            )
        else:
            QMessageBox.critical(self, "タグ追加失敗", f"タグ '{tag}' の追加に失敗しました。")
            logger.error(f"Failed to add tag in batch: tag='{tag}', image_count={len(image_ids)}")

    def _handle_staging_cleared(self) -> None:
        """
        BatchTagAddWidget からのステージングクリアシグナルハンドラ（Phase 3.1）

        ステージングクリア時にアノテーションUIを更新する。
        """
        logger.debug("Batch staging cleared")
        self._update_annotation_target_ui(0)

    def _on_staged_images_changed(self, image_ids: list[int]) -> None:
        """ステージング画像変更シグナルハンドラ

        ステージング画像数に応じてアノテーション対象ラベルとボタン状態を更新する。

        Args:
            image_ids: 現在のステージング画像IDリスト
        """
        count = len(image_ids) if image_ids else 0
        self._update_annotation_target_ui(count)

    def _update_annotation_target_ui(self, staging_count: int) -> None:
        """アノテーション対象UIを更新

        ステージング画像数に応じてラベルテキストとボタンの有効/無効を設定する。

        Args:
            staging_count: ステージング画像数
        """
        # ラベル更新
        if hasattr(self, "labelAnnotationTarget"):
            if staging_count > 0:
                self.labelAnnotationTarget.setText(f"◎ ステージング: {staging_count} 枚")
            else:
                self.labelAnnotationTarget.setText("◎ ステージング: 0 枚（画像を追加してください）")

        # ボタン有効/無効
        if hasattr(self, "btnAnnotationExecute"):
            self.btnAnnotationExecute.setEnabled(staging_count > 0)

    def _show_quick_tag_dialog(self, image_ids: list[int]) -> None:
        """クイックタグダイアログを表示する。

        サムネイル右クリックメニューから呼び出され、
        選択された画像に素早くタグを追加する。

        Args:
            image_ids: タグを追加する画像IDのリスト
        """
        if not image_ids:
            logger.warning("Quick tag dialog requested with empty image list")
            return

        dialog = QuickTagDialog(image_ids, parent=self)
        dialog.tag_add_requested.connect(self._handle_quick_tag_add)
        dialog.exec()

    def _handle_quick_tag_add(self, image_ids: list[int], tag: str) -> None:
        """クイックタグダイアログからのタグ追加要求を処理する。

        Args:
            image_ids: 対象画像のIDリスト
            tag: 追加するタグ（正規化済み）
        """
        logger.info(f"Quick tag add: tag='{tag}' for {len(image_ids)} images")

        success = self._execute_batch_tag_write(image_ids, tag)
        if success:
            self.statusBar().showMessage(f"クイックタグ '{tag}' を追加しました", 5000)
            logger.info(f"Quick tag add completed: tag='{tag}', {len(image_ids)} images updated")
        else:
            QMessageBox.critical(self, "タグ追加失敗", f"クイックタグ '{tag}' の追加に失敗しました。")
            logger.error(f"Failed quick tag add: tag='{tag}', image_count={len(image_ids)}")

    def _on_save_requested(self, save_data: dict[str, Any]) -> None:
        """保存要求シグナルハンドラ（Issue #4）

        Args:
            save_data: 保存データ {"image_id": int, "rating": str, "score": int}
        """
        if not self.image_db_write_service:
            logger.warning("ImageDBWriteService not initialized")
            return

        image_id = save_data.get("image_id")
        rating = save_data.get("rating")
        score = save_data.get("score")

        if image_id is None:
            logger.warning("Save requested but image_id is None")
            return

        # Rating更新
        if rating:
            self.image_db_write_service.update_rating(image_id, rating)

        # Score更新
        if score is not None:
            self.image_db_write_service.update_score(image_id, score)

        logger.info(f"Save completed: image_id={image_id}, rating={rating}, score={score}")

    # === Edit/View モード切替（Side Panel） ===
    def _get_current_image_payload(self) -> dict[str, Any] | None:
        """現在選択中の画像データを編集パネル用に取得"""
        if not self.dataset_state_manager:
            logger.warning("DatasetStateManager not available")
            return None

        data = self.dataset_state_manager.get_current_image_data()
        if not data:
            logger.warning("No current image selected")
            return None

        payload = {
            "id": data.get("id"),
            "rating": data.get("rating_value") or "PG",
            # DBスコア(0-10) → UI内部値(0-1000)へ変換
            "score": int((data.get("score_value") or 0) * 100),
            "tags": data.get("tags_text") or "",
            "caption": data.get("caption_text") or "",
        }
        return payload

    def _create_search_filter_service(self) -> SearchFilterService:
        """
        SearchFilterService作成（ServiceContainer統一）

        Returns:
            SearchFilterService: 設定されたサービスインスタンス
        """
        try:
            # ServiceContainer経由で一貫したサービス取得
            service_container = get_service_container()
            repo = service_container.image_repository
            model_selection_service = ModelSelectionService.create(db_repository=repo)

            dbm = self.db_manager

            if not dbm:
                raise ValueError("ImageDatabaseManager is required but not available")

            return SearchFilterService(db_manager=dbm, model_selection_service=model_selection_service)

        except Exception as e:
            logger.error(f"Failed to create SearchFilterService: {e}", exc_info=True)
            # 致命的エラーとして扱う（フォールバック中止）
            raise ValueError("SearchFilterService作成不可") from e

    def _setup_search_filter_integration(self) -> None:
        """SearchFilterService統合処理（必須機能）

        filterSearchPanelにSearchFilterServiceを注入して検索機能を有効化。
        検索機能は必須のため、失敗時はアプリケーション起動を中止する。
        """
        if not hasattr(self, "filterSearchPanel") or not self.filterSearchPanel:
            self._handle_critical_initialization_failure(
                "SearchFilterService統合", RuntimeError("filterSearchPanel not available")
            )
            return

        if not self.db_manager:
            self._handle_critical_initialization_failure(
                "SearchFilterService統合", RuntimeError("db_manager not available")
            )
            return

        try:
            search_filter_service = self._create_search_filter_service()
            self.filterSearchPanel.set_search_filter_service(search_filter_service)

            if self.worker_service:
                self.filterSearchPanel.set_worker_service(self.worker_service)
                logger.info("✅ SearchFilterService統合完了（WorkerService統合済み）")
            else:
                logger.info("✅ SearchFilterService統合完了（同期検索モード）")

            # Phase 4: FavoriteFiltersService統合
            service_container = get_service_container()
            favorite_filters_service = service_container.favorite_filters_service
            self.filterSearchPanel.set_favorite_filters_service(favorite_filters_service)
            logger.info("✅ FavoriteFiltersService統合完了")

        except Exception as e:
            # 検索機能は必須のため、失敗時はアプリケーション起動を中止
            self._handle_critical_initialization_failure("SearchFilterService統合", e)

    def _setup_phase24_services(self) -> None:
        """Service層の初期化と統合

        ResultHandlerService, PipelineControlServiceを初期化。
        MainWindowから抽出されたロジックをService層に委譲する。
        """
        try:
            # ResultHandlerService初期化（Stage 4-1）
            logger.info("  - ResultHandlerService初期化中...")
            self.result_handler_service = ResultHandlerService(parent=self)
            logger.info("  ✅ ResultHandlerService初期化成功")

            # PipelineControlService初期化（Stage 4-2）
            logger.info("  - PipelineControlService初期化中...")
            self.pipeline_control_service = PipelineControlService(
                worker_service=self.worker_service,
                thumbnail_selector=self.thumbnail_selector,
                filter_search_panel=self.filterSearchPanel if hasattr(self, "filterSearchPanel") else None,
            )
            logger.info("  ✅ PipelineControlService初期化成功")

            # ProgressStateService初期化
            logger.info("  - ProgressStateService初期化中...")
            self.progress_state_service = ProgressStateService(status_bar=self.statusBar())
            logger.info("  ✅ ProgressStateService初期化成功")

            # ImageDBWriteService初期化（Issue #4: Rating/Score更新機能）
            logger.info("  - ImageDBWriteService初期化中...")
            self._setup_image_db_write_service()
            logger.info("  ✅ ImageDBWriteService初期化成功")

            logger.info("Service層統合完了")

        except Exception as e:
            logger.error(f"Service層統合失敗: {e}", exc_info=True)
            logger.warning("一部のService機能は利用できませんが、その他の機能は正常に動作します")
            self.result_handler_service = None
            self.pipeline_control_service = None
            self.progress_state_service = None

    def open_settings(self) -> None:
        """設定ウィンドウを開く（SettingsControllerに委譲）"""
        if self.settings_controller:
            self.settings_controller.open_settings_dialog()
        else:
            logger.error("SettingsControllerが初期化されていません")
            QMessageBox.warning(
                self, "設定エラー", "SettingsControllerが初期化されていないため、設定を開けません。"
            )

    def start_annotation(self) -> None:
        """アノテーション処理を開始（AnnotationWorkflowController統合版）"""
        if not self.annotation_workflow_controller:
            QMessageBox.warning(
                self,
                "コントローラー未初期化",
                "AnnotationWorkflowControllerが初期化されていないため、アノテーション処理を開始できません。",
            )
            return

        # batchModelSelectionから選択されたモデルを取得
        selected_models: list[str] = []
        if hasattr(self, "batchModelSelection") and self.batchModelSelection:
            selected_models = self.batchModelSelection.get_selected_models()
            logger.debug(f"batchModelSelectionから選択されたモデル: {selected_models}")

        # バッチタグタブの場合はステージング画像を使用
        override_image_paths: list[str] | None = None
        if self.tabWidgetMainMode.currentIndex() == 1:  # tabBatchTag
            override_image_paths = self._get_staged_image_paths_for_annotation()
            if not override_image_paths:
                QMessageBox.information(
                    self,
                    "ステージング画像なし",
                    "ステージングリストに画像がありません。\n"
                    "画像を選択してからアノテーションを実行してください。",
                )
                return

        # AnnotationWorkflowControllerに委譲（チェックボックスから選択されたモデルを優先）
        self.annotation_workflow_controller.start_annotation_workflow(
            selected_models=selected_models if selected_models else None,
            model_selection_callback=self._show_model_selection_dialog if not selected_models else None,
            image_paths=override_image_paths,
        )

    def _show_model_selection_dialog(self, available_models: list[str]) -> str | None:
        """モデル選択ダイアログ表示（Callbackパターン）

        Args:
            available_models: 利用可能なモデル名リスト

        Returns:
            str | None: 選択されたモデル名、キャンセル時はNone
        """
        from PySide6.QtWidgets import QInputDialog

        selected_model, ok = QInputDialog.getItem(
            self,
            "モデル選択",
            "アノテーションに使用するモデルを選択してください:",
            available_models,
            0,  # デフォルト選択
            False,  # 編集不可
        )

        return selected_model if ok else None

    def _get_staged_image_paths_for_annotation(self) -> list[str]:
        """バッチタグタブのステージング画像パスを取得

        BatchTagAddWidget._staged_imagesから画像IDを取得し、
        DatasetStateManagerから実際のファイルパスに変換する。

        Returns:
            list[str]: 画像ファイルパスリスト。エラー時は空リスト。
        """
        from lorairo.database.db_core import resolve_stored_path

        batch_widget = getattr(self, "batchTagAddWidget", None)
        if not batch_widget or not batch_widget._staged_images:
            return []

        if not self.dataset_state_manager:
            logger.warning("DatasetStateManager not available for path resolution")
            return []

        paths: list[str] = []
        for image_id, (_, stored_path) in batch_widget._staged_images.items():
            if stored_path:
                resolved = resolve_stored_path(stored_path)
                if resolved and resolved.exists():
                    paths.append(str(resolved))
                else:
                    logger.debug(f"画像パスが存在しない: ID={image_id}, path={stored_path}")

        logger.debug(f"ステージング画像パスを取得: {len(paths)}件")
        return paths

    def export_data(self) -> None:
        """データセットエクスポート機能を開く（ExportControllerに委譲）"""
        if self.export_controller:
            self.export_controller.open_export_dialog()
        else:
            logger.error("ExportControllerが初期化されていません")
            QMessageBox.warning(
                self, "エラー", "ExportControllerが初期化されていないため、エクスポートを開始できません。"
            )

    def send_selected_to_batch_tag(self, selected_ids: list[int] | None = None) -> None:
        """ワークスペースの選択画像をバッチタグのステージングに追加"""
        if not self.dataset_state_manager:
            logger.warning("DatasetStateManager not available")
            QMessageBox.warning(self, "エラー", "データセットが初期化されていません。")
            return

        batch_tag_widget = getattr(self, "batchTagAddWidget", None)
        if not batch_tag_widget:
            logger.warning("BatchTagAddWidget not found")
            QMessageBox.warning(self, "エラー", "バッチタグ機能が初期化されていません。")
            return

        target_ids = (
            selected_ids if selected_ids is not None else self.dataset_state_manager.selected_image_ids
        )
        if not target_ids:
            QMessageBox.information(self, "選択なし", "バッチタグに追加する画像が選択されていません。")
            return

        # バッチタグタブへ移動してステージングタブを表示
        if hasattr(self, "tabWidgetMainMode") and self.tabWidgetMainMode:
            self.tabWidgetMainMode.setCurrentIndex(1)
        if hasattr(self, "tabWidgetBatchTagWorkflow") and self.tabWidgetBatchTagWorkflow:
            self.tabWidgetBatchTagWorkflow.setCurrentIndex(0)

        # ステージングに追加
        if hasattr(batch_tag_widget, "add_image_ids_to_staging"):
            batch_tag_widget.add_image_ids_to_staging(target_ids)
        elif hasattr(batch_tag_widget, "add_selected_images_to_staging"):
            batch_tag_widget.add_selected_images_to_staging()
        else:
            # 互換: 旧実装のクリックハンドラを直接呼び出す
            batch_tag_widget._on_add_selected_clicked()

    def _setup_main_tab_connections(self) -> None:
        """
        タブウィジェットのSignal接続（UIで定義済みのタブを使用）

        MainWindow.ui で定義された tabWidgetMainMode の Signal 接続を設定し、
        タブ構造の検証を行う。

        Note:
            ワークスペースタブでは右カラムのアノテーション制御（groupBoxAnnotationControl）を
            非表示にする。バッチタグ機能はバッチタグタブに移動したため。
        """
        # UIで定義されたtabWidgetMainModeの存在確認
        if not hasattr(self, "tabWidgetMainMode") or not self.tabWidgetMainMode:
            logger.error("tabWidgetMainMode not found in UI - check MainWindow.ui")
            return

        # タブ構造の検証
        if not TabReorganizationService.validate_tab_structure(self):
            logger.warning("Tab structure validation failed - some widgets may be missing")

        # タブ切り替えSignal接続
        self.tabWidgetMainMode.currentChanged.connect(self._on_main_tab_changed)

        logger.info("Main tab connections setup completed")

    def _on_main_tab_changed(self, index: int) -> None:
        """
        メインタブ切り替えハンドラ

        Args:
            index: 切り替え先のタブインデックス（0=ワークスペース、1=バッチタグ）
        """
        if index == 0:  # ワークスペース
            logger.info("Switched to Workspace tab")
            # ワークスペースタブに切り替え時の処理（必要に応じて実装）
        elif index == 1:  # バッチタグ
            logger.info("Switched to Batch Tag tab")
            self._refresh_batch_tag_staging()
        else:
            logger.warning(f"Unknown tab index: {index}")

    def _refresh_batch_tag_staging(self) -> None:
        """
        バッチタグタブのステージングリスト更新

        Note:
            BatchTagAddWidget._staged_imagesはprivate属性なので直接アクセスしない。
            代わりに_refresh_staging_list_ui()を呼び出してUI更新を委譲する。
        """
        # BatchTagAddWidgetを取得（Ui_MainWindowを多重継承しているため、selfの直接の属性）
        batch_tag_widget = getattr(self, "batchTagAddWidget", None)
        if not batch_tag_widget:
            logger.warning("BatchTagAddWidget not found, skipping staging refresh")
            return

        # BatchTagAddWidgetのUI更新メソッドを呼び出し
        if hasattr(batch_tag_widget, "_refresh_staging_list_ui"):
            batch_tag_widget._refresh_staging_list_ui()
            logger.debug("Batch tag staging list refreshed")
        else:
            logger.error("_refresh_staging_list_ui method not found on BatchTagAddWidget")

    # -------------------------------------------------------------------------
    # QSettings: ウィンドウ/スプリッター状態の保存・復元
    # -------------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        """ウィンドウ閉鎖時にレイアウト状態を保存する。

        Args:
            event: クローズイベント
        """
        self._save_window_state()
        super().closeEvent(event)

    def _save_window_state(self) -> None:
        """QSettingsにウィンドウ/スプリッター状態を保存する。"""
        settings = QSettings()

        # バージョン記録
        settings.setValue("main_window/settings_version", self.SETTINGS_VERSION)

        # ウィンドウジオメトリ
        settings.setValue("main_window/geometry", self.saveGeometry())

        # ウィンドウ状態（最大化等）
        settings.setValue("main_window/state", self.saveState())

        # スプリッター状態
        self._save_splitter_states(settings)

        # パネル表示状態
        if hasattr(self, "actionToggleFilterPanel"):
            settings.setValue("panel_visible/filter", self.actionToggleFilterPanel.isChecked())
        if hasattr(self, "actionTogglePreviewPanel"):
            settings.setValue("panel_visible/preview", self.actionTogglePreviewPanel.isChecked())

        settings.sync()
        logger.info("Window state saved to QSettings")

    def _save_splitter_states(self, settings: QSettings) -> None:
        """スプリッター状態を保存する。

        Args:
            settings: QSettingsインスタンス
        """
        splitters = [
            ("splitterMainWorkArea", "splitter/main_work_area"),
            ("splitterPreviewDetails", "splitter/preview_details"),
            ("splitterBatchTagMain", "splitter/batch_tag_main"),
            ("splitterBatchTagOperations", "splitter/batch_tag_operations"),
        ]

        for attr_name, settings_key in splitters:
            splitter = getattr(self, attr_name, None)
            if splitter:
                settings.setValue(settings_key, splitter.saveState())

    def _restore_window_state(self) -> None:
        """QSettingsからウィンドウ/スプリッター状態を復元する。"""
        settings = QSettings()

        # バージョンチェック
        saved_version = cast(int, settings.value("main_window/settings_version", 0, type=int))
        if saved_version != self.SETTINGS_VERSION:
            logger.info(
                f"Settings version mismatch (saved={saved_version}, "
                f"current={self.SETTINGS_VERSION}) - using defaults"
            )
            return

        # ウィンドウジオメトリ
        geometry = settings.value("main_window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
            logger.debug("Window geometry restored")

        # ウィンドウ状態（最大化等）
        state = settings.value("main_window/state")
        if state:
            self.restoreState(state)
            logger.debug("Window state restored")

        # スプリッター状態
        restored = self._restore_splitter_states(settings)

        # パネル表示状態
        self._restore_panel_visibility(settings)

        if restored:
            logger.info("Window state restored from QSettings")

    def _restore_splitter_states(self, settings: QSettings) -> bool:
        """スプリッター状態を復元する。

        Args:
            settings: QSettingsインスタンス

        Returns:
            少なくとも1つのスプリッターが復元された場合True
        """
        splitters = [
            ("splitterMainWorkArea", "splitter/main_work_area"),
            ("splitterPreviewDetails", "splitter/preview_details"),
            ("splitterBatchTagMain", "splitter/batch_tag_main"),
            ("splitterBatchTagOperations", "splitter/batch_tag_operations"),
        ]

        restored_any = False
        for attr_name, settings_key in splitters:
            splitter = getattr(self, attr_name, None)
            if splitter:
                state = settings.value(settings_key)
                if state:
                    splitter.restoreState(state)
                    restored_any = True
                    logger.debug(f"{attr_name} state restored")

        return restored_any

    def _restore_panel_visibility(self, settings: QSettings) -> None:
        """パネル表示状態を復元する。

        blockSignals で toggled シグナルを抑制し、
        パネルの可視状態を直接設定することで race condition を回避する。

        Args:
            settings: QSettingsインスタンス
        """
        # フィルターパネル
        filter_visible = bool(settings.value("panel_visible/filter", True, type=bool))
        if hasattr(self, "actionToggleFilterPanel"):
            self.actionToggleFilterPanel.blockSignals(True)
            self.actionToggleFilterPanel.setChecked(filter_visible)
            self.actionToggleFilterPanel.blockSignals(False)
            panel = getattr(self, "frameFilterSearchPanel", None)
            if panel:
                panel.setVisible(filter_visible)

        # プレビューパネル
        preview_visible = bool(settings.value("panel_visible/preview", True, type=bool))
        if hasattr(self, "actionTogglePreviewPanel"):
            self.actionTogglePreviewPanel.blockSignals(True)
            self.actionTogglePreviewPanel.setChecked(preview_visible)
            self.actionTogglePreviewPanel.blockSignals(False)
            panel = getattr(self, "framePreviewDetailPanel", None)
            if panel:
                panel.setVisible(preview_visible)
