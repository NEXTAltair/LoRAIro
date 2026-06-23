# src/lorairo/gui/window/main_window.py

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QResizeEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsOpacityEffect,
    QMainWindow,
    QMenu,
    QMessageBox,
    QTabWidget,
    QWidget,
)

from ...database.db_core import IMG_DB_PATH, get_current_project_root, get_user_tag_db_path
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
from ..state.staging_state import StagingStateManager
from ..tab.annotate_tab import AnnotateTabWidget
from ..tab.cli_tab import CliTabWidget
from ..tab.errors_tab import ErrorsTabWidget
from ..tab.export_tab import ExportTabWidget
from ..tab.map_tab import MapTabWidget
from ..tab.results_tab import ResultsTabWidget
from ..widgets.error_notification_widget import ErrorNotificationWidget
from ..widgets.filter_search_panel import FilterSearchPanel
from ..widgets.image_preview import ImagePreviewWidget
from ..widgets.provider_batch_job_widget import ProviderBatchJobWidget
from ..widgets.quick_tag_dialog import QuickTagDialog
from ..widgets.registration_summary_widget import RegistrationSummaryWidget
from ..widgets.selected_image_details_widget import SelectedImageDetailsWidget
from ..widgets.tag_management_dialog import TagManagementDialog
from ..widgets.thumbnail import ThumbnailSelectorWidget


