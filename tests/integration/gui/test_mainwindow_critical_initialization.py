"""MainWindow初期化の致命的エラー処理の統合テスト

このテストはMainWindowの初期化時に発生する可能性のある致命的エラー経路を検証します。
特にSearchFilterService統合の失敗ケースを網羅的にテストします。

テスト戦略:
- 統合テスト: モックのみ使用（test_strategy_policy_change_2025_11_06準拠）
- 致命的失敗時の動作検証: sys.exit、logger.critical、QMessageBoxの呼び出し
- ヘッドレス環境対応: QT_QPA_PLATFORM=offscreen で実行可能
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from lorairo.gui.window.main_window import MainWindow


@pytest.mark.integration
@pytest.mark.fast_integration
class TestMainWindowCriticalInitializationFailures:
    """MainWindow初期化の致命的エラー経路テスト"""

    @pytest.fixture
    def critical_failure_hooks(self, monkeypatch):
        """致命的失敗時のhookをモック

        Args:
            monkeypatch: pytestのmonkeypatchフィクスチャ

        Returns:
            dict: モック呼び出しを記録する辞書
                - "sys_exit": sys.exit()の呼び出し記録
                - "messagebox": QMessageBox関連の呼び出し記録
                - "logger": モック化されたlogger
        """
        calls = {
            "sys_exit": [],
            "messagebox_instances": [],
            "logger": MagicMock(),
        }

        # sys.exitをモック（SystemExit例外を発生させる）
        def mock_sys_exit(code):
            calls["sys_exit"].append(code)
            # SystemExit例外を発生させる（sys.exitの本来の動作を模倣）
            raise SystemExit(code)

        # Note: main_window.pyは_handle_critical_initialization_failure内で
        # "import sys"をローカルインポートしているため、sysモジュール自体をパッチ
        import sys

        monkeypatch.setattr(sys, "exit", mock_sys_exit)

        # QMessageBoxをモック（ヘッドレス環境対応）
        def _create_mock_messagebox(*_args, **_kwargs):
            instance = Mock()
            calls["messagebox_instances"].append(instance)
            return instance

        mock_messagebox_class = Mock(side_effect=_create_mock_messagebox)

        # QMessageBox.Iconの列挙型をモック
        mock_icon = Mock()
        mock_icon.Critical = Mock()
        mock_messagebox_class.Icon = mock_icon

        monkeypatch.setattr("lorairo.gui.window.main_window.QMessageBox", mock_messagebox_class)

        # loggerをモック
        monkeypatch.setattr("lorairo.gui.window.main_window.logger", calls["logger"])

        return calls

    @pytest.fixture
    def mock_services(self, monkeypatch):
        """MainWindow初期化に必要な外部サービスをモック

        Args:
            monkeypatch: pytestのmonkeypatchフィクスチャ
        """
        # ConfigurationServiceをモック
        mock_config = Mock()
        monkeypatch.setattr(
            "lorairo.gui.window.main_window.ConfigurationService", Mock(return_value=mock_config)
        )

        # ServiceContainerをモック
        mock_container = Mock()
        mock_container.image_db_manager = Mock()
        mock_container.image_repository = Mock()
        monkeypatch.setattr(
            "lorairo.gui.window.main_window.get_service_container", Mock(return_value=mock_container)
        )

        # WorkerServiceをモック
        mock_worker = Mock()
        mock_worker.get_active_worker_count = Mock(return_value=0)
        monkeypatch.setattr("lorairo.gui.window.main_window.WorkerService", Mock(return_value=mock_worker))

        # DatasetStateManagerをモック
        monkeypatch.setattr("lorairo.gui.window.main_window.DatasetStateManager", Mock())

        # FileSystemManagerをモック
        monkeypatch.setattr("lorairo.gui.window.main_window.FileSystemManager", Mock())

    # ============================================================================
    # Phase 2: サービス初期化経路テスト
    # ============================================================================

    def test_configuration_service_initialization_failure(self, qtbot, critical_failure_hooks, monkeypatch):
        """ConfigurationService初期化失敗時の致命的失敗テスト

        検証項目:
        - sys.exit(1)が呼ばれること
        - logger.criticalが呼ばれること
        - QMessageBoxが表示されること
        - エラーメッセージに"ConfigurationService"が含まれること
        """

        # ConfigurationService()コンストラクタが例外を投げるようにモック
        def mock_config_init_with_exception(*args, **kwargs):
            raise RuntimeError("設定ファイル読み込み失敗（テスト用例外）")

        monkeypatch.setattr(
            "lorairo.gui.window.main_window.ConfigurationService",
            mock_config_init_with_exception,
        )

        # ServiceContainerは正常（ConfigurationServiceのみ失敗）
        mock_container = Mock()
        mock_container.db_manager = Mock()
        mock_container.image_repository = Mock()
        monkeypatch.setattr(
            "lorairo.gui.window.main_window.get_service_container",
            Mock(return_value=mock_container),
        )

        # MainWindowの初期化を試みる（致命的エラーが発生する）
        try:
            window = MainWindow()
            qtbot.addWidget(window)
        except SystemExit:
            pass

        # 検証1: sys.exit(1)が呼ばれたこと
        assert len(critical_failure_hooks["sys_exit"]) == 1
        assert critical_failure_hooks["sys_exit"][0] == 1

        # 検証2: logger.criticalが呼ばれたこと
        critical_failure_hooks["logger"].critical.assert_called()
        logger_args = critical_failure_hooks["logger"].critical.call_args
        assert "ConfigurationService" in str(logger_args)

        # 検証3: QMessageBoxが作成・表示されたこと
        assert len(critical_failure_hooks["messagebox_instances"]) > 0
        messagebox = critical_failure_hooks["messagebox_instances"][0]
        messagebox.exec.assert_called()

        # 検証4: エラーメッセージに"ConfigurationService"が含まれること
        text_args = messagebox.setText.call_args
        assert "ConfigurationService" in str(text_args)

    def test_worker_service_initialization_failure(self, qtbot, critical_failure_hooks, monkeypatch):
        """WorkerService初期化失敗時の致命的失敗テスト

        検証項目:
        - sys.exit(1)が呼ばれること
        - logger.criticalが呼ばれること
        - QMessageBoxが表示されること
        - エラーメッセージに"WorkerService"が含まれること
        """

        # WorkerService()コンストラクタが例外を投げるようにモック
        def mock_worker_init_with_exception(*args, **kwargs):
            raise RuntimeError("WorkerService初期化失敗（テスト用例外）")

        monkeypatch.setattr(
            "lorairo.gui.window.main_window.WorkerService",
            mock_worker_init_with_exception,
        )

        # ServiceContainer/ConfigurationServiceは正常
        mock_container = Mock()
        mock_container.db_manager = Mock()
        mock_container.image_repository = Mock()
        monkeypatch.setattr(
            "lorairo.gui.window.main_window.get_service_container",
            Mock(return_value=mock_container),
        )

        mock_config = Mock()
        monkeypatch.setattr(
            "lorairo.gui.window.main_window.ConfigurationService",
            Mock(return_value=mock_config),
        )

        # FileSystemManagerも正常（WorkerServiceの依存）
        monkeypatch.setattr(
            "lorairo.gui.window.main_window.FileSystemManager",
            Mock(),
        )

        # MainWindowの初期化を試みる（致命的エラーが発生する）
        try:
            window = MainWindow()
            qtbot.addWidget(window)
        except SystemExit:
            pass

        # 検証1: sys.exit(1)が呼ばれたこと
        assert len(critical_failure_hooks["sys_exit"]) == 1
        assert critical_failure_hooks["sys_exit"][0] == 1

        # 検証2: logger.criticalが呼ばれたこと
        critical_failure_hooks["logger"].critical.assert_called()
        logger_args = critical_failure_hooks["logger"].critical.call_args
        assert "WorkerService" in str(logger_args)

        # 検証3: QMessageBoxが作成・表示されたこと
        assert len(critical_failure_hooks["messagebox_instances"]) > 0
        messagebox = critical_failure_hooks["messagebox_instances"][0]
        messagebox.exec.assert_called()

        # 検証4: エラーメッセージに"WorkerService"が含まれること
        text_args = messagebox.setText.call_args
        assert "WorkerService" in str(text_args)

    # ============================================================================
    # Phase 3.5: SearchFilterService統合経路テスト
    # ============================================================================

    def test_missing_filter_search_panel_triggers_critical_failure(
        self, qtbot, critical_failure_hooks, monkeypatch
    ):
        """filterSearchPanel属性欠落時の致命的失敗テスト

        検証項目:
        - sys.exit(1)が呼ばれること
        - logger.criticalが呼ばれること
        - QMessageBoxが表示されること
        - エラーメッセージに"filterSearchPanel"が含まれること
        """

        # setupUi()をモックして、filterSearchPanelを作成しない
        def mock_setupui(ui_self, main_window_instance):
            """Ui_MainWindow.setupUi()のモック

            Args:
                ui_self: Ui_MainWindowインスタンス（使用しない）
                main_window_instance: MainWindowインスタンス（属性を設定する対象）
            """
            # filterSearchPanel属性を意図的に作成しない
            # その他の必須属性は作成
            main_window_instance.centralwidget = Mock()

        # MainWindowインポート前にUi_MainWindowをパッチ
        monkeypatch.setattr("lorairo.gui.designer.MainWindow_ui.Ui_MainWindow.setupUi", mock_setupui)

        # MainWindowの初期化を試みる（致命的エラーが発生する）
        try:
            window = MainWindow()
            qtbot.addWidget(window)
        except SystemExit:
            # SystemExitはモックがraise SystemExitするため発生する
            pass

        # 検証1: sys.exit(1)が呼ばれたこと
        assert len(critical_failure_hooks["sys_exit"]) == 1, "sys.exit()が呼ばれていない"
        assert critical_failure_hooks["sys_exit"][0] == 1, "sys.exit()の引数が1でない"

        # 検証2: logger.criticalが呼ばれたこと
        critical_failure_hooks["logger"].critical.assert_called()
        logger_args = critical_failure_hooks["logger"].critical.call_args
        assert "FilterSearchPanel" in str(logger_args), (
            "logger.criticalのメッセージにFilterSearchPanelが含まれていない"
        )

        # 検証3: QMessageBoxが作成・表示されたこと
        assert len(critical_failure_hooks["messagebox_instances"]) > 0, "QMessageBoxが作成されていない"
        messagebox = critical_failure_hooks["messagebox_instances"][0]
        messagebox.setIcon.assert_called()
        messagebox.setWindowTitle.assert_called()
        messagebox.setText.assert_called()
        messagebox.exec.assert_called()

        # 検証4: エラーメッセージに期待されるキーワードが含まれること
        text_args = messagebox.setText.call_args
        assert "filterSearchPanel" in str(text_args), "エラーメッセージにfilterSearchPanelが含まれていない"

    def test_missing_db_manager_triggers_critical_failure(self, qtbot, critical_failure_hooks, monkeypatch):
        """db_manager欠落時の致命的失敗テスト

        検証項目:
        - sys.exit(1)が呼ばれること
        - logger.criticalが呼ばれること
        - QMessageBoxが表示されること
        - エラーメッセージに"db_manager"が含まれること
        """
        # ServiceContainerのdb_managerをNoneに設定
        mock_container = Mock()
        mock_container.db_manager = None  # db_managerを意図的にNoneに（正しいプロパティ名）
        mock_container.image_repository = Mock()
        # main_window.pyでインポートされている場所でパッチ
        monkeypatch.setattr(
            "lorairo.gui.window.main_window.get_service_container", Mock(return_value=mock_container)
        )

        # MainWindowの初期化を試みる（致命的エラーが発生する）
        try:
            window = MainWindow()
            qtbot.addWidget(window)
        except SystemExit:
            pass

        # 検証1: sys.exit(1)が呼ばれたこと
        assert len(critical_failure_hooks["sys_exit"]) == 1
        assert critical_failure_hooks["sys_exit"][0] == 1

        # 検証2: logger.criticalが呼ばれたこと
        critical_failure_hooks["logger"].critical.assert_called()
        logger_args = critical_failure_hooks["logger"].critical.call_args
        assert "ServiceContainer" in str(logger_args) or "ImageDatabaseManager" in str(logger_args)

        # 検証3: QMessageBoxが作成・表示されたこと
        assert len(critical_failure_hooks["messagebox_instances"]) > 0
        messagebox = critical_failure_hooks["messagebox_instances"][0]
        messagebox.exec.assert_called()

        # 検証4: エラーメッセージに"ImageDatabaseManager"または"ServiceContainer"が含まれること
        text_args = messagebox.setText.call_args
        assert "ImageDatabaseManager" in str(text_args) or "ServiceContainer" in str(text_args)

    def test_service_creation_exception_triggers_critical_failure(
        self, qtbot, critical_failure_hooks, mock_services, monkeypatch
    ):
        """SearchFilterService作成失敗時の致命的失敗テスト

        検証項目:
        - sys.exit(1)が呼ばれること
        - logger.criticalが呼ばれること
        - QMessageBoxが表示されること
        - エラーメッセージに"SearchFilterService"が含まれること
        """

        # _create_search_filter_service()が例外を投げるようにモック
        def mock_create_service_with_exception(self):
            raise ValueError("SearchFilterService作成に失敗しました（テスト用例外）")

        monkeypatch.setattr(
            "lorairo.gui.window.main_window.MainWindow._create_search_filter_service",
            mock_create_service_with_exception,
        )

        # MainWindowの初期化を試みる（致命的エラーが発生する）
        try:
            window = MainWindow()
            qtbot.addWidget(window)
        except SystemExit:
            pass

        # 検証1: sys.exit(1)が呼ばれたこと
        assert len(critical_failure_hooks["sys_exit"]) == 1
        assert critical_failure_hooks["sys_exit"][0] == 1

        # 検証2: logger.criticalが呼ばれたこと
        critical_failure_hooks["logger"].critical.assert_called()
        logger_args = critical_failure_hooks["logger"].critical.call_args
        assert "SearchFilterService" in str(logger_args)

        # 検証3: QMessageBoxが作成・表示されたこと
        assert len(critical_failure_hooks["messagebox_instances"]) > 0
        messagebox = critical_failure_hooks["messagebox_instances"][0]
        messagebox.exec.assert_called()

        # 検証4: エラーメッセージに"SearchFilterService"が含まれること
        text_args = messagebox.setText.call_args
        assert "SearchFilterService" in str(text_args)

    # ============================================================================
    # Phase 3: 追加経路テスト
    # ============================================================================

    def test_invalid_filter_panel_interface_triggers_critical_failure(
        self, qtbot, critical_failure_hooks, monkeypatch
    ):
        """filterSearchPanelインターフェース検証失敗時の致命的失敗テスト

        検証項目:
        - sys.exit(1)が呼ばれること
        - logger.criticalが呼ばれること
        - QMessageBoxが表示されること
        - エラーメッセージに"interface validation failed"が含まれること
        """

        # setupUi()をモックして、不完全なfilterSearchPanelを作成
        def mock_setupui_with_invalid_interface(ui_self, main_window_instance):
            # 必須メソッドが欠落したfilterSearchPanelを作成
            main_window_instance.filterSearchPanel = Mock(spec=[])  # 空のspecで必須メソッドが存在しない
            main_window_instance.centralwidget = Mock()

        monkeypatch.setattr(
            "lorairo.gui.designer.MainWindow_ui.Ui_MainWindow.setupUi",
            mock_setupui_with_invalid_interface,
        )

        # MainWindowの初期化を試みる（致命的エラーが発生する）
        try:
            window = MainWindow()
            qtbot.addWidget(window)
        except SystemExit:
            pass

        # 検証1: sys.exit(1)が呼ばれたこと
        assert len(critical_failure_hooks["sys_exit"]) == 1
        assert critical_failure_hooks["sys_exit"][0] == 1

        # 検証2: logger.criticalが呼ばれたこと
        critical_failure_hooks["logger"].critical.assert_called()
        logger_args = critical_failure_hooks["logger"].critical.call_args
        assert "FilterSearchPanel" in str(logger_args)

        # 検証3: QMessageBoxが作成・表示されたこと
        assert len(critical_failure_hooks["messagebox_instances"]) > 0
        messagebox = critical_failure_hooks["messagebox_instances"][0]
        messagebox.exec.assert_called()

        # 検証4: エラーメッセージに"interface validation"が含まれること
        text_args = messagebox.setText.call_args
        assert "interface validation failed" in str(text_args) or "missing" in str(text_args)

    def test_service_injection_exception_triggers_critical_failure(
        self, qtbot, critical_failure_hooks, monkeypatch
    ):
        """SearchFilterService注入失敗時の致命的失敗テスト

        検証項目:
        - sys.exit(1)が呼ばれること
        - logger.criticalが呼ばれること
        - QMessageBoxが表示されること
        - エラーメッセージに"SearchFilterService"が含まれること
        """

        # setupUi()をモックして、set_search_filter_service()が例外を投げるようにする
        def mock_setupui_with_injection_failure(ui_self, main_window_instance):
            mock_panel = Mock()
            # set_search_filter_service()呼び出し時に例外を投げる
            mock_panel.set_search_filter_service.side_effect = RuntimeError(
                "SearchFilterService注入に失敗しました（テスト用例外）"
            )
            main_window_instance.filterSearchPanel = mock_panel
            main_window_instance.centralwidget = Mock()

        monkeypatch.setattr(
            "lorairo.gui.designer.MainWindow_ui.Ui_MainWindow.setupUi",
            mock_setupui_with_injection_failure,
        )

        # MainWindowの初期化を試みる（致命的エラーが発生する）
        try:
            window = MainWindow()
            qtbot.addWidget(window)
        except SystemExit:
            pass

        # 検証1: sys.exit(1)が呼ばれたこと
        assert len(critical_failure_hooks["sys_exit"]) == 1
        assert critical_failure_hooks["sys_exit"][0] == 1

        # 検証2: logger.criticalが呼ばれたこと
        critical_failure_hooks["logger"].critical.assert_called()
        logger_args = critical_failure_hooks["logger"].critical.call_args
        assert "SearchFilterService" in str(logger_args)

        # 検証3: QMessageBoxが作成・表示されたこと
        assert len(critical_failure_hooks["messagebox_instances"]) > 0
        messagebox = critical_failure_hooks["messagebox_instances"][0]
        messagebox.exec.assert_called()

        # 検証4: エラーメッセージに"SearchFilterService"が含まれること
        text_args = messagebox.setText.call_args
        assert "SearchFilterService" in str(text_args)
