# src/lorairo/gui/window/main_window.py

import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import (
    QSettings,
    Signal,
)
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...database.db_core import IMG_DB_PATH, get_current_project_root, get_user_tag_db_path
from ...database.db_manager import ImageDatabaseManager
from ...filesystem import FileSystemManager
from ...gui.designer.MainWindow_ui import Ui_MainWindow
from ...services import get_service_container
from ...services.configuration_service import ConfigurationService
from ...services.selection_state_service import SelectionStateService
from ...services.service_container import ServiceContainer
from ...utils.log import logger
from ..controllers.annotation_workflow_controller import AnnotationWorkflowController
from ..controllers.dataset_controller import DatasetController
from ..controllers.settings_controller import SettingsController
from ..services.pipeline_control_service import PipelineControlService
from ..services.progress_state_service import ProgressStateService
from ..services.result_handler_service import ResultHandlerService
from ..services.tab_reorganization_service import TabReorganizationService
from ..services.worker_service import WorkerService
from ..state.dataset_state import DatasetStateManager
from ..state.model_selection_state import ModelSelectionStateManager
from ..state.staging_state import StagingStateManager
from ..tab.annotate_tab import AnnotateTabWidget
from ..tab.cli_tab import CliTabWidget
from ..tab.errors_tab import ErrorsTabWidget
from ..tab.export_tab import ExportTabWidget
from ..tab.jobs_tab import JobsTabWidget
from ..tab.map_tab import MapTabWidget
from ..tab.results_tab import ResultsTabWidget
from ..tab.search_tab import SearchTabWidget
from ..widgets.error_notification_widget import ErrorNotificationWidget
from ..widgets.registration_summary_widget import RegistrationSummaryWidget
from ..widgets.tag_management_dialog import TagManagementDialog