class MainWindow(QMainWindow, Ui_MainWindow):
    """
    メインワークスペースウィンドウ。
    データベース中心の設計で、画像の管理・検索・処理を統合的に提供。
    """

    # QSettings バージョン（UI構造変更時にインクリメント）
    # 2: Wireframes v11 · 6 タブ化（検索/マップ/アノテーション/ジョブ/結果/エラー）
    # 3: Wireframes v11 Phase 5 · エクスポートタブ追加（7 タブ化）
    # 4: #863 アノテタブ1カラム化（splitterBatchTagMain 縦）· 旧 (横) 保存状態を破棄
    SETTINGS_VERSION = 4

    # シグナル
    dataset_loaded = Signal(str)  # dataset_path
    database_registration_completed = Signal(int)  # registered_count

    # サービス属性の型定義（初期化で設定）
    config_service: ConfigurationService | None
    file_system_manager: FileSystemManager | None
    db_manager: ImageDatabaseManager | None
    worker_service: WorkerService | None
    dataset_state_manager: DatasetStateManager | None
    staging_state_manager: StagingStateManager | None

    # Service/Controller層属性
    selection_state_service: SelectionStateService | None
    dataset_controller: DatasetController | None
    annotation_workflow_controller: AnnotationWorkflowController | None
    settings_controller: SettingsController | None
    export_tab: ExportTabWidget | None
    annotate_tab: AnnotateTabWidget | None
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
    provider_batch_job_widget: ProviderBatchJobWidget | None

    # Tab widget (programmatically created)
    tabWidgetMainMode: QTabWidget

    # Error handling UI components
    error_notification_widget: ErrorNotificationWidget | None
    errors_tab: ErrorsTabWidget | None
    results_tab: ResultsTabWidget | None

    # Map tab
    map_tab: MapTabWidget | None

    # 登録完了サマリパネル (Wireframes v11 Frame 1)
    registration_summary_widget: RegistrationSummaryWidget | None

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

            # タグ管理メニューアクション追加（ツールメニューへ）
            if hasattr(self, "menuTools"):
                self.actionTagManagement = QAction("未分類タグの整理", self)
                self.actionTagManagement.setShortcut("Ctrl+Shift+T")
                self.actionTagManagement.triggered.connect(self._show_tag_management_dialog)
                self.menuTools.addAction(self.actionTagManagement)
                logger.debug("Tag management menu action added to Tools menu")

            # Batch APIインポートメニューアクション追加
            if hasattr(self, "menuFile"):
                self.actionBatchImport = QAction("Batch API結果インポート...", self)
                self.actionBatchImport.setShortcut("Ctrl+Shift+I")
                self.actionBatchImport.triggered.connect(self._start_batch_import)
                self.menuFile.addAction(self.actionBatchImport)
                logger.debug("Batch import menu action added")

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

        # ステージング集合の SSoT (Annotate / Jobs タブが共有する、ADR 0074)
        self._initialize_staging_state_manager()

        # DBステータス表示を現在のプロジェクトディレクトリに更新
        self._update_database_status_label()

        logger.info("サービス初期化完了")

    def _initialize_staging_state_manager(self) -> None:
        """ステージング集合の SSoT (StagingStateManager) を初期化する (ADR 0074)。

        fan-out 元を manager 一本に集約し、各タブの widget シグナルでの二重発火を避ける。
        """
        try:
            self.staging_state_manager = StagingStateManager()
            if self.dataset_state_manager is not None:
                self.staging_state_manager.set_dataset_state_manager(self.dataset_state_manager)
            self.staging_state_manager.staged_images_changed.connect(self._on_staged_images_changed)
            self.staging_state_manager.staging_cleared.connect(self._handle_staging_cleared)
            logger.info("✅ StagingStateManager初期化成功")
        except Exception as e:
            logger.error(f"❌ StagingStateManager初期化失敗: {e}")
            self.staging_state_manager = None

    def _update_database_status_label(self) -> None:
        """ステータスバーのDB表示を現在のプロジェクトディレクトリに合わせる"""
        if not hasattr(self, "labelDbInfo") or self.labelDbInfo is None:
            return

        try:
            project_root = get_current_project_root().resolve()
            image_db_path = IMG_DB_PATH.resolve()
            tooltip_lines = [f"画像DB: {image_db_path}"]

            tag_db_path = get_user_tag_db_path()
            if tag_db_path:
                tooltip_lines.append(f"タグDB: {tag_db_path.resolve()}")

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
                db_repository=self.db_manager.image_repo if self.db_manager else None,
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

            logger.info("✅ Service/Controller層初期化完了")
        except Exception as e:
            logger.error(f"❌ Controller初期化失敗: {e}")
            self.selection_state_service = None
            self.dataset_controller = None
            self.annotation_workflow_controller = None
            self.settings_controller = None

        # ErrorNotificationWidget初期化（Phase 4.5）
        self._setup_error_notification()

        # アノテーションタブ (AnnotateTabWidget) を tabBatchTag へ埋め込む (#868)
        self._setup_annotate_tab()

        # QTabWidget初期化（タブ切り替え用）
        self._setup_tab_widget()
        self._setup_map_tab()
        self._setup_provider_batch_tab()
        self._setup_results_tab()
        self._setup_errors_tab()
        self._setup_export_tab()
        self._setup_cli_tab()
        self._setup_tab_shortcuts()
        self._setup_registration_summary_panel()

    def _setup_map_tab(self) -> None:
        """マップタブ (MapTabWidget) を初期化する。

        固有の配置・振る舞いは MapTabWidget が所有し、MainWindow は .ui の
        tabMap コンテナへ埋め込み db_manager を注入するだけ (glue)。
        """
        container = getattr(self, "tabMap", None)
        if container is None:
            logger.warning("tabMap not found - マップタブ skipped")
            self.map_tab = None
            return
        if self.db_manager is None:
            logger.warning("db_manager 未初期化 - マップタブ skipped")
            self.map_tab = None
            return
        try:
            layout = container.layout()
            if layout is not None:
                while layout.count():
                    item = layout.takeAt(0)
                    w = item.widget() if item else None
                    if w is not None:
                        w.deleteLater()
            else:
                from PySide6.QtWidgets import QVBoxLayout

                layout = QVBoxLayout(container)
            widget = MapTabWidget(db_manager=self.db_manager, parent=container)
            layout.addWidget(widget)
            self.map_tab = widget
            logger.info("マップタブ (MapTabWidget) initialized")
        except Exception as e:
            self.map_tab = None
            logger.error(f"マップタブ initialization failed: {e}", exc_info=True)

    def _setup_registration_summary_panel(self) -> None:
        """登録完了サマリパネルを Search タブ上部 (qbar の上) へ常設する。

        Wireframes v11 Frame 1。statusBar の 5 秒表示を置換し、registered /
        variant / skipped / errors と重複 / 別版の内訳を ✕ で閉じるまで表示する。
        """
        container = getattr(self, "tabWorkspace", None)
        layout = container.layout() if container is not None else None
        if layout is None:
            logger.warning("tabWorkspace layout not found - 登録完了サマリパネル skipped")
            self.registration_summary_widget = None
            return
        widget = RegistrationSummaryWidget(parent=container)
        widget.view_image_requested.connect(self._on_registration_view_image_requested)
        # work area splitter (qbar を含む) の直前へ挿入する = qbar の上
        insert_index = layout.count()
        splitter = getattr(self, "splitterMainWorkArea", None)
        if splitter is not None:
            idx = layout.indexOf(splitter)
            if idx != -1:
                insert_index = idx
        layout.insertWidget(insert_index, widget)
        self.registration_summary_widget = widget
        logger.info("✅ 登録完了サマリパネル (RegistrationSummaryWidget) initialized")

    def _on_registration_view_image_requested(self, image_id: int) -> None:
        """登録完了サマリの「#N を表示」リンク → 該当画像を詳細表示する。"""
        tab_widget = getattr(self, "tabWidgetMainMode", None)
        workspace = getattr(self, "tabWorkspace", None)
        if tab_widget is not None and workspace is not None:
            tab_widget.setCurrentWidget(workspace)
        if self.dataset_state_manager is not None:
            self.dataset_state_manager.set_current_image(image_id)

    def _setup_provider_batch_tab(self) -> None:
        """ジョブタブ (Provider Batch job management) を追加する。

        Wireframes v11 ナビ順（検索 / マップ / アノテーション / ジョブ / 結果 / エラー）
        に従い、結果タブ (tabResults) の直前へ挿入する。
        """
        if not hasattr(self, "tabWidgetMainMode") or not self.tabWidgetMainMode:
            logger.warning("tabWidgetMainMode not found - ジョブタブ skipped")
            self.provider_batch_job_widget = None
            return

        try:
            widget = ProviderBatchJobWidget(parent=self.tabWidgetMainMode)
            widget.set_dataset_state_manager(self.dataset_state_manager)
            service_container = self.service_container
            widget.set_dependencies(
                workflow_service=service_container.provider_batch_workflow_service,
                repository=service_container.db_manager.provider_batch_repo,
                model_source=service_container.annotator_library,
                model_repository=service_container.db_manager.model_repo,
            )
            # 共有 SSoT を注入 (Annotate タブと同一の StagingStateManager を共有、ADR 0074)。
            # fan-out は staging_state_manager 側で一括接続済みのため widget シグナルは繋がない。
            if self.staging_state_manager is not None:
                widget.set_staging_state_manager(self.staging_state_manager)
            # ADR 0066: 同期ジョブ台帳 (実行中/履歴) を Jobs タブへ接続
            if self.worker_service:
                widget.set_job_ledger(self.worker_service.job_ledger)
                self.worker_service.job_ledger_changed.connect(widget.refresh_sync_jobs)
                widget.sync_job_cancel_requested.connect(self._on_sync_job_cancel_requested)
            self.provider_batch_job_widget = widget
            insert_index = self.tabWidgetMainMode.indexOf(self.tabResults)
            self.tabWidgetMainMode.insertTab(insert_index, widget, "ジョブ")
            logger.info("✅ ジョブタブ (Provider Batch) initialized")
        except Exception as e:
            self.provider_batch_job_widget = None
            logger.error(f"❌ ジョブタブ initialization failed: {e}", exc_info=True)

    def _on_sync_job_cancel_requested(self, job_id: str) -> None:
        """Jobs タブの同期ジョブ行からのキャンセル要求 (ADR 0066 §4)。

        進捗ポップアップ廃止に伴い、キャンセル操作は Jobs 行のボタンへ移設された。

        Args:
            job_id: 台帳の job_id (= worker_id)。
        """
        if not self.worker_service:
            logger.warning("WorkerService未初期化 - ジョブキャンセルをスキップ")
            return
        if self.worker_service.cancel_job(job_id):
            self.statusBar().showMessage(f"ジョブをキャンセルしています: {job_id}", 5000)
        else:
            logger.warning(f"ジョブキャンセル要求に失敗: {job_id}")

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

            # クリックでエラータブへ遷移
            self.error_notification_widget.clicked.connect(self._on_error_notification_clicked)

            # Dialog初期化（遅延生成）
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

    def _setup_tab_shortcuts(self) -> None:
        """「移動」メニューと Ctrl+1〜N のタブ切替を登録する。

        Wireframes v11 のナビショートカット (⌘1–⌘8) に対応する。8 タブを
        メニューからも到達できるようにし、旧ツールメニューにあったタブ重複導線
        （アノテーション / エクスポート / エラーログ）を置き換える。各アクションが
        Ctrl+N ショートカットを保持するため、別途 QShortcut は登録しない。
        """
        if not hasattr(self, "tabWidgetMainMode") or not self.tabWidgetMainMode:
            logger.warning("tabWidgetMainMode not found - 移動メニュー skipped")
            return
        navigate_menu = QMenu("移動", self)
        for i in range(self.tabWidgetMainMode.count()):
            action = QAction(self.tabWidgetMainMode.tabText(i), self)
            action.setShortcut(QKeySequence(f"Ctrl+{i + 1}"))
            action.triggered.connect(partial(self.tabWidgetMainMode.setCurrentIndex, i))
            navigate_menu.addAction(action)
        # 「表示」と「ツール」の間（ツールメニューの直前）へ挿入する
        tools_action = self.menuTools.menuAction() if hasattr(self, "menuTools") else None
        if tools_action is not None:
            self.menuBar().insertMenu(tools_action, navigate_menu)
        else:
            self.menuBar().addMenu(navigate_menu)
        self.menuNavigate = navigate_menu
        logger.debug(f"移動メニュー登録: Ctrl+1..Ctrl+{self.tabWidgetMainMode.count()}")

    def _setup_results_tab(self) -> None:
        """結果タブに ResultsTabWidget を埋め込む。

        Wireframes v11 Frame 5 · Results。Phase 1 のスタブラベルを除去し、
        固有の振る舞いを持つ ResultsTabWidget を常設する。MainWindow は .ui の
        tabResults コンテナへ埋め込み、依存を注入するだけ (glue, #870)。
        """
        container = getattr(self, "tabResults", None)
        if container is None:
            logger.warning("tabResults not found - results tab skipped")
            self.results_tab = None
            return

        # Phase 1 スタブラベルを除去（setParent(None) で即座に tabResults から切り離す）
        stub = getattr(self, "labelResultsStub", None)
        if stub is not None:
            container.layout().removeWidget(stub)
            stub.setParent(None)
            stub.deleteLater()

        widget = ResultsTabWidget(
            db_manager=self.db_manager,
            staging_state_manager=self.staging_state_manager,
            parent=container,
        )
        container.layout().addWidget(widget)
        self.results_tab = widget
        logger.info("✅ 結果タブ (ResultsTabWidget) initialized")

    def _setup_errors_tab(self) -> None:
        """エラータブに ErrorsTabWidget を埋め込む。

        Wireframes v11 Frame 4 · Errors。固有の振る舞いを持つ ErrorsTabWidget を
        .ui の tabErrors コンテナへ埋め込み、依存を注入するだけ (glue, #871)。
        resolve 時の statusBar 通知バッジ更新は errors_resolved シグナル経由で行う。
        """
        container = getattr(self, "tabErrors", None)
        if container is None:
            logger.warning("tabErrors not found - errors tab skipped")
            self.errors_tab = None
            return

        widget = ErrorsTabWidget(db_manager=self.db_manager, parent=container)
        widget.errors_resolved.connect(self._update_error_notification_count)
        container.layout().addWidget(widget)
        self.errors_tab = widget
        logger.info("✅ エラータブ (ErrorsTabWidget) initialized")

    def _update_error_notification_count(self) -> None:
        """statusBar のエラー通知バッジ件数を再計算する。"""
        if self.error_notification_widget:
            self.error_notification_widget.update_error_count()

    def _setup_export_tab(self) -> None:
        """エクスポートタブに ExportTabWidget を常設する。

        Wireframes v11 Frame 7 · Export (Phase 5)。対象 = ステージング集合
        (ADR 0055/0019)。初期対象は現在のステージングから読み、以降は
        ``staged_images_changed`` → ``set_image_ids`` でライブ更新する。.ui の
        tabExport コンテナへ埋め込み依存を注入するだけ (glue, #872)。
        """
        container = getattr(self, "tabExport", None)
        if container is None:
            logger.warning("tabExport not found - export tab skipped")
            self.export_tab = None
            return

        widget = ExportTabWidget(
            service_container=self.service_container,
            initial_image_ids=self._get_staged_export_ids(),
            parent=container,
        )
        container.layout().addWidget(widget)
        self.export_tab = widget
        logger.info("✅ エクスポートタブ (ExportTabWidget) initialized")

    def _setup_cli_tab(self) -> None:
        """CLI タブ (CliTabWidget) をナビ末尾に追加する。

        Wireframes v11 Frame 8。agent-friendly CLI 契約 (ADR 0057-0060) を
        読み物として図解する読み取り専用リファレンス。DB 接続不要のため
        依存注入はなく、コンテンツは初回表示時に遅延生成される。MainWindow は
        タブを末尾へ追加するだけ (glue)。
        """
        if not hasattr(self, "tabWidgetMainMode") or not self.tabWidgetMainMode:
            logger.warning("tabWidgetMainMode not found - CLIタブ skipped")
            self.cli_tab = None
            return

        widget = CliTabWidget(parent=self.tabWidgetMainMode)
        self.tabWidgetMainMode.addTab(widget, "CLI")
        self.cli_tab = widget
        logger.info("✅ CLIタブ (CliTabWidget) initialized")

    def _setup_annotate_tab(self) -> None:
        """アノテーションタブに AnnotateTabWidget を埋め込む (Epic #867 / #868)。

        Wireframes v11 Frame 2 · Annotate。パイプライン構成ビュー・モデル選択 SSoT・
        stage ピッカー往復・preset 配線・送信前プリフライト・推論台帳・run bar・
        batch tag フローを AnnotateTabWidget が所有する。MainWindow は .ui の
        tabBatchTag コンテナへ埋め込み依存を注入し、横断 glue (worker dispatch /
        settings / staging fan-out) だけを残す (glue)。
        """
        container = getattr(self, "tabBatchTag", None)
        if container is None:
            logger.warning("tabBatchTag not found - アノテーションタブ skipped")
            self.annotate_tab = None
            return

        widget = AnnotateTabWidget(
            service_container=self.service_container,
            db_manager=self.db_manager,
            staging_state_manager=self.staging_state_manager,
            dataset_state_manager=self.dataset_state_manager,
            parent=container,
        )
        container.layout().addWidget(widget)
        self.annotate_tab = widget
        logger.info("✅ アノテーションタブ (AnnotateTabWidget) initialized")

    def _on_error_notification_clicked(self) -> None:
        """エラー通知 / メニュー操作でエラータブへ遷移する。"""
        self.tabWidgetMainMode.setCurrentWidget(self.tabErrors)

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

    def _connect_thumbnail_preview_signals(self) -> None:
        """サムネイル→プレビュー間の Signal 接続を行う。"""
        if not (self.thumbnail_selector and self.image_preview_widget):
            return
        try:
            self.thumbnail_selector.image_selected.connect(self.image_preview_widget.load_image)
            if hasattr(self.thumbnail_selector, "stage_selected_requested"):
                self.thumbnail_selector.stage_selected_requested.connect(self.send_selected_to_batch_tag)
            if hasattr(self.thumbnail_selector, "quick_tag_requested"):
                self.thumbnail_selector.quick_tag_requested.connect(self._show_quick_tag_dialog)
            logger.info("    ✅ サムネイル→プレビュー接続完了")
        except Exception as e:
            logger.error(f"    ❌ サムネイル→プレビュー接続失敗: {e}")

    def _connect_menu_actions(self) -> None:
        """ファイル/編集/ヘルプメニューのアクション Signal 接続を行う。"""
        # ファイル: 終了 / ヘルプ: about（thumbnail_selector 非依存なので先に接続）
        if hasattr(self, "actionExit"):
            self.actionExit.triggered.connect(self.close)
        if hasattr(self, "actionAbout"):
            self.actionAbout.triggered.connect(self._show_about_dialog)
        if not self.thumbnail_selector:
            return
        try:
            if hasattr(self, "actionSelectAll"):
                self.actionSelectAll.triggered.connect(self.thumbnail_selector._select_all_items)
            if hasattr(self, "actionDeselectAll"):
                self.actionDeselectAll.triggered.connect(self.thumbnail_selector._deselect_all_items)
            logger.info("    ✅ 編集メニュー（全選択/選択解除）接続完了")
        except Exception as e:
            logger.error(f"    ❌ 編集メニュー接続失敗: {e}")

    def _show_about_dialog(self) -> None:
        """「LoRAIroについて」ダイアログを表示する。"""
        QMessageBox.about(
            self,
            "LoRAIroについて",
            "LoRAIro — LoRA 学習用データセット管理ツール",
        )

    def _connect_details_widget_signals(self) -> None:
        """SelectedImageDetailsWidget の Rating/Score シグナル接続を行う。"""
        if not hasattr(self, "selectedImageDetailsWidget"):
            return
        try:
            self.selectedImageDetailsWidget.rating_changed.connect(self._handle_rating_changed)
            self.selectedImageDetailsWidget.score_changed.connect(self._handle_score_changed)
            self.selectedImageDetailsWidget.batch_rating_changed.connect(self._handle_batch_rating_changed)
            self.selectedImageDetailsWidget.batch_score_changed.connect(self._handle_batch_score_changed)
            logger.info("    ✅ SelectedImageDetailsWidget シグナル接続完了")
        except Exception as e:
            logger.error(f"    ❌ SelectedImageDetailsWidget シグナル接続失敗: {e}")

    def _connect_dataset_state_signals(self) -> None:
        """DatasetStateManager の選択変更シグナル接続を行う。"""
        if not self.dataset_state_manager:
            return
        try:
            self.dataset_state_manager.selection_changed.connect(self._handle_selection_changed_for_rating)
            logger.info("    ✅ DatasetStateManager selection_changed シグナル接続完了")
        except Exception as e:
            logger.error(f"    ❌ DatasetStateManager selection_changed 接続失敗: {e}")

    def _connect_batch_tag_signals(self) -> None:
        """AnnotateTabWidget の glue シグナル接続を行う (#868)。

        ステージング集合の fan-out は StagingStateManager 側で一括接続済み
        (ADR 0074) のため、タブが再公開する ``staged_images_changed`` /
        ``staging_cleared`` は繋がない (二重発火回避)。タブ → MainWindow の
        横断 glue シグナルのみ接続する。
        """
        if self.annotate_tab is None:
            return
        try:
            self.annotate_tab.tag_add_requested.connect(self._handle_batch_tag_add)
            self.annotate_tab.annotation_execute_requested.connect(self.start_annotation)
            self.annotate_tab.configure_key_requested.connect(self._on_annotate_configure_key_requested)
            logger.info("    ✅ AnnotateTabWidget シグナル接続完了")
        except Exception as e:
            logger.error(f"    ❌ AnnotateTabWidget シグナル接続失敗: {e}")

    def _on_annotate_configure_key_requested(self, provider: str) -> None:
        """アノテタブの ``○ needs key`` チップ → 設定の該当プロバイダ欄へ誘導する (#755/#868)。

        旧 ``_on_picker_configure_key_requested`` の MainWindow 側ハンドラ。ピッカー
        本体は AnnotateTabWidget が所有するため、ここでは設定ダイアログを開き、
        キー保存後にモデル一覧とタブを再評価させる薄い glue だけを担う。

        Args:
            provider: API キーが必要な provider 名 (例 ``"anthropic"``)。
        """
        if not self.settings_controller:
            logger.warning("SettingsController 未初期化のため API キー設定導線をスキップします")
            return
        settings_applied = self.settings_controller.open_settings_dialog(highlight_provider=provider)
        if not settings_applied:
            return
        self._reload_model_widget_after_settings()
        if self.annotate_tab is not None:
            self.annotate_tab.refresh()

    def _connect_settings_signals(self) -> None:
        """設定ダイアログを開くアクション・ボタンの Signal 接続を行う。"""
        if hasattr(self, "actionSettings"):
            self.actionSettings.triggered.connect(self.open_settings)
        if hasattr(self, "pushButtonSettings"):
            self.pushButtonSettings.clicked.connect(self.open_settings)

    def _connect_events(self) -> None:
        """イベント接続を設定（安全な実装）"""
        try:
            logger.info("  - イベント接続開始...")
            self._connect_thumbnail_preview_signals()
            self._connect_menu_actions()
            self._setup_worker_pipeline_signals()
            self._connect_details_widget_signals()
            self._connect_dataset_state_signals()
            self._connect_batch_tag_signals()
            self._connect_settings_signals()
            self._connect_export_entry_signals()
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
            "batch_registration_started",
            "batch_registration_finished",
            "batch_registration_error",
            "batch_registration_canceled",
            "batch_import_finished",
            "batch_import_error",
            "batch_import_canceled",
            "enhanced_annotation_finished",
            "enhanced_annotation_error",
            "enhanced_annotation_canceled",
            "worker_progress_updated",
            "worker_batch_progress",
            "operation_event",
        ]

        missing_signals = [
            signal for signal in required_signals if not hasattr(self.worker_service, signal)
        ]

        if missing_signals:
            logger.error(f"WorkerService missing required signals: {missing_signals}")
            return

        # Search/thumbnail pipeline lifecycle is driven by operation events.
        self.worker_service.operation_event.connect(self._on_worker_operation_event)

        # Batch registration connections
        self.worker_service.batch_registration_started.connect(self._on_batch_registration_started)
        self.worker_service.batch_registration_finished.connect(self._on_batch_registration_finished)
        self.worker_service.batch_registration_error.connect(self._on_batch_registration_error)
        self.worker_service.batch_registration_canceled.connect(self._on_batch_registration_canceled)

        # Batch import connections
        self.worker_service.batch_import_finished.connect(self._on_batch_import_finished)
        self.worker_service.batch_import_error.connect(self._on_batch_import_error)
        self.worker_service.batch_import_canceled.connect(self._on_batch_import_canceled)

        # Annotation connections
        self.worker_service.enhanced_annotation_finished.connect(self._on_annotation_finished)
        self.worker_service.enhanced_annotation_error.connect(self._on_annotation_error)
        self.worker_service.enhanced_annotation_canceled.connect(self._on_annotation_canceled)

        # ADR 0066 §4: 進捗ポップアップ廃止 — 開始通知は statusbar のみ (自動タブ遷移はしない)
        self.worker_service.enhanced_annotation_started.connect(self._on_sync_job_started_notify)
        self.worker_service.batch_import_started.connect(self._on_sync_job_started_notify)

        # Progress feedback connections
        self.worker_service.worker_progress_updated.connect(self._on_worker_progress_updated)
        self.worker_service.worker_batch_progress.connect(self._on_worker_batch_progress)

        logger.info("WorkerService pipeline signals connected")

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

    def _on_pipeline_search_canceled(self, worker_id: str) -> None:
        self._delegate_to_pipeline_control("on_search_canceled", worker_id)

    def _on_pipeline_thumbnail_canceled(self, worker_id: str) -> None:
        self._delegate_to_pipeline_control("on_thumbnail_canceled", worker_id)

    def _on_worker_terminal(self, event: Any) -> None:
        """Route terminal events with outcome and reason details."""
        self._delegate_to_pipeline_control("on_worker_terminal", event)

    def _on_worker_operation_event(self, event: Any) -> None:
        """Route operation lifecycle events to pipeline control."""
        self._delegate_to_pipeline_control("on_operation_event", event)
        operation_type = getattr(getattr(event, "operation_type", None), "value", None)
        if (
            operation_type in {"search", "thumbnail"}
            and getattr(event, "is_current", False)
            and getattr(event, "outcome", None)
            and getattr(event.outcome, "value", None)
            in {
                "failed",
                "terminated",
                "unresponsive",
            }
        ):
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
                result,
                status_bar=self.statusBar(),
                completion_signal=self.database_registration_completed,
                summary_widget=getattr(self, "registration_summary_widget", None),
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

    def _on_batch_registration_canceled(self, worker_id: str) -> None:
        """Batch registration canceled signal handler（エラー通知は出さない）"""
        self._delegate_to_progress_state("on_batch_registration_canceled", worker_id)

    def _on_sync_job_started_notify(self, worker_id: str) -> None:
        """同期ジョブ開始の statusbar 通知 (ADR 0066 §4: ポップアップ代替)。

        Args:
            worker_id: 開始したワーカーID。進捗・キャンセルはジョブタブで扱う。
        """
        self.statusBar().showMessage("処理を開始しました（進捗はジョブタブで確認できます）", 8000)
        logger.debug(f"同期ジョブ開始通知: {worker_id}")

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
        """アノテーション完了ハンドラ（サマリーダイアログ + キャッシュ更新）

        Args:
            result: AnnotationExecutionResult または PHashAnnotationResults（後方互換）

        Note:
            - Phase 1: サマリーダイアログ表示
            - Phase 2: 検索結果キャッシュ更新（選択中画像の詳細パネル反映）
        """
        from image_annotator_lib import PHashAnnotationResults

        from lorairo.gui.widgets.annotation_summary_dialog import AnnotationSummaryDialog
        from lorairo.gui.workers.annotation_worker import AnnotationExecutionResult

        # Phase 1: サマリーダイアログ表示
        raw_results: PHashAnnotationResults | None = None
        if isinstance(result, AnnotationExecutionResult):
            dialog = AnnotationSummaryDialog(result, parent=self)
            dialog.exec()
            raw_results = result.results
        else:
            # 後方互換: 旧形式の生dict（PHashAnnotationResults は dict サブクラス）
            self._delegate_to_result_handler(
                "handle_annotation_finished", result, status_bar=self.statusBar()
            )
            raw_results = cast(PHashAnnotationResults, result) if isinstance(result, dict) else None

        # Phase 2: 検索結果キャッシュ更新
        # ワークスペースタブで選択中の画像がアノテーション対象に含まれていた場合、
        # 詳細パネル（SelectedImageDetailsWidget）に最新情報が反映される
        if not self.dataset_state_manager or not self.db_manager:
            return

        if raw_results and isinstance(raw_results, dict):
            try:
                # #633: 同一 pHash に別版 (複数 image_id) が紐づき得るため、全 image_id を更新する。
                phash_to_image_ids = self.db_manager.image_repo.find_image_ids_by_phashes_multi(
                    set(raw_results.keys())
                )
                image_ids = [
                    img_id for ids in phash_to_image_ids.values() for img_id in ids if img_id is not None
                ]

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

    def _on_annotation_canceled(self, worker_id: str) -> None:
        """Annotation canceled signal handler（エラー通知は出さない）"""
        self._delegate_to_progress_state("on_batch_annotation_canceled", worker_id)

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

            # Issue #792: タグ soft-reject / 復活 / 手動追加の編集モードを有効化
            if hasattr(self.selected_image_details_widget, "set_db_manager"):
                self.selected_image_details_widget.set_db_manager(self.db_manager)

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
            # ステージング集合をクリア (SSoT = StagingStateManager、fan-out で各タブへ反映)
            if self.staging_state_manager is not None:
                self.staging_state_manager.clear()

            self.statusBar().showMessage(f"タグ '{tag}' を {len(image_ids)} 件の画像に追加しました", 5000)
            logger.info(
                f"Batch tag add completed successfully: tag='{tag}', {len(image_ids)} images updated"
            )
        else:
            QMessageBox.critical(self, "タグ追加失敗", f"タグ '{tag}' の追加に失敗しました。")
            logger.error(f"Failed to add tag in batch: tag='{tag}', image_count={len(image_ids)}")

    def _handle_staging_cleared(self) -> None:
        """ステージング集合クリア時のハンドラ (StagingStateManager fan-out、ADR 0074)。

        アノテーションタブ (run bar / pipeline / preflight) とエクスポート対象を
        空集合へ同期する。
        """
        logger.debug("Batch staging cleared")
        self._update_export_target_ui(0)
        if self.annotate_tab is not None:
            self.annotate_tab.set_staging_target([])

    def _on_staged_images_changed(self, image_ids: list[int]) -> None:
        """ステージング画像変更シグナルハンドラ (StagingStateManager fan-out、ADR 0074)。

        エクスポート対象・エクスポートタブ・アノテーションタブをステージング集合へ
        ライブ同期する。アノテ側の run bar / pipeline / preflight 再計算は
        AnnotateTabWidget.set_staging_target() が担う (#868)。

        Args:
            image_ids: 現在のステージング画像IDリスト
        """
        count = len(image_ids) if image_ids else 0
        self._update_export_target_ui(count)
        # Phase 5: エクスポートタブの対象もステージング集合とライブ同期する (ADR 0055)
        export_tab = getattr(self, "export_tab", None)
        if export_tab is not None:
            export_tab.set_image_ids(list(image_ids) if image_ids else [])
        # #868: アノテーションタブ (run bar / pipeline / preflight) をステージング集合と同期
        if self.annotate_tab is not None:
            self.annotate_tab.set_staging_target(list(image_ids) if image_ids else [])

    def _update_export_target_ui(self, staging_count: int) -> None:
        """エクスポート下部バーの対象件数ラベルを更新する。

        ADR 0055: ワークスペースのエクスポート入口の対象＝ステージング集合。
        件数は ``StagingWidget.staged_images_changed``（= ステージング件数）を反映し、
        サムネ選択数ではない。ステージング後にサムネ選択を変更・クリアしても件数は
        ズレない。

        Args:
            staging_count: 現在のステージング画像数。
        """
        if hasattr(self, "labelExportTarget"):
            self.labelExportTarget.setText(f"エクスポート対象: {staging_count} 枚")

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
            repo = service_container.db_manager.model_repo
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

    def _reload_model_widget_after_settings(self) -> None:
        """設定保存後にモデル選択ウィジェットへ最新のキー状況を反映する。

        Issue #249: route_preference 等の保存値を即時反映。
        Issue #755: API キー保存による ● API ready / ○ needs key の更新もここで行う。
        MainWindow.config_service と ServiceContainer.config_service は別インスタンス
        (Codex review PR #757) のため、container 側を破棄して保存済みファイルから
        再読込させてから widget を更新する (widget は container 側を参照する)。
        """
        try:
            container = get_service_container()
            del container.config_service
        except (RuntimeError, AttributeError) as e:
            logger.warning(f"ServiceContainer の config_service 再読込に失敗 (継続可): {e}")

        if self.annotate_tab is None:
            return
        batch_widget = self.annotate_tab.batch_model_selection
        try:
            batch_widget.update_model_display()
            logger.debug("設定変更を反映してモデル選択ウィジェットを更新しました")
        except Exception as e:
            logger.warning(f"モデル選択ウィジェットの更新に失敗 (継続可): {e}")

    def open_settings(self) -> None:
        """設定ウィンドウを開く（SettingsControllerに委譲）"""
        if self.settings_controller:
            settings_applied = self.settings_controller.open_settings_dialog()
            if settings_applied:
                self._reload_model_widget_after_settings()
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

        # アノテーションタブの選択モデルを取得 (Issue #245: litellm_model_id ベース、#868)
        selected_litellm_model_ids: list[str] = []
        if self.annotate_tab is not None:
            selected_litellm_model_ids = self.annotate_tab.selected_litellm_model_ids()
            logger.debug(
                f"アノテタブから選択されたモデル (litellm_model_ids): {selected_litellm_model_ids}"
            )

        # アノテーションタブの場合はステージング画像を使用
        override_image_paths: list[str] | None = None
        if self.tabWidgetMainMode.currentWidget() is self.tabBatchTag:
            override_image_paths = self._get_staged_image_paths_for_annotation()
            if not override_image_paths:
                QMessageBox.information(
                    self,
                    "ステージング画像なし",
                    "ステージングリストに画像がありません。\n"
                    "画像を選択してからアノテーションを実行してください。",
                )
                return

        # #851: stage ピッカーで設定された conf-min 閾値を worker へ伝播する
        # (litellm_model_id → 閾値)。RunOptions には混ぜず別 dict で渡す。
        confidence_thresholds: dict[str, float] = {}
        if self.annotate_tab is not None:
            confidence_thresholds = self.annotate_tab.stage_confidence_thresholds()

        # AnnotationWorkflowControllerに委譲（チェックボックスから選択されたモデルを優先）
        self.annotation_workflow_controller.start_annotation_workflow(
            selected_litellm_model_ids=selected_litellm_model_ids if selected_litellm_model_ids else None,
            model_selection_callback=self._show_model_selection_dialog
            if not selected_litellm_model_ids
            else None,
            image_paths=override_image_paths,
            confidence_thresholds=confidence_thresholds or None,
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
        """アノテーションタブのステージング画像パスを取得

        AnnotateTabWidget.get_staged_items() で画像 ID とメタデータを取得し、
        DatasetStateManager 由来の stored_path を実際のファイルパスに解決する。

        Returns:
            list[str]: 画像ファイルパスリスト。エラー時は空リスト。
        """
        from lorairo.database.db_core import resolve_stored_path

        staged_items = self.annotate_tab.get_staged_items() if self.annotate_tab is not None else None
        if not staged_items:
            return []

        if not self.dataset_state_manager:
            logger.warning("DatasetStateManager not available for path resolution")
            return []

        paths: list[str] = []
        for image_id, (_, stored_path) in staged_items.items():
            if stored_path:
                resolved = resolve_stored_path(stored_path)
                if resolved and resolved.exists():
                    paths.append(str(resolved))
                else:
                    logger.debug(f"画像パスが存在しない: ID={image_id}, path={stored_path}")

        logger.debug(f"ステージング画像パスを取得: {len(paths)}件")
        return paths

    def _connect_export_entry_signals(self) -> None:
        """エクスポート/アノテーション入口（ツールバー・下部バー）の Signal 接続を行う。

        ADR 0055: ワークスペースに常設のエクスポート入口（ツールバー action と
        サムネグリッド下部バーのボタン）を追加する。対象解決ロジックは変更せず、
        既存の ``export_data()``（エクスポートタブ遷移）に委譲する（新しい選択解決
        パスを足さない）。
        """
        try:
            # サムネグリッド下部バーのエクスポートボタン（triggered の bool ペイロードは無視する）
            if hasattr(self, "btnExportData"):
                self.btnExportData.clicked.connect(self._on_export_entry_triggered)
            # 下部バーの件数表示を初期化（起動直後のステージング件数 0）
            self._update_export_target_ui(0)
            logger.info("    ✅ エクスポート入口 Signal 接続完了")
        except Exception as e:
            logger.error(f"    ❌ エクスポート入口 Signal 接続失敗: {e}")

    def _on_export_entry_triggered(self, _checked: bool = False) -> None:
        """エクスポート入口（ツールバー action / 下部バーボタン）のハンドラ。

        ``QAction.triggered`` / ``QPushButton.clicked`` が渡す bool ペイロードは
        画像 ID ではないため無視する（ADR 0072 / Issue #570）。対象解決は
        ``export_data()``（エクスポートタブ遷移）に委譲し、新しい選択解決パスを足さない。

        Args:
            _checked: シグナルが渡す checked 状態。意図的に無視する。
        """
        self.export_data()

    def _get_staged_export_ids(self) -> list[int]:
        """エクスポート対象のステージング画像 ID を返す（エクスポートタブの対象ソース）。

        ADR 0055: エクスポート対象＝ステージング集合。SSoT である
        ``StagingStateManager``（ADR 0074）を直接読むことで、下部バーの件数表示と
        実エクスポート対象を一致させる。未初期化の場合は空リストを返す。

        Returns:
            ステージング中の画像 ID リスト（追加順）。未初期化時は空リスト。
        """
        if self.staging_state_manager is None:
            return []
        return self.staging_state_manager.get_image_ids()

    def export_data(self) -> None:
        """エクスポートタブへ遷移する。

        Phase 5 (Wireframes v11 Frame 7): モーダルダイアログからタブ常設に変更。
        遷移前にステージング集合を再読込し、シグナル取りこぼしがあっても
        タブ表示時点の対象件数を正とする。
        """
        export_tab = getattr(self, "export_tab", None)
        if export_tab is None or not hasattr(self, "tabExport"):
            logger.error("エクスポートタブが初期化されていません")
            QMessageBox.warning(
                self, "エラー", "エクスポートタブが初期化されていないため、エクスポートを開けません。"
            )
            return

        export_tab.set_image_ids(self._get_staged_export_ids())
        self.tabWidgetMainMode.setCurrentWidget(self.tabExport)

    def send_selected_to_batch_tag(self, selected_ids: list[int] | bool | None = None) -> None:
        """ワークスペースの選択画像をアノテーションタブのステージングに追加 (#868)。"""
        if not self.dataset_state_manager:
            logger.warning("DatasetStateManager not available")
            QMessageBox.warning(self, "エラー", "データセットが初期化されていません。")
            return

        if self.annotate_tab is None:
            logger.warning("AnnotateTabWidget not found")
            QMessageBox.warning(self, "エラー", "アノテーション機能が初期化されていません。")
            return

        target_ids = (
            selected_ids
            if isinstance(selected_ids, list)
            else self.dataset_state_manager.selected_image_ids
        )
        if not target_ids:
            dataset_selected_count = len(self.dataset_state_manager.selected_image_ids)
            thumbnail_selector_available = bool(getattr(self, "thumbnail_selector", None))
            logger.debug(
                "No image ids resolved for batch tag staging: "
                f"dataset_selected={dataset_selected_count}, "
                f"thumbnail_selector_available={thumbnail_selector_available}"
            )
            QMessageBox.information(self, "選択なし", "バッチタグに追加する画像が選択されていません。")
            return

        # アノテーションタブへ移動 (#844: サブタブ廃止、単一縦カラム)
        if hasattr(self, "tabWidgetMainMode") and self.tabWidgetMainMode:
            self.tabWidgetMainMode.setCurrentWidget(self.tabBatchTag)

        # ステージングへ追加する導線はタブへ委譲 (#868)
        self.annotate_tab.add_image_ids_to_staging(list(target_ids))

    def _setup_main_tab_connections(self) -> None:
        """
        タブウィジェットのSignal接続（UIで定義済みのタブを使用）

        MainWindow.ui で定義された tabWidgetMainMode の Signal 接続を設定し、
        タブ構造の検証を行う。

        Note:
            バッチタグ機能はバッチタグタブに移動済み。
            タブ切り替えは _on_main_tab_changed で処理する。
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
        """メインタブ切り替えハンドラ。

        タブ構成変更（Wireframes v11 · 6 タブ化）に耐えるよう、index の
        マジックナンバーではなく widget 同一性で分岐する。

        Args:
            index: 切り替え先のタブインデックス。
        """
        current = self.tabWidgetMainMode.widget(index)
        if current is getattr(self, "tabBatchTag", None):
            logger.info("Switched to Annotate tab")
            self._refresh_batch_tag_staging()
        elif self.provider_batch_job_widget is not None and current is self.provider_batch_job_widget:
            logger.info("Switched to Jobs tab")
            self.provider_batch_job_widget.refresh_jobs()
        elif current is getattr(self, "tabResults", None):
            logger.info("Switched to Results tab")
            if self.results_tab is not None:
                self.results_tab.refresh()
        elif current is getattr(self, "tabErrors", None):
            logger.info("Switched to Errors tab")
            if self.errors_tab is not None:
                self.errors_tab.refresh()
        elif current is getattr(self, "tabExport", None):
            logger.info("Switched to Export tab")
            # ステージング集合を再読込（シグナル取りこぼしの安全網、ADR 0055）
            export_tab = getattr(self, "export_tab", None)
            if export_tab is not None:
                export_tab.set_image_ids(self._get_staged_export_ids())

    def _refresh_batch_tag_staging(self) -> None:
        """アノテーションタブ表示時の再計算をタブへ委譲する (#868)。

        ステージングリスト・run bar・pipeline・preflight の再描画は
        AnnotateTabWidget.refresh() が担う。
        """
        if self.annotate_tab is None:
            logger.warning("AnnotateTabWidget not found, skipping staging refresh")
            return
        self.annotate_tab.refresh()
        logger.debug("Annotate tab refreshed")

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
        ]

        restored_any = False
        for attr_name, settings_key in splitters:
            splitter = getattr(self, attr_name, None)
            if splitter:
                state = settings.value(settings_key)
                if state:
                    # QSplitter.restoreState() は sizes だけでなく orientation も
                    # 復元するため、.ui 由来の orientation を保存し復元後に再適用する。
                    # 旧 (横) 状態が新 (縦) レイアウトの向きを巻き戻す回帰を防ぐ (#865)。
                    designed_orientation = splitter.orientation()
                    splitter.restoreState(state)
                    splitter.setOrientation(designed_orientation)
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

    def _start_batch_import(self) -> None:
        """Batch APIインポートダイアログを開いてワーカーを起動する。"""
        from PySide6.QtWidgets import QDialogButtonBox

        if not self.worker_service:
            QMessageBox.warning(self, "エラー", "WorkerServiceが初期化されていません")
            return

        # JSONLファイル選択（複数可）
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Batch API結果ファイルを選択 (JSONL)",
            "",
            "JSONL Files (*.jsonl)",
        )
        if not file_paths:
            return

        jsonl_files = [Path(p) for p in file_paths]

        # Dry-Run確認
        dry_run_box = QMessageBox(self)
        dry_run_box.setWindowTitle("インポートモード選択")
        dry_run_box.setText(
            f"{len(jsonl_files)}ファイルをインポートします。\n\n"
            "Dry-Run: 照合結果のみ確認（DB書き込みなし）\n"
            "インポート: DBに保存"
        )
        dry_run_btn = dry_run_box.addButton("Dry-Run", QMessageBox.ButtonRole.AcceptRole)
        import_btn = dry_run_box.addButton("インポート", QMessageBox.ButtonRole.AcceptRole)
        dry_run_box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
        dry_run_box.exec()

        clicked = dry_run_box.clickedButton()
        if clicked is None or (clicked is not dry_run_btn and clicked is not import_btn):
            return

        dry_run = clicked is dry_run_btn
        self.worker_service.start_batch_import(jsonl_files, dry_run=dry_run)

    def _on_batch_import_finished(self, result: Any) -> None:
        """バッチインポート完了ハンドラ。"""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextEdit, QVBoxLayout

        from ...services.batch_image_matcher import BatchImageMatcher
        from ...services.batch_import_service import BatchImportResult

        if not isinstance(result, BatchImportResult):
            logger.warning(f"Unexpected batch import result type: {type(result)}")
            return

        mode = "DRY-RUN" if result.saved == 0 and result.matched > 0 else "LIVE"
        message = (
            f"バッチインポート完了 ({mode})\n\n"
            f"総レコード: {result.total_records}\n"
            f"パース成功: {result.parsed_ok}\n"
            f"照合成功: {result.matched}\n"
            f"照合失敗: {result.unmatched}\n"
            f"保存: {result.saved}\n"
            f"モデル: {result.model_name}"
        )

        if result.unmatched_ids:
            message += f"\n\n照合失敗 ({len(result.unmatched_ids)}件):"
            message += "\n(custom_idから抽出したファイル名がDBに未登録)"
            for uid in result.unmatched_ids[:5]:
                stem = BatchImageMatcher.extract_stem(uid)
                message += f"\n  - {stem}  ← {uid}"
            if len(result.unmatched_ids) > 5:
                message += f"\n  ... 他 {len(result.unmatched_ids) - 5} 件"

        # コピー可能なダイアログで結果表示
        dlg = QDialog(self)
        dlg.setWindowTitle("バッチインポート結果")
        dlg.setMinimumSize(520, 360)
        layout = QVBoxLayout(dlg)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(message)
        layout.addWidget(text_edit)
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(dlg.accept)
        layout.addWidget(btn_box)
        dlg.exec()

        self.statusBar().showMessage(
            f"バッチインポート完了: {result.saved}件保存, {result.unmatched}件アンマッチ", 10000
        )

    def _on_batch_import_error(self, error_message: str) -> None:
        """バッチインポートエラーハンドラ。"""
        QMessageBox.critical(
            self, "バッチインポートエラー", f"インポート中にエラーが発生しました:\n\n{error_message}"
        )
        if self.error_notification_widget:
            self.error_notification_widget.update_error_count()

    def _on_batch_import_canceled(self, worker_id: str) -> None:
        """バッチインポートキャンセルハンドラ（エラー通知は出さない）。"""
        self._delegate_to_progress_state("on_batch_import_canceled", worker_id)
