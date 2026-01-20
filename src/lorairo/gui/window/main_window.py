# src/lorairo/gui/window/main_window.py

from pathlib import Path
from typing import Any

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Signal
from PySide6.QtGui import QResizeEvent
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
from ...services.data_transform_service import DataTransformService
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
from ..widgets.selected_image_details_widget import SelectedImageDetailsWidget
from ..widgets.tag_management_dialog import TagManagementDialog
from ..widgets.thumbnail import ThumbnailSelectorWidget


class MainWindow(QMainWindow, Ui_MainWindow):
    """
    メインワークスペースウィンドウ。
    データベース中心の設計で、画像の管理・検索・処理を統合的に提供。
    """

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
    data_transform_service: DataTransformService | None
    result_handler_service: ResultHandlerService | None
    pipeline_control_service: PipelineControlService | None

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
    tabWidgetMainMode: QTabWidget | None

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
            self.setupUi(self)
            logger.info("UI設定完了")

            # エラーログメニューアクション接続（UI生成後に接続）
            if hasattr(self, "actionErrorLog"):
                self.actionErrorLog.triggered.connect(self._show_error_log_dialog)
                logger.debug("Error log menu action connected")

            # タグ管理メニューアクション追加（プログラム的に追加）
            if hasattr(self, "menuView"):
                from PySide6.QtGui import QAction

                self.actionTagManagement = QAction("タグタイプ管理", self)
                self.actionTagManagement.setShortcut("Ctrl+T")
                self.actionTagManagement.triggered.connect(self._show_tag_management_dialog)
                self.menuView.addAction(self.actionTagManagement)
                logger.debug("Tag management menu action added")

            # サービス初期化（例外を個別にキャッチ）
            logger.info("サービス初期化開始")
            self._initialize_services()

            # Phase 2.5: トップレベルタブ作成（新規）
            logger.info("Phase 2.5: トップレベルタブ作成開始")
            self._create_main_tab_widget()

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

            self.annotation_workflow_controller = AnnotationWorkflowController(
                worker_service=self.worker_service,
                selection_state_service=self.selection_state_service,
                config_service=self.config_service,
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
        # QTabWidget (画像詳細 / バッチタグ追加)
        self.tab_widget_right_panel = getattr(self, "tabWidgetRightPanel", None)

        if not self.tab_widget_right_panel:
            logger.warning("tabWidgetRightPanel not found - tab widget integration skipped")
            return

        # 初期表示は画像詳細タブ（インデックス0）
        self.tab_widget_right_panel.setCurrentIndex(0)
        logger.info("QTabWidget initialized with 2 tabs: 画像詳細, バッチタグ追加")

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
                    logger.info("    ✅ サムネイル→プレビュー接続完了")
                except Exception as e:
                    logger.error(f"    ❌ サムネイル→プレビュー接続失敗: {e}")

            # Sequential Worker Pipeline 統合シグナル接続
            self._setup_worker_pipeline_signals()

            # SelectedImageDetailsWidget から転送される Rating/Score シグナル接続
            if hasattr(self, "selectedImageDetailsWidget"):
                try:
                    self.selectedImageDetailsWidget.rating_changed.connect(self._handle_rating_changed)
                    self.selectedImageDetailsWidget.score_changed.connect(self._handle_score_changed)
                    logger.info("    ✅ SelectedImageDetailsWidget シグナル接続完了")
                except Exception as e:
                    logger.error(f"    ❌ SelectedImageDetailsWidget シグナル接続失敗: {e}")

            # BatchTagAddWidget シグナル接続（Phase 3.1）
            if hasattr(self, "batchTagAddWidget"):
                try:
                    # DatasetStateManager 参照を設定
                    self.batchTagAddWidget.set_dataset_state_manager(self.dataset_state_manager)
                    # シグナル接続
                    self.batchTagAddWidget.tag_add_requested.connect(self._handle_batch_tag_add)
                    self.batchTagAddWidget.staging_cleared.connect(self._handle_staging_cleared)
                    logger.info("    ✅ BatchTagAddWidget シグナル接続完了")
                except Exception as e:
                    logger.error(f"    ❌ BatchTagAddWidget シグナル接続失敗: {e}")

            logger.info("  ✅ イベント接続完了")

        except Exception as e:
            logger.error(f"イベント接続で予期しないエラー: {e}", exc_info=True)

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

        # Progress feedback connections
        self.worker_service.worker_progress_updated.connect(self._on_worker_progress_updated)
        self.worker_service.worker_batch_progress.connect(self._on_worker_batch_progress)

        logger.info("WorkerService pipeline signals connected (13 connections)")

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

        Note:
            - Phase 1: ResultHandlerService経由で通知処理
            - Phase 2: DatasetStateManagerキャッシュ更新でGUI反映
        """
        # Phase 1: 既存のResultHandlerService処理
        self._delegate_to_result_handler("handle_annotation_finished", result, status_bar=self.statusBar())

        # Phase 2: キャッシュ更新 (NEW)
        # dataset_state_manager未初期化チェック
        if not self.dataset_state_manager:
            logger.warning("DatasetStateManager未初期化 - キャッシュ更新をスキップ")
            return

        current_image_id = self.dataset_state_manager.current_image_id
        if current_image_id:
            try:
                # DBから最新メタデータ取得
                fresh_metadata = self.db_manager.repository.get_image_metadata(current_image_id)

                if fresh_metadata:
                    # キャッシュ更新＋シグナル発行
                    self.dataset_state_manager.update_image_metadata(current_image_id, fresh_metadata)
                    logger.info(f"キャッシュ更新完了: image_id={current_image_id}")
            except Exception as e:
                logger.error(f"キャッシュ更新失敗: {e}", exc_info=True)

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

    def _resolve_optimal_thumbnail_data(
        self, image_metadata: list[dict[str, Any]]
    ) -> list[tuple[Path, int]]:
        """画像メタデータから最適なサムネイル表示用パスを解決（DataTransformService委譲）

        Args:
            image_metadata: 画像メタデータリスト

        Returns:
            list[tuple[Path, int]]: (画像パス, 画像ID) のタプルリスト
        """
        if self.data_transform_service:
            return self.data_transform_service.resolve_optimal_thumbnail_paths(image_metadata)

        # Fallback: Service未初期化時は元画像のみ使用
        return [(Path(metadata["stored_image_path"]), metadata["id"]) for metadata in image_metadata]

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

    def _handle_batch_tag_add(self, image_ids: list[int], tag: str) -> None:
        """
        BatchTagAddWidget からのバッチタグ追加シグナルハンドラ（Phase 3.1）

        複数画像に対して1つのタグを一括追加します。

        Args:
            image_ids: 対象画像のIDリスト
            tag: 追加するタグ（正規化済み）

        Side Effects:
            - ImageDBWriteService.add_tag_batch() を呼び出し
            - 成功時: DatasetStateManager.refresh_images() でキャッシュ一括更新
            - 成功時: BatchTagAddWidget のステージングリストをクリア
            - 失敗時: エラーログ出力
        """
        if not self.image_db_write_service:
            logger.warning("ImageDBWriteService not initialized")
            return

        if not image_ids:
            logger.warning("Batch tag add requested with empty image list")
            return

        logger.info(f"Batch tag add requested: tag='{tag}' for {len(image_ids)} images")

        success = self.image_db_write_service.add_tag_batch(image_ids, tag)
        if success:
            # キャッシュを一括更新
            if self.dataset_state_manager:
                self.dataset_state_manager.refresh_images(image_ids)

            # ステージングリストをクリア
            if hasattr(self, "batchTagAddWidget"):
                self.batchTagAddWidget._on_clear_staging_clicked()

            logger.info(
                f"Batch tag add completed successfully: tag='{tag}', {len(image_ids)} images updated"
            )
        else:
            logger.error(f"Failed to add tag in batch: tag='{tag}', image_count={len(image_ids)}")

    def _handle_staging_cleared(self) -> None:
        """
        BatchTagAddWidget からのステージングクリアシグナルハンドラ（Phase 3.1）

        現在は何もしない（将来的にUI状態をリセットする場合に使用）
        """
        logger.debug("Batch staging cleared")

    def _on_save_requested(self, save_data: dict) -> None:
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

        DataTransformService, ResultHandlerService, PipelineControlServiceを初期化。
        MainWindowから抽出されたロジックをService層に委譲する。
        """
        try:
            # DataTransformService初期化（Stage 4-1）
            logger.info("  - DataTransformService初期化中...")
            self.data_transform_service = DataTransformService(db_manager=self.db_manager)
            logger.info("  ✅ DataTransformService初期化成功")

            # ResultHandlerService初期化（Stage 4-2）
            logger.info("  - ResultHandlerService初期化中...")
            self.result_handler_service = ResultHandlerService(parent=self)
            logger.info("  ✅ ResultHandlerService初期化成功")

            # PipelineControlService初期化（Stage 4-3）
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
            self.data_transform_service = None
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

        # AnnotationWorkflowControllerに委譲
        self.annotation_workflow_controller.start_annotation_workflow(
            model_selection_callback=self._show_model_selection_dialog
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

    def export_data(self) -> None:
        """データセットエクスポート機能を開く（ExportControllerに委譲）"""
        if self.export_controller:
            self.export_controller.open_export_dialog()
        else:
            logger.error("ExportControllerが初期化されていません")
            QMessageBox.warning(
                self, "エラー", "ExportControllerが初期化されていないため、エクスポートを開始できません。"
            )

    def _create_main_tab_widget(self) -> None:
        """
        トップレベルタブウィジェット作成（Phase 2.5）

        重要:
            setup_custom_widgets()より前に呼び出す必要がある。
            既存のcentralwidgetレイアウトをトップレベルタブに再構成する。

        Note:
            ワークスペースタブでは右カラムのアノテーション制御（groupBoxAnnotationControl）を
            非表示にする。バッチタグ機能はバッチタグタブに移動したため。

        Raises:
            RuntimeError: タブ作成に失敗した場合
        """
        try:
            self.tabWidgetMainMode = TabReorganizationService.create_main_tab_widget()
            self.tabWidgetMainMode.setParent(self)
            TabReorganizationService.reorganize_main_window_layout(self)
            self.tabWidgetMainMode.currentChanged.connect(self._on_main_tab_changed)

            # ワークスペースタブでアノテーション制御を非表示にする
            # バッチタグ機能はバッチタグタブに移動したため
            self._hide_annotation_control_in_workspace()

            logger.info("Main tab widget created successfully")
        except Exception as e:
            logger.error(f"Failed to create main tab widget: {e}", exc_info=True)
            self._handle_critical_initialization_failure(
                "Main tab widget creation failed", RuntimeError(f"Tab widget creation error: {e}")
            )

    def _hide_annotation_control_in_workspace(self) -> None:
        """
        ワークスペースタブでアノテーション制御を非表示にする

        右パネル（framePreviewDetailPanel）内のgroupBoxAnnotationControlを非表示にする。
        バッチタグ機能はトップレベルのバッチタグタブに移動したため、
        ワークスペースタブでは不要。

        Note:
            groupBoxAnnotationControlはMainWindow.uiで定義されている。
            hide()で非表示にし、ウィジェットは削除しない（将来の復元可能性のため）。
        """
        if hasattr(self, "groupBoxAnnotationControl") and self.groupBoxAnnotationControl:
            self.groupBoxAnnotationControl.hide()
            logger.info("Hidden groupBoxAnnotationControl in workspace tab")
        else:
            logger.debug("groupBoxAnnotationControl not found, skipping hide")

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
