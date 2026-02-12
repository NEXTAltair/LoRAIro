# tests/unit/gui/conftest.py
"""
GUI テスト層の共有フィクスチャ

責務:
- QApplication 初期化・管理
- QMessageBox 自動モック
- Qt ウィジェット用テストデータ
- pytest-qt ベストプラクティス実装

このファイルは tests/conftest.py (ルート) の qapp に依存します。
"""

from unittest.mock import Mock, patch

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

# ===== Qt Configuration (inherited from root) =====
# tests/conftest.py で qapp フィクスチャと configure_qt_for_tests が
# 既に定義されています。

# ===== QMessageBox Mocking =====


@pytest.fixture(autouse=True)
def auto_mock_qmessagebox(monkeypatch):
    """
    QMessageBox を自動モック（全GUI テストで自動実行）

    使用: GUI テストで QMessageBox.question() 等が呼ばれると、
    自動的に QMessageBox.Yes を返す
    """

    def mock_question(*args, **kwargs):
        return QMessageBox.Yes

    def mock_warning(*args, **kwargs):
        return QMessageBox.Ok

    def mock_information(*args, **kwargs):
        return QMessageBox.Ok

    def mock_critical(*args, **kwargs):
        return QMessageBox.Ok

    monkeypatch.setattr(QMessageBox, "question", mock_question)
    monkeypatch.setattr(QMessageBox, "warning", mock_warning)
    monkeypatch.setattr(QMessageBox, "information", mock_information)
    monkeypatch.setattr(QMessageBox, "critical", mock_critical)


# ===== GUI Test Data Fixtures =====


@pytest.fixture
def mock_config_for_gui():
    """GUI 用 ConfigService モック"""
    mock = Mock()
    mock.get_setting.return_value = None
    mock.get_all_settings.return_value = {
        "theme": "light",
        "language": "ja",
    }
    return mock


@pytest.fixture
def mock_db_manager_for_gui():
    """GUI 用 DatabaseManager モック"""
    mock = Mock()
    mock.get_all_images.return_value = []
    mock.get_image.return_value = None
    mock.save_image.return_value = None
    return mock


@pytest.fixture
def mock_worker_service_for_gui():
    """GUI 用 WorkerService モック"""
    mock = Mock()
    mock.get_active_worker_count.return_value = 0
    mock.cancel_all_workers.return_value = True
    mock.submit_worker.return_value = None
    return mock


@pytest.fixture
def mock_dataset_state():
    """DatasetStateManager モック"""
    mock = Mock()
    mock.get_current_project.return_value = None
    mock.get_current_image.return_value = None
    mock.get_selected_images.return_value = []
    return mock


@pytest.fixture
def mock_file_system_manager_for_gui():
    """GUI 用 FileSystemManager モック"""
    mock = Mock()
    mock.get_image_files.return_value = []
    mock.get_project_directory.return_value = None
    return mock


# ===== Qt Widget Test Helpers =====


@pytest.fixture
def sample_qt_main_config():
    """MainWindow 用のモック設定"""
    return {
        "config_service": Mock(),
        "fsm": Mock(),
        "db_manager": Mock(),
        "worker_service": Mock(),
        "dataset_state": Mock(),
        "image_repo": Mock(),
    }


@pytest.fixture
def sample_qt_widget_config():
    """汎用 Qt ウィジェット用の設定"""
    return {
        "enabled": True,
        "visible": True,
        "focus_policy": "StrongFocus",
    }


# ===== Async GUI Test Helpers =====


@pytest.fixture
def qt_signal_waiter(qtbot):
    """Qt シグナル待機ヘルパー"""

    def wait_for_signal(signal, timeout=5000):
        """
        シグナルを待機

        Args:
            signal: 待機対象のシグナル
            timeout: タイムアウト（ミリ秒）

        Usage:
            wait_for_signal(widget.valueChanged)
        """
        with qtbot.waitSignal(signal, timeout=timeout):
            pass

    return wait_for_signal


@pytest.fixture
def qt_wait_condition(qtbot):
    """Qt 条件待機ヘルパー"""

    def wait_until(condition, timeout=5000):
        """
        条件を待機

        Args:
            condition: callable, 条件判定関数
            timeout: タイムアウト（ミリ秒）

        Usage:
            wait_until(lambda: widget.isEnabled(), timeout=3000)
        """
        qtbot.waitUntil(condition, timeout=timeout)

    return wait_until


# ===== pytest-qt Configuration =====


@pytest.fixture(scope="session")
def qt_api():
    """pytest-qt の API バージョン設定"""
    return "pyqt5"  # or "pyside2", "pyside6"


@pytest.fixture
def qt_messaging(qtbot):
    """Qt メッセージ処理ヘルパー"""

    class QtMessaging:
        def process_events(self):
            """イベント処理（ただし waitUntil の使用を推奨）"""
            from PySide6.QtCore import QCoreApplication

            QCoreApplication.processEvents()

        def wait_until(self, condition, timeout=5000):
            """条件待機（ベストプラクティス）"""
            qtbot.waitUntil(condition, timeout=timeout)

    return QtMessaging()


# ===== Automatic Marker Application =====


def pytest_collection_modifyitems(config, items):
    """tests/unit/gui 配下のテストに @pytest.mark.gui を自動付与"""
    for item in items:
        if "tests/unit/gui" in str(item.fspath) or "tests/integration/gui" in str(item.fspath):
            item.add_marker(pytest.mark.gui)