class MainWindow(QMainWindow, Ui_MainWindow):
    """
    メインワークスペースウィンドウ。
    データベース中心の設計で、画像の管理・検索・処理を統合的に提供。
    """

    # QSettings バージョン（UI構造変更時にインクリメント）
    # 2: Wireframes v11 · 6 タブ化（検索/マップ/アノテーション/ジョブ/結果/エラー）
    # 3: Wireframes v11 Phase 5 · エクスポートタブ追加（7 タブ化）
    # 4: #863 アノテタブ1カラム化（splitterBatchTagMain 縦）· 旧 (横) 保存状態を破棄
    # 5: #869 検索タブ SearchTabWidget 化（tabWorkspace 空化）· splitter キー構成変更
    SETTINGS_VERSION = 5

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
    model_selection_state_manager: ModelSelectionStateManager | None

    # Service/Controller層属性
    selection_state_service: SelectionStateService | None
    dataset_controller: DatasetController | None
    annotation_workflow_controller: AnnotationWorkflowController | None
    settings_controller: SettingsController | None
    export_tab: ExportTabWidget | None
    annotate_tab: AnnotateTabWidget | None
    search_tab: SearchTabWidget | None
    result_handler_service: ResultHandlerService | None
    pipeline_control_service: PipelineControlService | None
    progress_state_service: ProgressStateService | None

    @property
    def service_container(self) -> ServiceContainer:
        """ServiceContainer singleton instance"""
        return ServiceContainer()

    # ウィジェット属性の型定義
    jobs_tab: JobsTabWidget | None

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

        # 選択モデル集合の SSoT (#884, ADR 0076)
        self._initialize_model_selection_state_manager()

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

    def _initialize_model_selection_state_manager(self) -> None:
        """選択モデル集合の SSoT (ModelSelectionStateManager) を初期化する (#884, ADR 0076)。"""
        try:
            self.model_selection_state_manager = ModelSelectionStateManager()
            logger.info("✅ ModelSelectionStateManager初期化成功")
        except RuntimeError as e:
            logger.error(f"❌ ModelSelectionStateManager初期化失敗: {e}", exc_info=True)
            self.model_selection_state_manager = None

    def _update_database_status_label(self) -> None:
        """検索タブのDB状態バーを現在のプロジェクトディレクトリに合わせる。

        DB 状態バー (labelDbInfo) は SearchTabWidget へ移管したため、
        ``set_db_info`` 経由で更新する。検索タブ生成前 (サービス初期化フェーズ)
        は no-op とし、タブ生成直後に再度呼び出して反映させる (#869)。
        """
        search_tab = getattr(self, "search_tab", None)
        if search_tab is None:
            return

        try:
            project_root = get_current_project_root().resolve()
            image_db_path = IMG_DB_PATH.resolve()
            tooltip_lines = [f"画像DB: {image_db_path}"]

            tag_db_path = get_user_tag_db_path()
            if tag_db_path:
                tooltip_lines.append(f"タグDB: {tag_db_path.resolve()}")

            search_tab.set_db_info(f"データベース: {project_root}", "\n".join(tooltip_lines))
        except (OSError, RuntimeError) as e:
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
        sys.exit(1)

    def setup_custom_widgets(self) -> None:
        """カスタムウィジェット・タブを設定する。

        検索系ウィジェット (filterSearchPanel / thumbnail / preview / details /
        splitter) は SearchTabWidget へ移管したため、MainWindow ではタブ埋め込みと
        横断 glue サービスの初期化のみを行う (#869)。
        """
        logger.info("🔍 カスタムウィジェット設定開始")
        self._setup_other_custom_widgets()
        logger.info("カスタムウィジェット設定完了")

    def _setup_other_custom_widgets(self) -> None:
        """タブ埋め込みと Service/Controller 層を初期化する。"""
        # Service/Controller層初期化
        try:
            self.selection_state_service = SelectionStateService(
                dataset_state_manager=self.dataset_state_manager,
                db_repository=self.db_manager.image_repo if self.db_manager else None,
            )

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

        # 検索タブ (SearchTabWidget) を tabWorkspace へ埋め込む (#869)
        self._setup_search_tab()

        # アノテーションタブ (AnnotateTabWidget) を tabBatchTag へ埋め込む (#868)
        self._setup_annotate_tab()

        # QTabWidget初期化（タブ切り替え用）
        self._setup_tab_widget()
        self._setup_map_tab()
        self._setup_jobs_tab()
        self._setup_results_tab()
        self._setup_errors_tab()
        self._setup_export_tab()
        self._setup_cli_tab()
        self._setup_tab_shortcuts()
        self._setup_registration_summary_panel()

        # 全タブ構築後に async batch dispatch の協調オブジェクトを controller へ注入する
        # (#896 PR4b)。controller 生成時点では annotate_tab / jobs_tab が未生成のため
        # setter injection で受ける。
        self._configure_async_dispatch_controller()

    def _configure_async_dispatch_controller(self) -> None:
        """AnnotationWorkflowController へ async batch dispatch の依存を注入する (#896 PR4b)。

        jobs 台帳の再読込と statusBar 表示は callback 経由で委譲し、controller が
        MainWindow の widget を直接握らないようにする。
        """
        if self.annotation_workflow_controller is None:
            return
        self.annotation_workflow_controller.configure_async_dispatch(
            service_container=self.service_container,
            db_manager=self.db_manager,
            staging_state_manager=self.staging_state_manager,
            annotate_tab=self.annotate_tab,
            jobs_refresh=lambda: self.jobs_tab.refresh() if self.jobs_tab is not None else None,
            status_callback=lambda message, timeout: self.statusBar().showMessage(message, timeout),
            is_annotate_tab_active=lambda: self.tabWidgetMainMode.currentWidget() is self.tabBatchTag,
        )

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
        # SearchTabWidget の上端へ常設する (Wireframes v11 Frame 1、#869 で tabWorkspace 直下へ移設)
        layout.insertWidget(0, widget)
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

    def _setup_jobs_tab(self) -> None:
        """ジョブタブに JobsTabWidget を埋め込む (Epic #867 / #874)。

        Wireframes v11 ナビ順（検索 / マップ / アノテーション / ジョブ / 結果 / エラー）
        に従い、結果タブ (tabResults) の直前へ挿入する。Provider Batch ジョブの
        監視・キャンセル・同期ジョブ台帳・Batch API 結果インポートを JobsTabWidget が
        所有する (ADR 0076 §3: 作成入口は Annotate へ移管済み)。MainWindow は配置 +
        サービス注入 + 共有サービスへの橋渡し (glue) だけを残す。

        ジョブタブは必須機能ではないため、構築失敗時は graceful degradation
        (jobs_tab=None) とし、検索タブのような致命的終了はしない。
        """
        if not hasattr(self, "tabWidgetMainMode") or not self.tabWidgetMainMode:
            logger.warning("tabWidgetMainMode not found - ジョブタブ skipped")
            self.jobs_tab = None
            return

        try:
            widget = JobsTabWidget(
                service_container=self.service_container,
                db_manager=self.db_manager,
                worker_service=self.worker_service,
                parent=self.tabWidgetMainMode,
            )
            self.jobs_tab = widget
            self._connect_jobs_tab_signals()
            insert_index = self.tabWidgetMainMode.indexOf(self.tabResults)
            self.tabWidgetMainMode.insertTab(insert_index, widget, "ジョブ")
            logger.info("✅ ジョブタブ (JobsTabWidget) initialized")
        except Exception as e:
            self.jobs_tab = None
            logger.error(f"❌ ジョブタブ initialization failed: {e}", exc_info=True)

    def _connect_jobs_tab_signals(self) -> None:
        """JobsTabWidget の glue シグナル接続を行う (#874)。

        共有サービス (statusbar / error_notification / ProgressStateService) への
        作用はタブから Signal で受け、MainWindow が委譲する。
        """
        if self.jobs_tab is None:
            return
        self.jobs_tab.status_message_requested.connect(self.statusBar().showMessage)
        self.jobs_tab.batch_import_error_occurred.connect(self._on_batch_import_error)
        self.jobs_tab.batch_import_canceled.connect(self._on_batch_import_canceled)
        logger.info("    ✅ JobsTabWidget シグナル接続完了")

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
        """「移動」メニューと Ctrl+1〜8 のタブ切替を登録する。

        操作プロトタイプ (wireframes.html の NUM2KEY) の固定ショートカット契約に
        合わせ、Ctrl+N を視覚 index ではなく **タブ識別子** で割り当てる。
        restructureNav でナビの視覚順が変わっても番号はタブに固定されるため、
        Ctrl+1=検索 / 2=マップ / 3=アノテーション / 4=ジョブ / 5=結果 / 6=エラー /
        7=エクスポート / 8=CLI を保つ。各アクションが Ctrl+N を保持するため、別途
        QShortcut は登録しない。jobs_tab / cli_tab は runtime 生成のため未生成 (None)
        ならその番号をスキップする。
        """
        if not hasattr(self, "tabWidgetMainMode") or not self.tabWidgetMainMode:
            logger.warning("tabWidgetMainMode not found - 移動メニュー skipped")
            return
        # Ctrl+N の固定割当 (番号順、タブ識別子基準)。
        shortcut_tabs: list[QWidget | None] = [
            getattr(self, "tabWorkspace", None),
            getattr(self, "tabMap", None),
            getattr(self, "tabBatchTag", None),
            getattr(self, "jobs_tab", None),
            getattr(self, "tabResults", None),
            getattr(self, "tabErrors", None),
            getattr(self, "tabExport", None),
            getattr(self, "cli_tab", None),
        ]
        navigate_menu = QMenu("移動", self)
        for number, tab in enumerate(shortcut_tabs, start=1):
            if tab is None or self.tabWidgetMainMode.indexOf(tab) < 0:
                continue
            label = self.tabWidgetMainMode.tabText(self.tabWidgetMainMode.indexOf(tab))
            action = QAction(label, self)
            action.setShortcut(QKeySequence(f"Ctrl+{number}"))
            action.triggered.connect(partial(self.tabWidgetMainMode.setCurrentWidget, tab))
            navigate_menu.addAction(action)
        # 「表示」と「ツール」の間（ツールメニューの直前）へ挿入する
        tools_action = self.menuTools.menuAction() if hasattr(self, "menuTools") else None
        if tools_action is not None:
            self.menuBar().insertMenu(tools_action, navigate_menu)
        else:
            self.menuBar().addMenu(navigate_menu)
        self.menuNavigate = navigate_menu
        logger.debug("移動メニュー登録: Ctrl+1..Ctrl+8 (タブ識別子固定)")

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
            db_manager=self.db_manager,
            staging_state_manager=self.staging_state_manager,
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

    def _setup_search_tab(self) -> None:
        """検索タブに SearchTabWidget を埋め込む (Epic #867 / #869)。

        Wireframes v11 Frame 1 · Search/Workbench。データセット選択・DB 検索・
        サムネ表示・プレビュー/詳細編集・3 ペイン splitter・ステージング/エクスポート
        導線を SearchTabWidget が所有する。MainWindow は .ui の tabWorkspace
        コンテナへ埋め込み依存を注入し、横断 glue (worker dispatch /
        PipelineControlService 所有 / staging fan-out / settings) だけを残す (glue)。
        """
        container = getattr(self, "tabWorkspace", None)
        if container is None:
            logger.warning("tabWorkspace not found - 検索タブ skipped")
            self.search_tab = None
            return

        # 検索機能は必須。SearchTabWidget 構築失敗 (例: SearchFilterService 生成失敗) は
        # 致命的初期化エラーとして扱い、中途半端な window を表示せず終了する。
        # 旧 _setup_search_filter_integration() の fatal フローを維持する (#869 回帰防止)。
        try:
            widget = SearchTabWidget(
                service_container=self.service_container,
                db_manager=self.db_manager,
                dataset_state_manager=self.dataset_state_manager,
                staging_state_manager=self.staging_state_manager,
                worker_service=self.worker_service,
                parent=container,
            )
        except Exception as e:
            self._handle_critical_initialization_failure("SearchTabWidget", e)
            return
        container.layout().addWidget(widget)
        self.search_tab = widget
        self._connect_search_tab_signals()
        # 検索タブ生成後に DB 状態バーを反映する (サービス初期化フェーズでは no-op)
        self._update_database_status_label()
        logger.info("✅ 検索タブ (SearchTabWidget) initialized")

    def _connect_search_tab_signals(self) -> None:
        """SearchTabWidget の glue シグナル接続を行う (#869)。

        ステージング集合の fan-out は StagingStateManager 側で一括接続済み
        (ADR 0074) のため、タブ → MainWindow の横断 glue シグナルのみ接続する。
        """
        if self.search_tab is None:
            return
        try:
            self.search_tab.stage_to_annotation_requested.connect(self.send_selected_to_batch_tag)
            # #896: クイックタグはタブ内で完結。タブの status_message を statusBar へ橋渡しする。
            self.search_tab.status_message.connect(self.statusBar().showMessage)
            self.search_tab.export_requested.connect(self.export_data)
            self.search_tab.dataset_selection_requested.connect(self.select_and_process_dataset)
            self.search_tab.settings_requested.connect(self.open_settings)
            self.search_tab.search_error_occurred.connect(self._on_search_error)
            logger.info("    ✅ SearchTabWidget シグナル接続完了")
        except Exception as e:
            logger.error(f"    ❌ SearchTabWidget シグナル接続失敗: {e}")

    def _on_search_error(self, error_message: str) -> None:
        """検索/サムネ pipeline エラー → エラー通知バッジを更新する (#869)。

        Args:
            error_message: SearchTabWidget が報告したエラーメッセージ。
        """
        logger.warning(f"検索タブ pipeline エラー: {error_message}")
        if self.error_notification_widget:
            self.error_notification_widget.update_error_count()

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
            model_selection_state_manager=self.model_selection_state_manager,
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

    def _connect_menu_actions(self) -> None:
        """ファイル/編集/ヘルプメニューのアクション Signal 接続を行う。

        全選択/選択解除は SearchTabWidget が所有するサムネイルセレクタへ委譲する
        (検索系ウィジェットは #869 で SearchTab へ移管)。
        """
        # ファイル: 終了 / ヘルプ: about（タブ非依存なので先に接続）
        if hasattr(self, "actionExit"):
            self.actionExit.triggered.connect(self.close)
        if hasattr(self, "actionAbout"):
            self.actionAbout.triggered.connect(self._show_about_dialog)
        if self.search_tab is None:
            return
        thumbnail_selector = self.search_tab.thumbnail_selector
        try:
            if hasattr(self, "actionSelectAll"):
                self.actionSelectAll.triggered.connect(thumbnail_selector._select_all_items)
            if hasattr(self, "actionDeselectAll"):
                self.actionDeselectAll.triggered.connect(thumbnail_selector._deselect_all_items)
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
            # #896: batch tag 書込はタブ内で完結。タブの status_message を statusBar へ橋渡しする。
            self.annotate_tab.status_message.connect(self.statusBar().showMessage)
            # 実行エントリは AnnotationWorkflowController が所有 (#896 PR4c)。controller 未初期化の
            # 縮退起動でも実行ボタンが無反応にならないよう、薄い wrapper 経由で接続し警告を出す。
            self.annotate_tab.annotation_execute_requested.connect(self._on_annotation_execute_requested)
            self.annotate_tab.configure_key_requested.connect(self._on_annotate_configure_key_requested)
            logger.info("    ✅ AnnotateTabWidget シグナル接続完了")
        except Exception as e:
            logger.error(f"    ❌ AnnotateTabWidget シグナル接続失敗: {e}")

    def _on_annotation_execute_requested(self) -> None:
        """run bar 実行ボタン → AnnotationWorkflowController へ委譲する (#896 PR4c)。

        controller 初期化が縮退した起動 (``_setup_other_custom_widgets`` の except 経路)
        でも実行ボタンが無反応にならないよう、薄い wrapper で受けて未初期化を警告する。
        """
        if self.annotation_workflow_controller is None:
            QMessageBox.warning(
                self,
                "コントローラー未初期化",
                "AnnotationWorkflowControllerが初期化されていないため、アノテーション処理を開始できません。",
            )
            return
        self.annotation_workflow_controller.start_annotation()

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
        """設定ダイアログを開くメニューアクションの Signal 接続を行う。

        旧ワークスペースの ``pushButtonSettings`` は SearchTabWidget の
        ``settings_requested`` シグナルへ移管したため、ここでは menubar の
        ``actionSettings`` のみ接続する (#869)。
        """
        if hasattr(self, "actionSettings"):
            self.actionSettings.triggered.connect(self.open_settings)

    def _connect_events(self) -> None:
        """イベント接続を設定（安全な実装）"""
        try:
            logger.info("  - イベント接続開始...")
            self._connect_menu_actions()
            self._setup_worker_pipeline_signals()
            self._connect_batch_tag_signals()
            self._connect_settings_signals()
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
        """フィルターパネルの表示切替を SearchTabWidget へ委譲する (#869)。

        パネル本体とスプリッターサイズの退避/復元は SearchTabWidget が所有する
        (契約スロット ``toggle_filter_panel``)。MainWindow は menubar の
        ``actionToggleFilterPanel`` (checkable) を薄く中継するだけ。

        Args:
            checked: ``actionToggleFilterPanel`` の新しいチェック状態。
        """
        if self.search_tab is not None:
            self.search_tab.toggle_filter_panel()
        logger.debug(f"Filter panel visibility: {checked}")

    def _toggle_preview_panel(self, checked: bool) -> None:
        """プレビューパネルの表示切替を SearchTabWidget へ委譲する (#869)。

        Args:
            checked: ``actionTogglePreviewPanel`` の新しいチェック状態。
        """
        if self.search_tab is not None:
            self.search_tab.toggle_preview_panel()
        logger.debug(f"Preview panel visibility: {checked}")

    def _setup_worker_pipeline_signals(self) -> None:
        """WorkerService pipeline signal connections setup"""
        if not self.worker_service:
            logger.warning("WorkerService not available - pipeline signals not connected")
            return

        # Verify WorkerService has required signals
        # batch_import_finished/error/canceled は JobsTabWidget が self-wire するため
        # ここでは検証・接続しない (#874)。
        required_signals = [
            "batch_registration_started",
            "batch_registration_finished",
            "batch_registration_error",
            "batch_registration_canceled",
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

        # Batch import の完了/エラー/キャンセルは JobsTabWidget が self-wire し所有する (#874)。
        # MainWindow は JobsTabWidget からの glue シグナル経由で error_notification /
        # ProgressStateService へ委譲する (_connect_jobs_tab_signals)。

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
        """データベースから画像を読み込み、検索パイプラインを開始する。

        検索起動ロジックは SearchTabWidget が所有するため委譲する (#869)。
        """
        if self.search_tab is not None:
            self.search_tab.load_images_from_db()

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

        エクスポート下部バーの件数表示とアノテーションタブをステージング集合へ
        ライブ同期する。エクスポートタブの対象は ExportTabWidget が自治購読する
        ため MainWindow からは push しない (#896)。アノテ側の run bar / pipeline /
        preflight 再計算は AnnotateTabWidget.set_staging_target() が担う (#868)。

        Args:
            image_ids: 現在のステージング画像IDリスト
        """
        count = len(image_ids) if image_ids else 0
        self._update_export_target_ui(count)
        # Phase 5: エクスポートタブの対象は ExportTabWidget が staged_images_changed を
        # 自治購読してライブ同期する (ADR 0055 / #896)。MainWindow からの push は不要。
        # #868: アノテーションタブ (run bar / pipeline / preflight) をステージング集合と同期
        if self.annotate_tab is not None:
            self.annotate_tab.set_staging_target(list(image_ids) if image_ids else [])

    def _update_export_target_ui(self, staging_count: int) -> None:
        """エクスポート下部バーの対象件数ラベルを更新する。

        ADR 0055: ワークスペースのエクスポート入口の対象=ステージング集合。
        件数は ``StagingWidget.staged_images_changed``（= ステージング件数）を反映し、
        サムネ選択数ではない。件数ラベルは SearchTabWidget へ移管したため
        ``set_export_target_count`` 経由で更新する (#869)。

        Args:
            staging_count: 現在のステージング画像数。
        """
        if self.search_tab is not None:
            self.search_tab.set_export_target_count(staging_count)

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
            # worker 横断のため MainWindow が所有し、検索系ウィジェットは
            # SearchTabWidget のプロパティ経由で注入する (#869)。
            logger.info("  - PipelineControlService初期化中...")
            self.pipeline_control_service = PipelineControlService(
                worker_service=self.worker_service,
                thumbnail_selector=self.search_tab.thumbnail_selector if self.search_tab else None,
                filter_search_panel=self.search_tab.filter_search_panel if self.search_tab else None,
            )
            logger.info("  ✅ PipelineControlService初期化成功")

            # ProgressStateService初期化
            logger.info("  - ProgressStateService初期化中...")
            self.progress_state_service = ProgressStateService(status_bar=self.statusBar())
            logger.info("  ✅ ProgressStateService初期化成功")

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

    def export_data(self) -> None:
        """エクスポートタブへ遷移する。

        Phase 5 (Wireframes v11 Frame 7): モーダルダイアログからタブ常設に変更。
        遷移前に ExportTabWidget.refresh() でステージング集合を再読込し、シグナル
        取りこぼしがあってもタブ表示時点の対象件数を正とする (#896)。
        """
        export_tab = getattr(self, "export_tab", None)
        if export_tab is None or not hasattr(self, "tabExport"):
            logger.error("エクスポートタブが初期化されていません")
            QMessageBox.warning(
                self, "エラー", "エクスポートタブが初期化されていないため、エクスポートを開けません。"
            )
            return

        export_tab.refresh()
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
            thumbnail_selector_available = self.search_tab is not None
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
        # (タブ widget, ログ名, 表示時ハンドラ) の dispatch 表。index ではなく
        # widget 同一性で分岐し、タブ構成変更に耐える。
        dispatch: list[tuple[QWidget | None, str, Callable[[], None]]] = [
            (getattr(self, "tabWorkspace", None), "Search", self._refresh_search_tab),
            (getattr(self, "tabBatchTag", None), "Annotate", self._refresh_batch_tag_staging),
            (self.jobs_tab, "Jobs", self._refresh_jobs_tab),
            (getattr(self, "tabResults", None), "Results", self._refresh_results_tab),
            (getattr(self, "tabErrors", None), "Errors", self._refresh_errors_tab),
            (getattr(self, "tabExport", None), "Export", self._refresh_export_tab),
        ]
        for widget, label, handler in dispatch:
            if widget is not None and current is widget:
                logger.info(f"Switched to {label} tab")
                handler()
                return

    def _refresh_search_tab(self) -> None:
        """検索タブ表示時の再計算をタブへ委譲する (#869)。"""
        if self.search_tab is not None:
            self.search_tab.refresh()

    def _refresh_jobs_tab(self) -> None:
        """ジョブタブ表示時の再計算をタブへ委譲する (#874)。"""
        if self.jobs_tab is not None:
            self.jobs_tab.refresh()

    def _refresh_results_tab(self) -> None:
        """結果タブ表示時の再計算をタブへ委譲する。"""
        if self.results_tab is not None:
            self.results_tab.refresh()

    def _refresh_errors_tab(self) -> None:
        """エラータブ表示時の再計算をタブへ委譲する。"""
        if self.errors_tab is not None:
            self.errors_tab.refresh()

    def _refresh_export_tab(self) -> None:
        """エクスポートタブ表示時の再読込をタブへ委譲する (ADR 0055 安全網, #896)。"""
        if self.export_tab is not None:
            self.export_tab.refresh()

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
        # 実行中のエクスポート thread を停止する (埋め込み widget の closeEvent は
        # 親ウィンドウ閉鎖で発火しないため明示的に呼ぶ、#949/#961 P2)。
        if self.export_tab is not None:
            self.export_tab.shutdown()
        # refinement worker を停止する (検索/エクスポート両タブの詳細ペイン、#931 P2)。
        # QThread が widget より長生きして Qt teardown 警告/クラッシュになるのを防ぐ。
        for tab in (self.search_tab, self.export_tab):
            if tab is not None:
                tab.selected_image_details_widget.shutdown()
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

        # スプリッター状態 (SearchTab が所有・#896)
        if self.search_tab is not None:
            self.search_tab.save_layout_state(settings)

        # エクスポートタブの splitter 状態 (ExportTab が所有・#949)
        if self.export_tab is not None:
            self.export_tab.save_splitter_state()

        # パネル表示状態
        if hasattr(self, "actionToggleFilterPanel"):
            settings.setValue("panel_visible/filter", self.actionToggleFilterPanel.isChecked())
        if hasattr(self, "actionTogglePreviewPanel"):
            settings.setValue("panel_visible/preview", self.actionTogglePreviewPanel.isChecked())

        settings.sync()
        logger.info("Window state saved to QSettings")

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

        # スプリッター状態 (SearchTab が所有・#896)
        restored = self.search_tab.restore_layout_state(settings) if self.search_tab is not None else False

        # パネル表示状態
        self._restore_panel_visibility(settings)

        if restored:
            logger.info("Window state restored from QSettings")

    def _restore_panel_visibility(self, settings: QSettings) -> None:
        """パネル表示状態を復元する。

        blockSignals で toggled シグナルを抑制し、
        パネルの可視状態を直接設定することで race condition を回避する。

        Args:
            settings: QSettingsインスタンス
        """
        # フィルターパネル: 実体は SearchTabWidget が所有する。非表示で保存されていた
        # 場合のみ契約スロットで切り替える (タブは既定で表示状態、#869)。
        filter_visible = bool(settings.value("panel_visible/filter", True, type=bool))
        if hasattr(self, "actionToggleFilterPanel"):
            self.actionToggleFilterPanel.blockSignals(True)
            self.actionToggleFilterPanel.setChecked(filter_visible)
            self.actionToggleFilterPanel.blockSignals(False)
            if not filter_visible and self.search_tab is not None:
                self.search_tab.toggle_filter_panel()

        # プレビューパネル
        preview_visible = bool(settings.value("panel_visible/preview", True, type=bool))
        if hasattr(self, "actionTogglePreviewPanel"):
            self.actionTogglePreviewPanel.blockSignals(True)
            self.actionTogglePreviewPanel.setChecked(preview_visible)
            self.actionTogglePreviewPanel.blockSignals(False)
            if not preview_visible and self.search_tab is not None:
                self.search_tab.toggle_preview_panel()

    def _start_batch_import(self) -> None:
        """Batch APIインポートを起動する (File メニュー → JobsTabWidget へ委譲, #874)。

        実ロジック (ファイル選択 / Dry-Run 選択 / worker 起動) は JobsTabWidget が所有する。
        メニューアクションは MainWindow 初期化フェーズで配線するため、タブ生成後に
        jobs_tab が存在する場合のみ委譲する。
        """
        if self.jobs_tab is None:
            QMessageBox.warning(self, "エラー", "ジョブタブが初期化されていません")
            return
        self.jobs_tab.start_batch_import()

    def _on_batch_import_error(self, error_message: str) -> None:
        """バッチインポートエラーハンドラ (JobsTabWidget からの glue, #874)。"""
        QMessageBox.critical(
            self, "バッチインポートエラー", f"インポート中にエラーが発生しました:\n\n{error_message}"
        )
        if self.error_notification_widget:
            self.error_notification_widget.update_error_count()

    def _on_batch_import_canceled(self, worker_id: str) -> None:
        """バッチインポートキャンセルハンドラ (JobsTabWidget からの glue, #874)。"""
        self._delegate_to_progress_state("on_batch_import_canceled", worker_id)
