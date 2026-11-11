# src/lorairo/gui/window/main_window.py

import os
import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import (
    QSettings,
    Qt,
    QThread,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import SQLAlchemyError

from ...database.db_core import (
    IMG_DB_PATH,
    get_current_project_root,
    get_project_dir,
    get_user_tag_db_path,
)
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
from ..message_box import show_critical, show_information, show_warning
from ..services.pipeline_control_service import PipelineControlService
from ..services.progress_state_service import ProgressStateService
from ..services.result_handler_service import ResultHandlerService
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
from ..watchdog import MainThreadWatchdog
from ..widgets.dataset_select_dialog import DatasetSelectDialog, DatasetSelection
from ..widgets.error_notification_widget import ErrorNotificationWidget
from ..widgets.model_selection_widget import ModelSelectionWidget
from ..widgets.registration_summary_widget import RegistrationSummaryWidget
from ..widgets.tag_management_dialog import TagManagementDialog
from ..workers.manager import WorkerManager
from ..workers.tag_db_warmup_worker import TagDbWarmupResult, TagDbWarmupWorker

if TYPE_CHECKING:
    from ..workers.annotation_worker import AnnotationExecutionResult

# プロジェクト切替で生成した MainWindow の参照を保持する (#1547)。
# main() のローカル変数が持つのは起動時のウィンドウだけなので、ここで保持しないと
# 切替後のウィンドウが GC で破棄される。
_PROJECT_SWITCH_WINDOWS: list["MainWindow"] = []


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
        self._startup_warnings: list[str] = []
        self._closing = False
        self._tag_db_manager: WorkerManager | None = None

        try:
            # Phase 1: 基本UI設定（最優先）
            logger.info("MainWindow初期化開始 - Phase 1: UI設定")
            setup_ui = cast(Callable[[QWidget], None], self.setupUi)
            setup_ui(self)
            self._clamp_initial_window_size()
            logger.info("UI設定完了")

            # タグ管理メニューアクション追加（ツールメニューへ）
            if hasattr(self, "menuTools"):
                self.actionTagManagement = QAction("未分類タグの整理", self)
                self.actionTagManagement.setShortcut("Ctrl+Shift+T")
                self.actionTagManagement.triggered.connect(self._show_tag_management_dialog)
                self.menuTools.addAction(self.actionTagManagement)
                logger.debug("Tag management menu action added to Tools menu")

            # ファイルメニューアクション構成 (#1547, #1550)
            self._populate_file_menu()

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

            # メインスレッド停滞 watchdog を開始する (#1221)。GUI が「応答なし」に
            # なった際、どの操作でイベントループが止まったかをログで追えるようにする。
            self._main_thread_watchdog = MainThreadWatchdog(self)
            self._main_thread_watchdog.start()

            if self._startup_warnings:
                summary = "、".join(self._startup_warnings)
                self.statusBar().showMessage(
                    f"一部のコンポーネントの初期化をスキップしました: {summary}", 8000
                )

            logger.info("MainWindow初期化完了")

        except Exception as e:
            self._initialization_failed = True
            self._initialization_error = f"初期化エラー: {e}"
            logger.opt(exception=True).error(f"MainWindow初期化失敗: {e}")
            # 失敗を無言にしない: ステータスバーへ出し、ダイアログは main.py が起動直後に 1 回出す (#1569)
            try:
                self.statusBar().showMessage("起動時の初期化に失敗しました。ログを確認してください", 8000)
            except (AttributeError, RuntimeError):
                logger.warning("初期化失敗のステータスバー表示に失敗しました")

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
            self.file_system_manager = self._create_project_file_system_manager()
            logger.info("✅ FileSystemManager初期化成功")
        except Exception as e:
            logger.error(f"❌ FileSystemManager初期化失敗: {e}")
            self._record_startup_warning("FileSystemManager")
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
            self._record_startup_warning("DatasetStateManager")
            self.dataset_state_manager = None

        # ステージング集合の SSoT (Annotate / Jobs タブが共有する、ADR 0074)
        self._initialize_staging_state_manager()

        # 選択モデル集合の SSoT (#884, ADR 0076)
        self._initialize_model_selection_state_manager()

        # DBステータス表示を現在のプロジェクトディレクトリに更新
        self._update_database_status_label()

        logger.info("サービス初期化完了")

    @staticmethod
    def _create_project_file_system_manager() -> FileSystemManager:
        """現在のプロジェクトルートで初期化した FileSystemManager を作る (#1360)。

        GUI のプロジェクトは起動時の DB 接続で確定するため、ここで一度だけ
        ``initialize(get_current_project_root())`` する。これにより登録操作を経ない
        セッション (クロップのみ等) でも WorkerService / DatasetController /
        CropDialogLauncher が共有する FSM が初期化済みになる。

        ディレクトリ作成に失敗しても起動は止めない (未初期化のまま返す)。登録経路は
        実行時に再初期化し、CropDialogLauncher も開く時点で遅延初期化する。

        Returns:
            プロジェクトルートで初期化済み (失敗時は未初期化) の FileSystemManager。
        """
        fsm = FileSystemManager()
        project_root = get_current_project_root()
        try:
            fsm.initialize(project_root)
        except OSError as e:
            logger.opt(exception=True).error(f"FileSystemManager のプロジェクト初期化に失敗: {e}")
        return fsm

    def show_startup_notice(self) -> bool:
        """起動時の初期化失敗・部分縮退を、ログの場所つきで 1 回だけダイアログ通知する (#1569)。

        ステータスバーの 8 秒表示は見逃されやすいため、イベントループ開始後に
        呼び出し側 (main.py) が ``QTimer.singleShot(0, ...)`` で 1 度だけ呼ぶ。
        2 回目以降の呼び出しは何もしない。

        Returns:
            ダイアログを表示した場合 True。通知対象が無い、または表示済みなら False。
        """
        if getattr(self, "_startup_notice_shown", False):
            return False
        warnings = list(getattr(self, "_startup_warnings", None) or [])
        failed = bool(getattr(self, "_initialization_failed", False))
        if not warnings and not failed:
            return False
        self._startup_notice_shown = True

        from ...utils.config import DEFAULT_LOG_PATH

        if failed:
            text = (
                "起動時の初期化に失敗したため、一部の機能が正しく動作しない可能性があります。\n"
                "アプリを再起動しても改善しない場合は、ログを添えて報告してください。"
            )
        else:
            text = (
                "一部の機能の初期化をスキップして起動しました。該当する機能は動作しない場合があります。\n"
                "アプリを再起動しても改善しない場合は、ログを添えて報告してください。"
            )
        lines = [f"ログの場所: {DEFAULT_LOG_PATH}"]
        if warnings:
            lines.append("スキップした項目: " + "、".join(warnings))
        error = getattr(self, "_initialization_error", None)
        if failed and error:
            lines.append(str(error))
        show_warning(self, "起動時の警告", text, detail="\n".join(lines))
        return True

    def _record_startup_warning(self, component_name: str) -> None:
        """起動時の非致命的なコンポーネント初期化失敗・スキップを記録する (#1569)。"""
        warnings = getattr(self, "_startup_warnings", None)
        if not isinstance(warnings, list):
            warnings = []
            self._startup_warnings = warnings
        if component_name not in warnings:
            warnings.append(component_name)

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
            MainWindow._record_startup_warning(self, "StagingStateManager")
            self.staging_state_manager = None

    def _initialize_model_selection_state_manager(self) -> None:
        """選択モデル集合の SSoT (ModelSelectionStateManager) を初期化する (#884, ADR 0076)。"""
        try:
            self.model_selection_state_manager = ModelSelectionStateManager()
            logger.info("✅ ModelSelectionStateManager初期化成功")
        except RuntimeError as e:
            logger.opt(exception=True).error(f"❌ ModelSelectionStateManager初期化失敗: {e}")
            MainWindow._record_startup_warning(self, "ModelSelectionStateManager")
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

        # ユーザーへの通知（GUI利用可能なら）。本文はコピー可能にする (#1160)。
        # 致命的初期化失敗の検証基盤 (critical_failure_hooks) が main_window.QMessageBox を
        # patch して setText/exec を追跡するため、ここは共通ヘルパーではなく素の QMessageBox
        # を構築し、本文ラベルだけ選択可能にする。
        try:
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Critical)
            msg_box.setWindowTitle("LoRAIro - 致命的エラー")
            msg_box.setText(error_message)
            label = msg_box.findChild(QLabel, "qt_msgbox_label")
            if label is not None:
                label.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                    | Qt.TextInteractionFlag.TextSelectableByKeyboard
                )
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
            MainWindow._record_startup_warning(self, "Controller")
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
            MainWindow._record_startup_warning(self, "MapTabWidget")
            logger.opt(exception=True).error(f"マップタブ initialization failed: {e}")

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
            MainWindow._record_startup_warning(self, "JobsTabWidget")
            logger.opt(exception=True).error(f"❌ ジョブタブ initialization failed: {e}")

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
            logger.opt(exception=True).error(f"❌ ErrorNotificationWidget初期化失敗: {e}")
            MainWindow._record_startup_warning(self, "ErrorNotificationWidget")
            self.error_notification_widget = None

    def _bind_tab_shortcut_action(self, action: QAction, number: int, tab: QWidget) -> None:
        """Ctrl+N アクションへ _TOP_NAV_ITEMS または QTabWidget の切替先を接続する (#1552)。"""
        top_nav_items = getattr(self, "_TOP_NAV_ITEMS", None)
        top_nav_buttons = getattr(self, "_top_nav_buttons", None)
        switch_top_nav = getattr(self, "_switch_top_nav", None)
        if (
            isinstance(top_nav_items, (list, tuple))
            and isinstance(top_nav_buttons, dict)
            and callable(switch_top_nav)
            and number - 1 < len(top_nav_items)
        ):
            item_entry = top_nav_items[number - 1]
            obj_name = item_entry[0] if isinstance(item_entry, tuple) else str(item_entry)
            if obj_name in top_nav_buttons:
                action.triggered.connect(partial(switch_top_nav, obj_name))
                return
        action.triggered.connect(partial(self.tabWidgetMainMode.setCurrentWidget, tab))

    def _setup_tab_shortcuts(self) -> None:
        """「移動」メニューと Ctrl+1〜8 / Ctrl+F / F5 / Esc のキーボードショートカットを登録する (#1552)。

        操作プロトタイプ (wireframes.html の NUM2KEY) の固定ショートカット契約に
        合わせ、Ctrl+N を視覚 index ではなく **タブ識別子** で割り当てる。
        restructureNav でナビの視覚順が変わっても番号はタブに固定されるため、
        Ctrl+1=検索 / 2=マップ / 3=アノテーション / 4=ジョブ / 5=結果 / 6=エラー /
        7=エクスポート / 8=CLI を保つ。DS AppShell ヘッダー (_top_nav_buttons) が
        存在する場合は _TOP_NAV_ITEMS 順で _switch_top_nav を呼び、通常の QTabWidget
        構成では各アクションに Ctrl+N を割り当てる。
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
            MainWindow._bind_tab_shortcut_action(self, action, number, tab)
            navigate_menu.addAction(action)
        # 「表示」と「ツール」の間（ツールメニューの直前）へ挿入する
        tools_action = self.menuTools.menuAction() if hasattr(self, "menuTools") else None
        if tools_action is not None:
            self.menuBar().insertMenu(tools_action, navigate_menu)
        else:
            self.menuBar().addMenu(navigate_menu)
        self.menuNavigate = navigate_menu

        self._shortcut_focus_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self._shortcut_focus_search.activated.connect(partial(MainWindow._focus_search_input, self))

        if getattr(self, "actionRefreshView", None) is None:
            self._shortcut_refresh_tab = QShortcut(QKeySequence("F5"), self)
            self._shortcut_refresh_tab.activated.connect(partial(MainWindow._refresh_active_tab, self))

        self._shortcut_escape = QShortcut(QKeySequence("Esc"), self)
        self._shortcut_escape.activated.connect(partial(MainWindow._handle_escape_shortcut, self))

        logger.debug("移動メニュー・キーボードショートカット登録: Ctrl+1..8, Ctrl+F, F5, Esc")

    def _setup_keyboard_shortcuts(self) -> None:
        """キーボードショートカットを設定する (#1552 互換エイリアス)。"""
        self._setup_tab_shortcuts()

    @Slot()
    def _focus_search_input(self) -> None:
        """Ctrl+F: 検索タブへ切り替え、検索入力欄にフォーカスして全選択する (#1552)。"""
        tab_widget = getattr(self, "tabWidgetMainMode", None)
        workspace = getattr(self, "tabWorkspace", None)
        if tab_widget is not None and workspace is not None and tab_widget.currentWidget() is not workspace:
            tab_widget.setCurrentWidget(workspace)

        search_tab = getattr(self, "search_tab", None)
        if search_tab is not None:
            frame_panel = getattr(search_tab, "frameFilterSearchPanel", None)
            if (
                frame_panel is not None
                and frame_panel.isHidden()
                and hasattr(search_tab, "toggle_filter_panel")
            ):
                search_tab.toggle_filter_panel()
            elif frame_panel is not None and not frame_panel.isVisible():
                frame_panel.setVisible(True)

        panel = getattr(self, "filter_search_panel", None)
        if panel is None and search_tab is not None:
            panel = getattr(search_tab, "filter_search_panel", None)
        if panel is not None and not panel.isVisible():
            panel.setVisible(True)

        action = getattr(self, "actionToggleFilterPanel", None)
        if action is not None and hasattr(action, "isChecked") and not action.isChecked():
            if hasattr(action, "blockSignals"):
                blocked = action.blockSignals(True)
                try:
                    action.setChecked(True)
                finally:
                    action.blockSignals(blocked)
            else:
                action.setChecked(True)

        line_edit = getattr(getattr(panel, "ui", None), "lineEditSearch", None)
        if line_edit is not None:
            line_edit.setFocus()
            line_edit.selectAll()

    def _refresh_search_tab_shortcut(self) -> None:
        """F5: 検索タブの再読込を実行する (#1552)。"""
        search_tab = getattr(self, "search_tab", None)
        if search_tab is not None and hasattr(search_tab, "load_images_from_db"):
            search_tab.load_images_from_db()
            return
        if hasattr(self, "load_images_from_db"):
            self.load_images_from_db()
            return
        selector = getattr(self, "thumbnail_selector", None)
        if selector is None and search_tab is not None:
            selector = getattr(search_tab, "thumbnail_selector", None)
        if selector is not None and hasattr(selector, "refresh_current_page"):
            selector.refresh_current_page()

    @Slot()
    def _refresh_active_tab(self) -> None:
        """F5: 現在アクティブなタブの表示を更新する (#1552)。"""
        tab_widget = getattr(self, "tabWidgetMainMode", None)
        current = tab_widget.currentWidget() if tab_widget is not None else None
        if current is None:
            return
        search_tab = getattr(self, "search_tab", None)
        if current in (getattr(self, "tabWorkspace", None), search_tab):
            MainWindow._refresh_search_tab_shortcut(self)
            return

        annotate_tab = getattr(self, "annotate_tab", None)
        if current in (getattr(self, "tabBatchTag", None), annotate_tab) and annotate_tab is not None:
            if hasattr(annotate_tab, "refresh_model_selection"):
                annotate_tab.refresh_model_selection()
            return

        for tab_container, tab_obj in (
            (getattr(self, "jobs_tab", None), getattr(self, "jobs_tab", None)),
            (getattr(self, "tabResults", None), getattr(self, "results_tab", None)),
            (getattr(self, "tabErrors", None), getattr(self, "errors_tab", None)),
            (getattr(self, "tabExport", None), getattr(self, "export_tab", None)),
        ):
            if current in (tab_container, tab_obj) and tab_obj is not None and hasattr(tab_obj, "refresh"):
                tab_obj.refresh()
                return

    @Slot()
    def _handle_escape_shortcut(self) -> None:
        """Esc: 検索タブでクロップモード終了またはサムネイル選択解除を行う (#1552)。"""
        tab_widget = getattr(self, "tabWidgetMainMode", None)
        current = tab_widget.currentWidget() if tab_widget is not None else None
        search_tab = getattr(self, "search_tab", None)
        if current is not None and current not in (getattr(self, "tabWorkspace", None), search_tab):
            return

        preview = getattr(self, "image_preview_widget", None)
        if preview is None and search_tab is not None:
            preview = getattr(search_tab, "image_preview_widget", None)
        crop_ctrl = getattr(preview, "_crop_controller", None) if preview is not None else None
        if crop_ctrl is not None:
            cancel_fn = getattr(preview, "cancel_crop_mode", None) or getattr(crop_ctrl, "cancel", None)
            if callable(cancel_fn):
                cancel_fn()
            elif preview is not None:
                preview._crop_controller = None
            return

        deselect_fn = getattr(self, "_deselect_all_thumbnails", None)
        if callable(deselect_fn):
            deselect_fn()
        else:
            MainWindow._deselect_all_thumbnails(self)

    def _deselect_all_thumbnails(self) -> None:
        """現在アクティブなタブのサムネイル選択をすべて解除する (#1552)。"""
        selector = MainWindow._active_thumbnail_selector(self)
        if selector is None:
            selector = getattr(self, "thumbnail_selector", None)
        if selector is not None and hasattr(selector, "_deselect_all_items"):
            selector._deselect_all_items()
            return
        dsm = getattr(self, "dataset_state_manager", None)
        if dsm is not None:
            dsm.clear_selection()

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
        self._batch_review_status = QLabel(container)
        self._batch_review_status.setTextFormat(Qt.TextFormat.PlainText)
        self.statusBar().addPermanentWidget(self._batch_review_status)
        widget.running_status_changed.connect(self._batch_review_status.setText)
        widget.running_status_changed.connect(
            lambda message: self._batch_review_status.setVisible(bool(message))
        )
        self._batch_review_status.setVisible(False)
        widget.review_result_saved.connect(self._refresh_search_annotation_review)
        widget.manual_review_requested.connect(self._open_annotation_review_image)
        widget.review_target_selection_requested.connect(
            partial(self.tabWidgetMainMode.setCurrentWidget, self.tabWorkspace)
        )
        widget.review_target_list_requested.connect(
            partial(self.tabWidgetMainMode.setCurrentWidget, self.tabBatchTag)
        )
        self._reload_results_annotation_review_service()
        logger.info("✅ 結果タブ (ResultsTabWidget) initialized")

    def _refresh_search_annotation_review(self, image_id: int) -> None:
        if self.search_tab is not None:
            self.search_tab.refresh_annotation_review(image_id)

    def _reload_results_annotation_review_service(self) -> None:
        """Bind saved Clef results and current configuration to the results tab."""
        if self.results_tab is None or self.db_manager is None:
            return
        from ...services.annotation_review_service import AnnotationReviewService
        from ...services.annotation_review_store import AnnotationReviewStore

        try:
            self.results_tab.set_annotation_review_services(
                AnnotationReviewService(get_service_container().config_service, self.db_manager),
                AnnotationReviewStore(self.db_manager),
            )
        except Exception as error:
            self.results_tab.set_annotation_review_unavailable_reason(str(error))
            logger.warning("Clef results configuration could not be loaded: {}", error)

    def _open_annotation_review_image(self, image_id: int) -> None:
        """Open an image's existing manual editor from a retained warning."""
        if self.dataset_state_manager is None or self.search_tab is None:
            return
        self.dataset_state_manager.set_selected_images([image_id])
        self.dataset_state_manager.set_current_image(image_id)
        # Reload even when the requested image is already current, so the editor
        # shows current annotations rather than a previous cached selection.
        self.dataset_state_manager.refresh_images([image_id])
        self.search_tab.show_preview_panel()
        preview_action = getattr(self, "actionTogglePreviewPanel", None)
        if preview_action is not None:
            previously_blocked = preview_action.blockSignals(True)
            preview_action.setChecked(True)
            preview_action.blockSignals(previously_blocked)
        self.tabWidgetMainMode.setCurrentWidget(self.tabWorkspace)

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
        select_btn = getattr(widget, "pushButtonSelectDataset", None)
        if select_btn is not None:
            select_btn.setText("画像を登録…")
            select_btn.setToolTip("画像フォルダを選択してデータベースへ登録します")
        self._connect_search_tab_signals()
        # 検索タブ生成後に DB 状態バーとプロジェクト表示を反映する (サービス初期化フェーズでは no-op)
        self._update_database_status_label()
        self._update_project_indicator()
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
            details = self.search_tab.selected_image_details_widget
            details.annotations_changed.connect(self.search_tab.refresh_annotation_review)
            details.annotation_review_widget.review_result_saved.connect(
                self.search_tab.refresh_annotation_review
            )
            self._single_review_status = QLabel(self)
            self._single_review_status.setTextFormat(Qt.TextFormat.PlainText)
            self.statusBar().addPermanentWidget(self._single_review_status)
            self.search_tab.review_running_status_changed.connect(self._single_review_status.setText)
            self.search_tab.review_running_status_changed.connect(
                lambda message: self._single_review_status.setVisible(bool(message))
            )
            self._single_review_status.setVisible(False)
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
                    show_warning(self, "エラー", "サービス接続が確立されていません")
                    return

                # refinement キャッシュ無効化用に共有 RefinementService を注入 (#977)。
                # tagdb 初期化失敗でもダイアログを巻き込まず degrade する (付加機能のため非致命)。
                refinement_service = None
                try:
                    refinement_service = self.service_container.refinement_service
                except Exception as e:
                    # graceful degradation (#977): RefinementService 初期化エラーでも
                    # タグ管理ダイアログ自体は使えるようにする。
                    logger.warning(f"RefinementService 配線をスキップ (tagdb 不可?): {e}")

                self.tag_management_dialog = TagManagementDialog(
                    tag_service=self.service_container.tag_management_service,
                    parent=self,
                    refinement_service=refinement_service,
                )

                logger.info("TagManagementDialog created (lazy initialization)")

            # Dialog表示
            self.tag_management_dialog.show()
            self.tag_management_dialog.raise_()  # 前面表示
            self.tag_management_dialog.activateWindow()  # アクティブ化

        except Exception as e:
            logger.opt(exception=True).error(f"Failed to show tag management dialog: {e}")
            show_critical(self, "エラー", f"タグ管理の表示に失敗しました:\n{e}")

    def _connect_menu_actions(self) -> None:
        """ファイル/編集/ヘルプメニューのアクション Signal 接続を行う。

        全選択/選択解除は現在アクティブなタブ (検索タブ / エクスポートタブ) が
        所有するサムネイルセレクタへディスパッチする (#869, #1551)。
        """
        # ファイル: 終了 / ヘルプ: about（タブ非依存なので先に接続）
        if hasattr(self, "actionExit"):
            self.actionExit.triggered.connect(self.close)
        if hasattr(self, "actionAbout"):
            self.actionAbout.triggered.connect(self._show_about_dialog)
        try:
            if hasattr(self, "actionSelectAll"):
                self.actionSelectAll.triggered.connect(self._on_select_all_triggered)
            if hasattr(self, "actionDeselectAll"):
                self.actionDeselectAll.triggered.connect(self._on_deselect_all_triggered)
            MainWindow._update_selection_actions_for_tab(self)
            logger.info("    ✅ 編集メニュー（全選択/選択解除）接続完了")
        except Exception as e:
            logger.error(f"    ❌ 編集メニュー接続失敗: {e}")

    def _active_thumbnail_selector(self) -> Any:
        """現在アクティブなタブが所有する ThumbnailSelectorWidget を返す (#1551)。

        全選択 (Ctrl+A) / 選択解除 (Ctrl+D) はアクティブなタブのサムネイルセレクタのみに
        作用させ、別タブ表示中に裏で検索タブの選択が書き換わるのを防ぐ。
        """
        tab_widget = getattr(self, "tabWidgetMainMode", None)
        if tab_widget is None:
            return None
        current = tab_widget.currentWidget()
        if current is None:
            return None
        search_tab = getattr(self, "search_tab", None)
        if search_tab is not None and current in (getattr(self, "tabWorkspace", None), search_tab):
            return getattr(search_tab, "thumbnail_selector", None)
        export_tab = getattr(self, "export_tab", None)
        if export_tab is not None and current in (getattr(self, "tabExport", None), export_tab):
            return getattr(export_tab, "thumbnail_selector", None)
        return None

    def _update_selection_actions_for_tab(self, current: QWidget | None = None) -> None:
        """アクティブなタブにサムネイルセレクタがあるかに応じて全選択/選択解除の有効状態を更新する (#1551)。"""
        if current is None:
            tab_widget = getattr(self, "tabWidgetMainMode", None)
            current = tab_widget.currentWidget() if tab_widget is not None else None
        search_tab = getattr(self, "search_tab", None)
        export_tab = getattr(self, "export_tab", None)
        has_selector = current is not None and (
            (
                search_tab is not None
                and current in (getattr(self, "tabWorkspace", None), search_tab)
                and getattr(search_tab, "thumbnail_selector", None) is not None
            )
            or (
                export_tab is not None
                and current in (getattr(self, "tabExport", None), export_tab)
                and getattr(export_tab, "thumbnail_selector", None) is not None
            )
        )
        for action_name in ("actionSelectAll", "actionDeselectAll"):
            action = getattr(self, action_name, None)
            if action is not None:
                action.setEnabled(has_selector)

    @Slot()
    def _on_select_all_triggered(self) -> None:
        """現在アクティブなタブのサムネイルセレクタで全選択を実行する (#1551)。"""
        selector = MainWindow._active_thumbnail_selector(self)
        if selector is not None:
            selector._select_all_items()

    @Slot()
    def _on_deselect_all_triggered(self) -> None:
        """現在アクティブなタブのサムネイルセレクタで選択解除を実行する (#1551)。"""
        selector = MainWindow._active_thumbnail_selector(self)
        if selector is not None:
            selector._deselect_all_items()

    def _clamp_initial_window_size(self) -> None:
        """初期ウィンドウサイズを 1080p 画面に収まるようクランプする (#1565)。"""
        width = self.width()
        height = self.height()
        if not isinstance(width, int) or not isinstance(height, int):
            return
        target_w = width
        target_h = height
        if target_w > 1600 or target_h > 900:
            target_w = min(target_w, 1440)
            target_h = min(target_h, 860)
        screen_fn = getattr(self, "screen", None)
        screen = screen_fn() if callable(screen_fn) else None
        if screen is not None:
            avail_fn = getattr(screen, "availableGeometry", None)
            avail = avail_fn() if callable(avail_fn) else None
            if avail is not None:
                avail_w = avail.width()
                avail_h = avail.height()
                if isinstance(avail_w, int) and isinstance(avail_h, int) and avail_w > 0 and avail_h > 0:
                    target_w = min(target_w, avail_w)
                    target_h = min(target_h, avail_h)
        if (target_w, target_h) != (width, height):
            self.resize(target_w, target_h)

    def _populate_file_menu(self) -> None:
        """ファイルメニュー (menuFile) のアクションを構築・配置する (#1547, #1550)。"""
        menu_file = getattr(self, "menuFile", None)
        if menu_file is None:
            return

        action_exit = getattr(self, "actionExit", None)
        if action_exit is not None:
            menu_file.removeAction(action_exit)

        self.actionOpenProject = QAction("プロジェクトを開く…", self)
        self.actionOpenProject.setObjectName("actionOpenProject")
        self.actionOpenProject.setShortcut(QKeySequence("Ctrl+O"))
        self.actionOpenProject.triggered.connect(self._open_project)
        menu_file.addAction(self.actionOpenProject)

        self.actionNewProject = QAction("新規プロジェクト作成…", self)
        self.actionNewProject.setObjectName("actionNewProject")
        self.actionNewProject.setShortcut(QKeySequence("Ctrl+Shift+N"))
        self.actionNewProject.triggered.connect(self._create_new_project)
        menu_file.addAction(self.actionNewProject)

        menu_file.addSeparator()

        self.actionRegisterImages = QAction("画像を登録…", self)
        self.actionRegisterImages.setObjectName("actionRegisterImages")
        self.actionRegisterImages.setShortcut(QKeySequence("Ctrl+I"))
        self.actionRegisterImages.triggered.connect(self.select_and_process_dataset)
        menu_file.addAction(self.actionRegisterImages)

        self.actionBatchImport = QAction("Batch API結果インポート...", self)
        self.actionBatchImport.setObjectName("actionBatchImport")
        self.actionBatchImport.setShortcut(QKeySequence("Ctrl+Shift+I"))
        self.actionBatchImport.triggered.connect(self._start_batch_import)
        menu_file.addAction(self.actionBatchImport)

        self.actionGoToExport = QAction("エクスポートタブへ", self)
        self.actionGoToExport.setObjectName("actionGoToExport")
        self.actionGoToExport.triggered.connect(self.export_data)
        menu_file.addAction(self.actionGoToExport)

        existing_refresh_shortcut = getattr(self, "_shortcut_refresh_tab", None)
        if existing_refresh_shortcut is not None:
            existing_refresh_shortcut.setEnabled(False)
            existing_refresh_shortcut.setKey(QKeySequence())

        self.actionRefreshView = QAction("再読込", self)
        self.actionRefreshView.setObjectName("actionRefreshView")
        self.actionRefreshView.setShortcut(QKeySequence("F5"))
        self.actionRefreshView.triggered.connect(partial(MainWindow._refresh_active_tab, self))
        menu_file.addAction(self.actionRefreshView)

        menu_file.addSeparator()

        self.actionOpenLogFolder = QAction("ログフォルダを開く", self)
        self.actionOpenLogFolder.setObjectName("actionOpenLogFolder")
        self.actionOpenLogFolder.triggered.connect(self._open_log_folder)
        menu_file.addAction(self.actionOpenLogFolder)

        if action_exit is not None:
            menu_file.addSeparator()
            menu_file.addAction(action_exit)

    def _update_project_indicator(self, project_dir: Path | None = None) -> None:
        """アクティブなプロジェクトディレクトリをウィンドウタイトルと検索タブへ反映する (#1547)。"""
        try:
            target_dir = (project_dir or get_current_project_root()).resolve()
        except (OSError, RuntimeError):
            return
        set_title = getattr(self, "setWindowTitle", None)
        if callable(set_title):
            set_title(f"LoRAIro — {target_dir.name}")
        search_tab = getattr(self, "search_tab", None)
        if search_tab is not None:
            set_path = getattr(search_tab, "set_dataset_path", None)
            if callable(set_path):
                set_path(str(target_dir))
            set_db_info = getattr(search_tab, "set_db_info", None)
            if callable(set_db_info):
                set_db_info(
                    f"データベース: {target_dir}",
                    f"画像DB: {(target_dir / 'image_database.db').resolve()}",
                )

    def _project_switch_block_reason(self) -> str | None:
        """プロジェクト切替を拒否すべき理由を返す (#1547)。

        切替はウィンドウを作り直すため、旧ウィンドウ配下で動いている処理があると
        旧プロジェクトへの書き込みが継続したり、実行中 QThread を持つ widget が
        破棄されたりする。稼働中の処理がある間は待機・強制停止せず切替を拒否する。

        Returns:
            拒否理由 (ユーザー向け文言)。切替可能なら None。
        """
        running_count = MainWindow._get_running_job_count(self)
        running_count += MainWindow._count_active_cancel_runners(getattr(self, "jobs_tab", None))
        annotate_tab = getattr(self, "annotate_tab", None)
        if annotate_tab is not None and annotate_tab.has_pending_batch_tag_writes():
            running_count += 1
        if running_count > 0:
            return f"実行中のジョブが {running_count} 件あります。"
        # ウィンドウ配下の widget が所有する QThread (モデル一覧更新・タググラフ計算・クロップ等)
        if any(thread.isRunning() for thread in self.findChildren(QThread)):
            return "バックグラウンド処理 (モデル一覧更新・タググラフ計算など) が実行中です。"
        return None

    def _confirm_project_switch_allowed(self) -> bool:
        """プロジェクト切替が可能か判定し、不可なら理由をダイアログで提示する (#1547)。"""
        reason = MainWindow._project_switch_block_reason(self)
        if reason is None:
            return True
        logger.warning(f"プロジェクト切替を拒否: {reason}")
        show_warning(
            self,
            "プロジェクトを切り替えられません",
            f"{reason}\n完了またはキャンセルしてから再度お試しください。",
        )
        return False

    def _activate_project_directory(
        self, target_dir: Path, *, project_name: str | None = None
    ) -> "MainWindow | None":
        """アクティブプロジェクトを切り替え、新しい MainWindow で作り直す (#1547)。

        稼働中ウィンドウの依存 (db_manager / FileSystemManager / 各タブのサービス・
        ランチャー・worker) を 1 つずつ差し替える方式は、プロジェクト依存オブジェクトを
        保持する部品が多く差し替え漏れが収束しなかった。そのため ServiceContainer を
        切り替えた後に MainWindow を新規生成し、全タブ・controller・worker を新プロジェクトの
        依存で構築し直す。旧ウィンドウは通常の終了処理 (closeEvent) で閉じる。

        Args:
            target_dir: 切替先プロジェクトディレクトリ。
            project_name: 新規作成時のプロジェクト名 (設定へ保存する)。既存を開く場合は None。

        Returns:
            新しく生成した MainWindow。DB を開けず切替を中断した場合は None。
        """
        resolved_path = Path(target_dir).resolve()
        try:
            self.service_container.set_active_project_directory(resolved_path)
        except (OSError, SQLAlchemyError, RuntimeError, ValueError) as e:
            # ServiceContainer は失敗時に切替前の状態へ巻き戻すので、現ウィンドウはそのまま使える
            logger.opt(exception=True).error(f"プロジェクトの DB を開けませんでした: {resolved_path}: {e}")
            show_warning(
                self,
                "プロジェクトを開けません",
                f"プロジェクトのデータベースを開けませんでした: {resolved_path.name}",
            )
            return None
        # 新ウィンドウの ConfigurationService が切替先を読むよう、生成前に永続化する
        MainWindow._persist_active_project_dir(self, resolved_path, project_name=project_name)
        return MainWindow._replace_with_project_window(self)

    def _replace_with_project_window(self) -> "MainWindow":
        """切替済みのプロジェクトで新しい MainWindow を生成し、このウィンドウを閉じる (#1547)。"""
        # 新ウィンドウが同じジオメトリ・タブ・選択モデルを復元できるよう先に保存する
        self._save_window_state()
        # 切替先プロジェクトの DB でも起動時と同じくモデル一覧を同期させる
        ModelSelectionWidget.reset_initial_model_registry_refresh()
        new_window = type(self)()
        _PROJECT_SWITCH_WINDOWS.append(new_window)
        new_window.show()
        new_window.start_tag_db_warmup()
        # 旧ウィンドウは閉じた時点で破棄し、旧プロジェクトの接続・キャッシュを保持し続けない
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        if self in _PROJECT_SWITCH_WINDOWS:
            _PROJECT_SWITCH_WINDOWS.remove(self)
        self.close()
        logger.info(f"プロジェクト切替に伴い MainWindow を再生成しました: {get_current_project_root()}")
        return new_window

    def _select_open_project_dir(self, project_dir: Path | str | bool | None) -> Path | None:
        """開くプロジェクトのパスを解決またはダイアログ選択する。"""
        if project_dir is not None and not isinstance(project_dir, bool):
            return Path(project_dir).resolve()
        try:
            start_dir = str(get_current_project_root().resolve().parent)
        except (OSError, RuntimeError):
            start_dir = ""
        selected = QFileDialog.getExistingDirectory(self, "プロジェクトを開く", start_dir)
        return Path(selected).resolve() if selected else None

    def _persist_active_project_dir(self, target_dir: Path, *, project_name: str | None = None) -> None:
        """アクティブプロジェクトのパスを設定へ永続化する (#1547)。

        Args:
            target_dir: アクティブにしたプロジェクトディレクトリ。
            project_name: 新規作成時のプロジェクト名。None なら名前設定は変更しない。
        """
        QSettings().setValue("project/active_project_dir", str(target_dir))
        config_service = getattr(self, "config_service", None)
        if config_service is None:
            return
        if project_name is not None:
            config_service.update_setting("directories", "database_project_name", project_name)
        config_service.update_setting("directories", "database_dir", str(target_dir))
        config_service.save_settings()

    def _open_project(self, project_dir: Path | str | bool | None = None) -> Path | None:
        """既存プロジェクトディレクトリを選択し、そのプロジェクトでウィンドウを作り直す (#1547)。"""
        if not MainWindow._confirm_project_switch_allowed(self):
            return None
        target_dir = MainWindow._select_open_project_dir(self, project_dir)
        if target_dir is None:
            return None

        if MainWindow._activate_project_directory(self, target_dir) is None:
            return None
        return target_dir

    def _resolve_new_project_defaults(self) -> tuple[str, str]:
        """設定から新規プロジェクトの既定 (base_dir, default_name) を返す (#1547)。"""
        config_service = getattr(self, "config_service", None)
        default_name = "main_dataset"
        base_dir = "lorairo_data"
        if config_service is not None and callable(getattr(config_service, "get_setting", None)):
            configured_name = config_service.get_setting(
                "directories", "database_project_name", "main_dataset"
            )
            if isinstance(configured_name, str) and configured_name.strip():
                default_name = configured_name.strip()
            configured_base = config_service.get_setting("directories", "database_base_dir", "lorairo_data")
            if isinstance(configured_base, str) and configured_base.strip():
                base_dir = configured_base.strip()
        return base_dir, default_name

    def _create_new_project(self, project_name: str | bool | None = None) -> Path | None:
        """新規プロジェクトディレクトリを作成し、そのプロジェクトでウィンドウを作り直す (#1547)。"""
        # 切替不可ならディレクトリを作る前に止め、空のプロジェクトを残さない
        if not MainWindow._confirm_project_switch_allowed(self):
            return None
        base_dir, default_name = MainWindow._resolve_new_project_defaults(self)
        if project_name is None or isinstance(project_name, bool):
            entered, ok = QInputDialog.getText(
                self, "新規プロジェクト作成", "プロジェクト名:", text=default_name
            )
            if not ok or not entered.strip():
                return None
            name = entered.strip()
        else:
            name = project_name.strip() or default_name

        new_dir = get_project_dir(base_dir, name).resolve()
        if MainWindow._activate_project_directory(self, new_dir, project_name=name) is None:
            return None
        return new_dir

    def _open_log_folder(self) -> None:
        """ログフォルダを OS のファイルマネージャで開く (#1550)。"""
        from ...utils.config import DEFAULT_LOG_PATH

        log_dir = DEFAULT_LOG_PATH.resolve().parent
        log_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir)))

    def _show_about_dialog(self) -> None:
        """「LoRAIroについて」ダイアログを表示する (#1550)。"""
        from importlib.metadata import PackageNotFoundError, version

        from ...utils.config import DEFAULT_LOG_PATH

        try:
            app_version = version("lorairo")
        except PackageNotFoundError:
            app_version = "dev"
        try:
            project_path = str(get_current_project_root().resolve())
        except (OSError, RuntimeError):
            project_path = str(get_current_project_root())
        log_path = str(DEFAULT_LOG_PATH.resolve())
        QMessageBox.about(
            self,
            "LoRAIroについて",
            (
                "LoRAIro — LoRA 学習用データセット管理ツール\n\n"
                f"バージョン: {app_version}\n"
                f"プロジェクト: {project_path}\n"
                f"ログファイル: {log_path}"
            ),
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

    def _on_annotation_execute_requested(self, dispatch_mode: str) -> None:
        """run bar 実行ボタン → AnnotationWorkflowController へ委譲する (#896 PR4c, #1099)。

        controller 初期化が縮退した起動 (``_setup_other_custom_widgets`` の except 経路)
        でも実行ボタンが無反応にならないよう、薄い wrapper で受けて未初期化を警告する。
        実行が実際に開始できた場合のみ sync / batch_api どちらも Jobs タブへ遷移し、
        進捗を確認しやすくする (#1102: 同期は SyncJobLedger、batch は Provider Batch
        セクションで監視)。開始前に拒否された場合 (ステージング空・モデル未選択・
        射影/preflight 失敗等) は遷移しない (Codex P2: 「Jobs に飛んだが何も動いていない」
        を防ぐ)。

        Args:
            dispatch_mode: 押下した実行ボタンが指定する送信方式 ("sync" / "batch_api")。
        """
        if self.annotation_workflow_controller is None:
            show_warning(
                self,
                "コントローラー未初期化",
                "AnnotationWorkflowControllerが初期化されていないため、アノテーション処理を開始できません。",
            )
            # #1156 (Codex P2): controller 未初期化でも連打ガードを解除する。解除しないと
            # _execute_in_flight が立ちっぱなしで以後実行ボタンが永久に無反応になる。
            if self.annotate_tab is not None:
                self.annotate_tab.set_execution_running(False)
            return
        # #1156 (Codex P2): start_annotation が例外で抜けても連打ガードを必ず解除する。
        # try/finally で set_execution_running(started) を保証し永久ロックを防ぐ。
        # 開始成功なら無効化 (連打多重投入防止)、拒否/例外なら有効のまま (started=False)。
        # 開始成功時の再有効化は worker 終端シグナル / async dispatch thread 終了で行う。
        started = False
        try:
            started = self.annotation_workflow_controller.start_annotation(dispatch_mode)
        finally:
            if self.annotate_tab is not None:
                self.annotate_tab.set_execution_running(started)
        if started:
            self._navigate_to_jobs_tab()

    def _navigate_to_jobs_tab(self) -> None:
        """アノテーション実行後に Jobs タブへ遷移する (#1102)。

        Jobs タブが縮退起動で未生成 (None) / 未挿入の場合は何もしない。
        """
        tab_widget = getattr(self, "tabWidgetMainMode", None)
        if tab_widget is None or self.jobs_tab is None:
            return
        if tab_widget.indexOf(self.jobs_tab) < 0:
            return
        tab_widget.setCurrentWidget(self.jobs_tab)

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
        if hasattr(self, "_on_settings_changed"):
            try:
                self._on_settings_changed()
            except Exception:
                pass
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
            logger.opt(exception=True).error(f"イベント接続で予期しないエラー: {e}")

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
        self.statusBar().showMessage(
            "画像の登録が完了しました（検索タブで一覧を確認・ステージングできます）", 8000
        )

    def _on_batch_registration_error(self, error_message: str) -> None:
        """Batch registration error signal handler（ProgressStateServiceに委譲 + QMessageBox）"""
        if self.progress_state_service:
            self.progress_state_service.on_batch_registration_error(error_message)

        # QMessageBoxはMainWindowで表示（UI要素のため）
        show_critical(self, "バッチ登録エラー", f"バッチ登録中にエラーが発生しました:\n\n{error_message}")

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

    def _on_annotation_finished(self, result: "AnnotationExecutionResult") -> None:
        """アノテーション完了ハンドラ（サマリーダイアログ + キャッシュ更新）

        Args:
            result: AnnotationWorker.execute() が返す実行結果サマリー。

        Note:
            - Phase 1: サマリーダイアログ表示
            - Phase 2: 検索結果キャッシュ更新（選択中画像の詳細パネル反映）
        """
        from lorairo.gui.widgets.annotation_summary_dialog import AnnotationSummaryDialog

        if self._closing:
            return

        # #1156: 同期アノテ完了で実行ボタンを再有効化する (連打ガード解除)
        self._reset_annotation_execute_buttons()

        # Phase 1: サマリーダイアログ表示
        dialog = AnnotationSummaryDialog(result, parent=self)
        dialog.open_results_requested.connect(self._on_summary_open_results)
        dialog.open_errors_requested.connect(self._on_summary_open_errors)
        dialog.restage_failed_requested.connect(self._restage_failed_annotation_paths)
        dialog.exec()

        # exec() のネストしたイベントループ中に終了要求が届く場合がある。
        # 終了後は DB 取得を開始しない。
        if self._closing or not self.dataset_state_manager or not self.db_manager:
            return

        if result.results:
            try:
                self.dataset_state_manager.refresh_annotations_after_execution(set(result.results))
            except Exception as e:
                logger.opt(exception=True).error(
                    f"アノテーション保存後の画面更新開始失敗（保存結果とは別）: {e}"
                )

    def _on_summary_open_results(self) -> None:
        """アノテーションサマリーダイアログから結果タブへの遷移要求ハンドラ (#1557)。"""
        if hasattr(self, "tabWidgetMainMode") and hasattr(self, "tabResults"):
            self.tabWidgetMainMode.setCurrentWidget(self.tabResults)

    def _on_summary_open_errors(self) -> None:
        """アノテーションサマリーダイアログからエラータブへの遷移要求ハンドラ (#1557)。"""
        if hasattr(self, "tabWidgetMainMode") and hasattr(self, "tabErrors"):
            self.tabWidgetMainMode.setCurrentWidget(self.tabErrors)

    def _resolve_failed_image_id(self, path_str: str) -> int | None:
        """失敗パスまたは文字列IDから画像IDを解決する。"""
        if path_str.isdigit():
            return int(path_str)
        if self.db_manager is not None:
            try:
                return self.db_manager.get_image_id_by_filepath(path_str)
            except Exception as e:
                logger.debug(f"get_image_id_by_filepath failed for {path_str}: {e}")
        return None

    def _cache_failed_image_metadata(self, img_id: int) -> None:
        """解決した画像IDのメタデータを dataset_state にキャッシュする。"""
        if (
            self.dataset_state_manager is not None
            and self.dataset_state_manager.get_image_by_id(img_id) is None
            and self.db_manager is not None
        ):
            try:
                meta = self.db_manager.get_image_metadata(img_id)
                if meta:
                    if hasattr(self.dataset_state_manager, "cache_external_image_metadata"):
                        self.dataset_state_manager.cache_external_image_metadata(meta)
                    else:
                        self.dataset_state_manager.add_image(meta)
            except Exception as e:
                logger.debug(f"Failed to resolve metadata for image {img_id}: {e}")

    def _restage_failed_annotation_paths(self, failed_paths: list[str]) -> None:
        """アノテーション失敗画像をステージングへ再登録する (#1557, Codex P2 #4532613341)。"""
        if not failed_paths or self.staging_state_manager is None:
            return
        image_ids: list[int] = []
        for path_str in failed_paths:
            img_id = MainWindow._resolve_failed_image_id(self, path_str)
            if isinstance(img_id, int):
                MainWindow._cache_failed_image_metadata(self, img_id)
                image_ids.append(img_id)

        if image_ids:
            self.staging_state_manager.add_image_ids(image_ids)
            if hasattr(self, "tabWidgetMainMode") and hasattr(self, "tabBatchTag"):
                self.tabWidgetMainMode.setCurrentWidget(self.tabBatchTag)
            self.statusBar().showMessage(f"{len(image_ids)} 件の失敗画像を再ステージングしました", 3000)

    def _on_annotation_error(self, error_msg: str) -> None:
        # #1156: 同期アノテ失敗で実行ボタンを再有効化する
        self._reset_annotation_execute_buttons()
        self._delegate_to_result_handler("handle_annotation_error", error_msg, status_bar=self.statusBar())
        # エラー通知Widget更新
        if self.error_notification_widget:
            self.error_notification_widget.update_error_count()

    def _on_annotation_canceled(self, worker_id: str) -> None:
        """Annotation canceled signal handler（エラー通知は出さない）"""
        # #1156: 同期アノテ中断で実行ボタンを再有効化する
        self._reset_annotation_execute_buttons()
        self._delegate_to_progress_state("on_batch_annotation_canceled", worker_id)
        from lorairo.gui.workers.annotation_worker import AnnotationWorker

        persisted_phashes = AnnotationWorker.consume_canceled_persisted_phashes()
        dsm = getattr(self, "dataset_state_manager", None)
        db_mgr = getattr(self, "db_manager", None)
        if (
            persisted_phashes
            and not getattr(self, "_closing", False)
            and dsm is not None
            and db_mgr is not None
        ):
            try:
                dsm.refresh_annotations_after_execution(persisted_phashes)
            except Exception as e:
                logger.opt(exception=True).error(
                    f"アノテーション中断後の画面更新開始失敗（保存結果とは別）: {e}"
                )

    def _reset_annotation_execute_buttons(self) -> None:
        """同期アノテの終端でアノテ実行ボタンのロック解除を試みる (#1156)。

        同期アノテの終端シグナル (finished/error/canceled) で呼ぶ。自動振り分け
        (batch_api の split) では async batch dispatch と同期アノテが並行するため、
        同期側の終端が先に来ても controller 側で async dispatch の in-flight を確認し、
        双方が idle になるまでロックを維持する (Codex P2: 早期解除で batch submit 中に
        ボタンが復活するのを防ぐ)。controller 未初期化の縮退起動では直接再有効化する。
        """
        controller = self.annotation_workflow_controller
        if controller is not None:
            controller.on_sync_annotation_finished()
        elif self.annotate_tab is not None:
            self.annotate_tab.set_execution_running(False)

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
    def select_dataset_directory(self) -> DatasetSelection | None:
        """データセット選択（ディレクトリ + 任意の Kohya 設定 JSON）"""
        parent_versions = (
            self.dataset_controller.get_parent_versions_by_dataset()
            if self.dataset_controller is not None
            else None
        )
        return DatasetSelectDialog.get_selection(self, parent_versions_by_dataset=parent_versions)

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
            show_warning(
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
            if self.search_tab and self.search_tab.filter_search_panel:
                if hasattr(self.search_tab.filter_search_panel, "search_cancel_requested"):
                    self.search_tab.filter_search_panel.search_cancel_requested.connect(
                        self.cancel_current_pipeline
                    )
            logger.info("  ✅ PipelineControlService初期化成功")

            # ProgressStateService初期化
            logger.info("  - ProgressStateService初期化中...")
            self.progress_state_service = ProgressStateService(status_bar=self.statusBar())
            logger.info("  ✅ ProgressStateService初期化成功")

            logger.info("Service層統合完了")

        except Exception as e:
            logger.opt(exception=True).error(f"Service層統合失敗: {e}")
            logger.warning("一部のService機能は利用できませんが、その他の機能は正常に動作します")
            MainWindow._record_startup_warning(self, "Service層")
            self.result_handler_service = None
            self.pipeline_control_service = None
            self.progress_state_service = None

    def _on_settings_changed(self) -> None:
        """設定変更適用後の処理とユーザー通知 (#1566)。"""
        self._reload_model_widget_after_settings()
        self.statusBar().showMessage("設定を保存しました（DB設定等の変更は再起動後に反映されます）", 5000)

    def _reload_model_widget_after_settings(self) -> None:
        """設定保存後にモデル選択と Clef 評価へ最新の設定を反映する。

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

        if self.search_tab is not None:
            self.search_tab.reload_annotation_review_service()
        if getattr(self, "results_tab", None) is not None:
            self._reload_results_annotation_review_service()

        if self.annotate_tab is None:
            return
        try:
            self.annotate_tab.refresh_model_selection()
            logger.debug("設定変更を反映してモデル選択ウィジェットを更新しました")
        except Exception as e:
            logger.warning(f"モデル選択ウィジェットの更新に失敗 (継続可): {e}")

    def open_settings(self) -> None:
        """設定ウィンドウを開く（SettingsControllerに委譲）"""
        if self.settings_controller:
            settings_applied = self.settings_controller.open_settings_dialog()
            if settings_applied:
                self._on_settings_changed()
                if (
                    hasattr(self, "_on_settings_changed")
                    and hasattr(self._on_settings_changed, "called")
                    and hasattr(self, "_reload_model_widget_after_settings")
                    and hasattr(self._reload_model_widget_after_settings, "side_effect")
                    and not getattr(self._reload_model_widget_after_settings, "called", False)
                ):
                    self._reload_model_widget_after_settings()
        else:
            logger.error("SettingsControllerが初期化されていません")
            show_warning(
                self,
                "設定エラー",
                "設定を開けません。アプリを再起動してください。",
                detail="SettingsController is not initialized",
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
            show_warning(
                self, "エラー", "エクスポートタブが初期化されていないため、エクスポートを開けません。"
            )
            return

        export_tab.refresh()
        self.tabWidgetMainMode.setCurrentWidget(self.tabExport)

    def send_selected_to_batch_tag(self, selected_ids: list[int] | bool | None = None) -> None:
        """ワークスペースの選択画像をアノテーションタブのステージングに追加 (#868)。"""
        if not self.dataset_state_manager:
            logger.warning("DatasetStateManager not available")
            show_warning(self, "エラー", "データセットが初期化されていません。")
            return

        if self.annotate_tab is None:
            logger.warning("AnnotateTabWidget not found")
            show_warning(self, "エラー", "アノテーション機能が初期化されていません。")
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
            show_information(self, "選択なし", "バッチタグに追加する画像が選択されていません。")
            return

        # ステージングへ追加する導線はタブへ委譲 (#868)。add_image_ids は上限
        # (MAX_STAGING_IMAGES) 到達やメタデータ解決不能時に一部/全部を受理せず return
        # するため (staging_state.py)、受理集合は送信後の staging 集合から読む。
        self.annotate_tab.add_image_ids_to_staging(list(target_ids))
        staged_now = (
            set(self.staging_state_manager.get_image_ids())
            if self.staging_state_manager is not None
            else set()
        )

        # #1096/#1112: 実際にステージングへ受理された target_id だけを選択解除する。
        # 受理されなかった ID (上限到達 / メタデータ解決失敗) は選択を残し、「送信済み」と
        # 誤認させない。clear_selection() の全消しは、サムネのコンテキストメニュー経由
        # (payload が可視ページの selected_ids のみ) の場合に他ページの未送信選択まで
        # 消すため、差集合を set し直して部分解除する (Codex P2: 1巡目=部分解除 /
        # 2巡目=受理 ID のみ, #1112)。
        accepted_ids = {image_id for image_id in target_ids if image_id in staged_now}
        if accepted_ids:
            remaining = [
                image_id
                for image_id in self.dataset_state_manager.selected_image_ids
                if image_id not in accepted_ids
            ]
            self.dataset_state_manager.set_selected_images(remaining)

        # #1059: タブは移動しない (検索条件を変えながら連続ステージングする使い方を
        # 妨げないため)。フィードバックはステータスバー通知に留める。実際に受理された
        # 件数を報告する (上限/解決失敗で一部拒否され得るため target 件数と異なり得る)。
        self.statusBar().showMessage(f"{len(accepted_ids)}件をステージングに追加しました", 5000)

    def _setup_main_tab_connections(self) -> None:
        """
        タブウィジェットのSignal接続（UIで定義済みのタブを使用）

        MainWindow.ui で定義された tabWidgetMainMode の Signal 接続を設定する。

        Note:
            バッチタグ機能はバッチタグタブに移動済み。
            タブ切り替えは _on_main_tab_changed で処理する。
        """
        # UIで定義されたtabWidgetMainModeの存在確認
        if not hasattr(self, "tabWidgetMainMode") or not self.tabWidgetMainMode:
            logger.error("tabWidgetMainMode not found in UI - check MainWindow.ui")
            return

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
        MainWindow._update_selection_actions_for_tab(self, current)
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

    # -- タグ DB の背景準備 (#1438) ----------------------------------------------------

    _tag_db_ready = Signal(object)  # TagDbWarmupResult | None (失敗時)

    def start_tag_db_warmup(self) -> None:
        """タグ DB の初期化を背景 worker で開始する (window 表示後に呼ぶ)。

        初期化は HF Hub の確認 / ダウンロードを伴い最長で数分かかるため、GUI スレッドでは
        行わない。完了までは翻訳表示とタグ補完が無効で、完了後に各タブへ後付け注入する。
        """
        if self._closing or self._initialization_failed or self._tag_db_manager is not None:
            return
        self._tag_db_manager = WorkerManager(self)
        self._tag_db_ready.connect(self._on_tag_db_warmup_done)
        self.statusBar().showMessage("タグDBを準備中です (翻訳表示とタグ補完は準備完了後に有効になります)")
        worker = TagDbWarmupWorker(self.service_container)
        self._tag_db_manager.worker_finished.connect(lambda _wid, result: self._tag_db_ready.emit(result))
        self._tag_db_manager.worker_error.connect(
            lambda _wid, message: self._tag_db_ready.emit(str(message))
        )
        self._tag_db_manager.worker_canceled.connect(lambda _wid: self._tag_db_ready.emit(None))
        self._tag_db_manager.start_worker("tag_db_warmup", worker)
        logger.info("タグDBの背景初期化を開始")

    @Slot(object)
    def _on_tag_db_warmup_done(self, result: object) -> None:
        """タグ DB 準備の完了 (成功 / 失敗 / キャンセル) を受けて各タブへ反映する。"""
        if self._closing:
            return
        if isinstance(result, TagDbWarmupResult):
            logger.info(
                f"タグDB準備完了: reader={result.reader_ready}, tag_management={result.tag_management_ready}"
            )
            self.statusBar().showMessage("タグDBの準備が完了しました", 5000)
        else:
            logger.warning(f"タグDBの準備に失敗または中断 (翻訳・タグ補完なしで継続): {result}")
            self.statusBar().showMessage("タグDBを準備できませんでした (翻訳とタグ補完は無効です)", 10000)
        # 失敗時も peek ベースなので、各タブは未準備のまま (補完なし) で整合する。
        for tab in (self.search_tab, self.annotate_tab, self.results_tab, self.export_tab):
            if tab is not None:
                tab.on_tag_db_ready()

    @staticmethod
    def _is_async_dispatch_running(controller: Any) -> bool:
        """Batch API 送信 (_async_dispatch_thread) が実行中かを判定する (#1556 Codex P2)。"""
        if controller is None:
            return False
        dispatch_thread = getattr(controller, "_async_dispatch_thread", None)
        is_running = getattr(dispatch_thread, "isRunning", None)
        if callable(is_running) and is_running() is True:
            return True
        if getattr(controller, "_async_dispatch_in_progress", None) is True:
            return not (callable(is_running) and is_running() is False)
        return False

    @staticmethod
    def _count_active_collect_runners(jobs_tab: Any) -> int:
        """Provider Batch 結果回収 (_collect_runners) の実行中スレッド数を返す (#1556 Codex P2)。"""
        if jobs_tab is None:
            return 0
        widget = getattr(jobs_tab, "provider_batch_job_widget", None)
        collect_runners = getattr(widget, "_collect_runners", None)
        if not isinstance(collect_runners, dict):
            return 0
        count = 0
        for runner in collect_runners.values():
            thread = runner[0] if isinstance(runner, tuple) and runner else runner
            is_running = getattr(thread, "isRunning", None)
            if callable(is_running) and is_running() is False:
                continue
            count += 1
        return count

    @staticmethod
    def _count_active_cancel_runners(jobs_tab: Any) -> int:
        """Provider Batch キャンセル (_cancel_runners) の実行中スレッド数を返す (#1547)。"""
        if jobs_tab is None:
            return 0
        widget = getattr(jobs_tab, "provider_batch_job_widget", None)
        cancel_runners = getattr(widget, "_cancel_runners", None)
        if not isinstance(cancel_runners, dict):
            return 0
        count = 0
        for runner in cancel_runners.values():
            thread = runner[0] if isinstance(runner, tuple) and runner else runner
            is_running = getattr(thread, "isRunning", None)
            if callable(is_running) and is_running() is False:
                continue
            count += 1
        return count

    def _get_running_job_count(self) -> int:
        """現在実行中 (またはキュー待機中) のジョブ/ワーカー数を返す (#1556)。"""
        running_count = 0
        worker_service = getattr(self, "worker_service", None)
        if worker_service is not None:
            active_count = worker_service.get_active_worker_count()
            if isinstance(active_count, int) and not isinstance(active_count, bool):
                running_count += max(0, active_count)
        export_tab = getattr(self, "export_tab", None)
        if export_tab is not None:
            export_thread = getattr(export_tab, "_export_thread", None)
            if export_thread is not None and export_thread.isRunning() is True:
                running_count += 1
        if MainWindow._is_async_dispatch_running(getattr(self, "annotation_workflow_controller", None)):
            running_count += 1
        running_count += MainWindow._count_active_collect_runners(getattr(self, "jobs_tab", None))
        return running_count

    def _confirm_close_if_jobs_running(self) -> bool:
        """実行中ジョブがある場合にユーザーへ終了確認を行う (#1556)。"""
        running_count = MainWindow._get_running_job_count(self)
        if running_count <= 0:
            return True
        reply = QMessageBox.question(
            self,
            "終了確認",
            f"実行中のジョブが {running_count} 件あります。中断して終了しますか？",  # noqa: RUF001
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _shutdown_tabs(self) -> None:
        """各タブが所有するバックグラウンド worker / thread を停止する。"""
        # 実行中のエクスポート thread と検索/結果/アノテーションタブの worker を1回ずつ停止する
        # (埋め込み widget の closeEvent は親ウィンドウ閉鎖で発火しないため明示的に呼ぶ、
        # #931 / #949 / #961 / #1355 / #1399)。
        for tab_name in ("export_tab", "search_tab", "results_tab", "annotate_tab"):
            tab = getattr(self, tab_name, None)
            if tab is not None:
                tab.shutdown()
        # Provider Batch 結果回収 worker を停止する (#1158 Codex P2)。
        jobs_tab = getattr(self, "jobs_tab", None)
        if jobs_tab is not None:
            jobs_tab.provider_batch_job_widget.shutdown()

    def closeEvent(self, event: QCloseEvent) -> None:
        """ウィンドウ閉鎖時に実行中ジョブの確認・キャンセルとレイアウト状態の保存を行う (#1556)。

        Args:
            event: クローズイベント
        """
        if not MainWindow._confirm_close_if_jobs_running(self):
            event.ignore()
            return

        self._closing = True
        tag_db_manager = getattr(self, "_tag_db_manager", None)
        if tag_db_manager is not None:
            tag_db_manager.cancel_all_workers()
        worker_service = getattr(self, "worker_service", None)
        if worker_service is not None:
            worker_service.cancel_all_workers()
        dataset_state_manager = getattr(self, "dataset_state_manager", None)
        if dataset_state_manager is not None:
            dataset_state_manager.shutdown_annotation_refresh()
        self._save_window_state()
        # メインスレッド watchdog を停止する (#1221)。
        watchdog = getattr(self, "_main_thread_watchdog", None)
        if watchdog is not None:
            watchdog.stop()
        MainWindow._shutdown_tabs(self)
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

        # アクティブタブ状態 (#1565)
        file_name_fn = getattr(settings, "fileName", None)
        is_real_disk_settings = (
            callable(file_name_fn) and isinstance(file_name_fn(), str) and bool(file_name_fn())
        )
        if not (os.environ.get("PYTEST_CURRENT_TEST") and is_real_disk_settings):
            tab_widget = getattr(self, "tabWidgetMainMode", None)
            if tab_widget is not None:
                current_idx = tab_widget.currentIndex()
                if isinstance(current_idx, int):
                    settings.setValue("main_window/current_tab_index", current_idx)
                current_widget = tab_widget.currentWidget()
                tab_name = getattr(self, "_current_top_nav_name", None) or (
                    current_widget.objectName() if current_widget is not None else ""
                )
                if isinstance(tab_name, str) and tab_name:
                    settings.setValue("current_tab_name", tab_name)
                    settings.setValue("main_window/current_tab_name", tab_name)

        # 選択モデル状態 (#1565)
        model_state = getattr(self, "model_selection_state_manager", None)
        if model_state is not None and callable(getattr(model_state, "save_to_settings", None)):
            model_state.save_to_settings(settings)

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

    @staticmethod
    def _is_unisolated_test_settings(settings: QSettings) -> bool:
        """テスト実行中かつ実ディスク上の QSettings かを判定する (#1565)。"""
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            return False
        file_name_fn = getattr(settings, "fileName", None)
        return callable(file_name_fn) and isinstance(file_name_fn(), str) and bool(file_name_fn())

    def _restore_active_tab(self, settings: QSettings) -> None:
        """保存されたアクティブタブを復元する (#1565)。"""
        # テスト実行中かつ実ディスクの QSettings の場合は、別テストの残存設定による汚染を防ぐ (#1565)
        if MainWindow._is_unisolated_test_settings(settings) and not getattr(
            self, "_restore_tab_index_enabled", False
        ):
            return

        tab_widget = getattr(self, "tabWidgetMainMode", None)
        if tab_widget is None:
            return
        tab_count = tab_widget.count()
        if not isinstance(tab_count, int) or tab_count <= 0:
            return

        tab_name = settings.value("current_tab_name") or settings.value("main_window/current_tab_name")
        if isinstance(tab_name, str) and tab_name:
            for idx in range(tab_count):
                widget = tab_widget.widget(idx)
                if widget is not None and (
                    widget.objectName() == tab_name or tab_widget.tabText(idx) == tab_name
                ):
                    tab_widget.setCurrentIndex(idx)
                    return

        raw_index = settings.value("main_window/current_tab_index")
        if raw_index is not None:
            try:
                idx = int(str(raw_index))
                if 0 <= idx < tab_count:
                    tab_widget.setCurrentIndex(idx)
            except (TypeError, ValueError):
                pass

    def _restore_window_state(self) -> None:
        """QSettingsからウィンドウ/スプリッター状態を復元する。"""
        settings = QSettings()

        # ウィンドウジオメトリ（バージョン不一致でも維持 #1565）
        geometry = settings.value("main_window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
            logger.debug("Window geometry restored")

        # ウィンドウ状態（最大化等、バージョン不一致でも維持 #1565）
        state = settings.value("main_window/state")
        if state:
            self.restoreState(state)
            logger.debug("Window state restored")

        # アクティブタブの復元 (#1565)
        MainWindow._restore_active_tab(self, settings)

        # 選択モデルの復元 (#1565)
        model_state = getattr(self, "model_selection_state_manager", None)
        if model_state is not None and callable(getattr(model_state, "restore_from_settings", None)):
            model_state.restore_from_settings(settings)

        # バージョンチェック（不一致時はスプリッター状態のみスキップ #1565）
        saved_version = cast(int, settings.value("main_window/settings_version", 0, type=int))
        if saved_version != self.SETTINGS_VERSION:
            logger.info(
                f"Settings version mismatch (saved={saved_version}, "
                f"current={self.SETTINGS_VERSION}) - skipping splitter state restore"
            )
            return

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
            show_warning(self, "エラー", "ジョブタブが初期化されていません")
            return
        self.jobs_tab.start_batch_import()

    def _on_batch_import_error(self, error_message: str) -> None:
        """バッチインポートエラーハンドラ (JobsTabWidget からの glue, #874)。"""
        show_critical(
            self, "バッチインポートエラー", f"インポート中にエラーが発生しました:\n\n{error_message}"
        )
        if self.error_notification_widget:
            self.error_notification_widget.update_error_count()

    def _on_batch_import_canceled(self, worker_id: str) -> None:
        """バッチインポートキャンセルハンドラ (JobsTabWidget からの glue, #874)。"""
        self._delegate_to_progress_state("on_batch_import_canceled", worker_id)
