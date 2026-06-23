"""MainWindow初期化の致命的エラー処理の統合テスト

このテストはMainWindowの初期化時に発生する可能性のある致命的エラー経路を検証します。
特にSearchFilterService統合の失敗ケースを網羅的にテストします。

テスト戦略:
- 統合テスト: モックのみ使用（test_strategy_policy_change_2025_11_06準拠）
- 致命的失敗時の動作検証: sys.exit、logger.critical、QMessageBoxの呼び出し
- ヘッドレス環境対応: QT_QPA_PLATFORM=offscreen で実行可能
"""

from unittest.mock import Mock

import pytest

from lorairo.gui.window.main_window import MainWindow

pytestmark = [pytest.mark.integration, pytest.mark.fast_integration]


# NOTE: #869 で SearchFilterService 生成 / filterSearchPanel インターフェース検証は
# SearchTabWidget の構築 (_setup_search_filter_integration / _create_search_filter_service)
# へ移送された。MainWindow ではこれらは致命的初期化失敗 (sys.exit) ではなくなったため、
# 旧 "Phase 3.5 / Phase 3: SearchFilterService 統合経路" の致命的失敗テストは削除した。
# SearchTab 構築失敗時の振る舞いは tests/unit/gui/tab/test_search_tab.py が担う。
# 本ファイルには MainWindow の致命的サービス初期化 (ConfigurationService / WorkerService /
# ImageDatabaseManager) の経路テストのみを残す。


# ============================================================================
# Phase 2: サービス初期化経路テスト
# ============================================================================


def test_configuration_service_initialization_failure(qtbot, critical_failure_hooks, monkeypatch):
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


def test_worker_service_initialization_failure(qtbot, critical_failure_hooks, monkeypatch):
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


def test_missing_db_manager_triggers_critical_failure(qtbot, critical_failure_hooks, monkeypatch):
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
