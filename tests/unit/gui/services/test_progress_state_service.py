"""ProgressStateService ユニットテスト。

進捗は実 QStatusBar に常設された StatusProgressWidget へ出し、showMessage は
結果通知だけに使うことを検証する (ADR 0108)。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QStatusBar

from lorairo.gui.services.progress_state_service import ProgressStateService
from lorairo.gui.widgets.status_progress_widget import StatusProgressWidget


@pytest.fixture
def service_no_statusbar():
    return ProgressStateService(status_bar=None)


@pytest.fixture
def statusbar(qtbot):
    bar = QStatusBar()
    qtbot.addWidget(bar)
    bar.show()
    return bar


@pytest.fixture
def service(statusbar):
    return ProgressStateService(status_bar=statusbar)


def _widget(service: ProgressStateService) -> StatusProgressWidget:
    widget = service.progress_widget
    assert widget is not None
    return widget


class TestProgressStateServiceInit:
    def test_init_without_statusbar(self):
        svc = ProgressStateService()
        assert svc.status_bar is None
        assert svc.progress_widget is None

    def test_init_with_statusbar_adds_hidden_permanent_widget(self, statusbar):
        svc = ProgressStateService(status_bar=statusbar)
        assert svc.status_bar is statusbar
        widget = _widget(svc)
        assert widget.parent() is statusbar
        assert statusbar.findChild(StatusProgressWidget) is widget
        # 進捗が無い間は非表示
        assert widget.isHidden()

    def test_non_qstatusbar_has_no_widget_and_no_progress_message(self):
        mock_bar = MagicMock()
        svc = ProgressStateService(status_bar=mock_bar)
        svc.on_worker_batch_progress("w1", 2, 10, "file.jpg")
        assert svc.progress_widget is None
        mock_bar.showMessage.assert_not_called()


class TestBatchRegistrationStarted:
    def test_no_statusbar(self, service_no_statusbar):
        service_no_statusbar.on_batch_registration_started("worker_001")

    def test_shows_indeterminate_progress_without_message(self, service, statusbar):
        service.on_batch_registration_started("worker_001")
        widget = _widget(service)
        assert widget.isVisible()
        assert widget.text() == "データベース登録処理を開始しています..."
        assert widget.is_indeterminate()
        assert statusbar.currentMessage() == ""


class TestBatchRegistrationError:
    def test_no_statusbar(self, service_no_statusbar):
        service_no_statusbar.on_batch_registration_error("テストエラー")

    def test_error_hides_progress_and_notifies(self, service, statusbar):
        service.on_batch_registration_started("worker_001")
        service.on_batch_registration_error("テストエラー")
        assert _widget(service).isHidden()
        assert "テストエラー" in statusbar.currentMessage()

    def test_error_message_with_mock_statusbar(self):
        mock_bar = MagicMock()
        ProgressStateService(status_bar=mock_bar).on_batch_registration_error("テストエラー")
        mock_bar.showMessage.assert_called_once()
        args = mock_bar.showMessage.call_args[0]
        assert "テストエラー" in args[0]
        assert args[1] == 8000


class TestBatchRegistrationCanceled:
    @pytest.mark.parametrize(
        "method_name",
        [
            "on_batch_registration_canceled",
            "on_batch_annotation_canceled",
            "on_batch_import_canceled",
        ],
    )
    def test_no_statusbar(self, service_no_statusbar, method_name):
        getattr(service_no_statusbar, method_name)("worker_001")

    @pytest.mark.parametrize(
        "method_name",
        [
            "on_batch_registration_canceled",
            "on_batch_annotation_canceled",
            "on_batch_import_canceled",
        ],
    )
    def test_cancel_hides_progress_and_notifies(self, service, statusbar, method_name):
        service.on_worker_batch_progress("worker_001", 1, 10, "a.jpg")
        getattr(service, method_name)("worker_001")
        assert _widget(service).isHidden()
        assert "キャンセル" in statusbar.currentMessage()

    def test_cancel_message_timeout(self):
        mock_bar = MagicMock()
        ProgressStateService(status_bar=mock_bar).on_batch_import_canceled("worker_001")
        args = mock_bar.showMessage.call_args[0]
        assert "キャンセル" in args[0]
        assert args[1] == 5000


class TestWorkerProgressUpdated:
    def test_no_statusbar_returns_early(self, service_no_statusbar):
        progress = SimpleNamespace(current=5, total=10)
        service_no_statusbar.on_worker_progress_updated("w1", progress)

    def test_current_total_progress(self, service, statusbar):
        service.on_worker_progress_updated("w1", SimpleNamespace(current=3, total=10))
        widget = _widget(service)
        assert widget.text() == "処理中... 3/10 (30%)"
        assert widget.progress_bar.maximum() == 10
        assert widget.progress_bar.value() == 3
        assert statusbar.currentMessage() == ""

    def test_without_current_total_does_nothing(self, service):
        service.on_worker_progress_updated("w1", SimpleNamespace(percentage=50))
        assert _widget(service).isHidden()

    def test_worker_progress_format_with_counts(self, service, statusbar):
        """WorkerProgress 形式は件数付きで部品に表示する"""
        progress = SimpleNamespace(
            percentage=42, status_message="処理中", processed_count=4, total_count=10
        )
        service.on_worker_progress_updated("w1", progress)
        widget = _widget(service)
        assert widget.text() == "処理中 (4/10) - 42%"
        assert widget.progress_bar.value() == 4
        assert widget.progress_bar.maximum() == 10
        assert statusbar.currentMessage() == ""

    def test_worker_progress_format_without_total(self, service):
        """total_count が 0 の WorkerProgress は件数なしで percentage を表示する"""
        progress = SimpleNamespace(percentage=10, status_message="開始", processed_count=0, total_count=0)
        service.on_worker_progress_updated("w1", progress)
        widget = _widget(service)
        assert widget.text() == "開始 - 10%"
        assert widget.progress_bar.maximum() == 100
        assert widget.progress_bar.value() == 10

    def test_zero_total_is_indeterminate(self, service):
        service.on_worker_progress_updated("w1", SimpleNamespace(current=0, total=0))
        widget = _widget(service)
        assert "0%" in widget.text()
        assert widget.is_indeterminate()

    def test_late_progress_after_terminal_is_ignored(self, service):
        service.on_worker_batch_progress("w1", 1, 10, "a.jpg")
        service.on_worker_terminal("w1")
        assert _widget(service).isHidden()
        service.on_worker_progress_updated("w1", SimpleNamespace(current=2, total=10))
        service.on_worker_batch_progress("w1", 2, 10, "b.jpg")
        assert _widget(service).isHidden()


class TestWorkerBatchProgress:
    def test_no_statusbar_returns_early(self, service_no_statusbar):
        service_no_statusbar.on_worker_batch_progress("w1", 2, 10, "file.jpg")

    def test_with_statusbar(self, service, statusbar):
        service.on_worker_batch_progress("w1", 2, 10, "file.jpg")
        widget = _widget(service)
        assert "file.jpg" in widget.text()
        assert "2/10" in widget.text()
        assert widget.progress_bar.value() == 2
        assert statusbar.currentMessage() == ""

    def test_zero_total(self, service):
        service.on_worker_batch_progress("w1", 0, 0, "file.jpg")
        assert _widget(service).is_indeterminate()


class TestMultipleProgress:
    def test_latest_update_is_shown_and_previous_returns_after_finish(self, service):
        service.show_progress("a", "工程A", 1, 4)
        service.show_progress("b", "工程B")
        widget = _widget(service)
        assert widget.text() == "工程B"
        service.finish_progress("b")
        assert widget.text() == "工程A"
        assert widget.progress_bar.value() == 1
        service.finish_progress("a")
        assert widget.isHidden()

    def test_finish_unknown_key_is_noop(self, service):
        service.show_progress("a", "工程A")
        service.finish_progress("unknown")
        assert _widget(service).text() == "工程A"


class TestBatchAnnotationStarted:
    def test_no_statusbar(self, service_no_statusbar):
        service_no_statusbar.on_batch_annotation_started(50)

    def test_with_statusbar(self, service, statusbar):
        service.on_batch_annotation_started(50)
        widget = _widget(service)
        assert "50" in widget.text()
        assert widget.progress_bar.maximum() == 50
        assert statusbar.currentMessage() == ""


class TestBatchAnnotationProgress:
    def test_no_statusbar_returns_early(self, service_no_statusbar):
        service_no_statusbar.on_batch_annotation_progress(5, 10)

    def test_with_statusbar(self, service):
        service.on_batch_annotation_progress(5, 10)
        widget = _widget(service)
        assert "5/10" in widget.text()
        assert "50%" in widget.text()
        assert widget.progress_bar.value() == 5

    def test_completion_hides_progress(self, service):
        service.on_batch_annotation_started(10)
        service.on_batch_annotation_progress(10, 10)
        assert _widget(service).isHidden()

    def test_zero_total(self, service):
        service.on_batch_annotation_progress(0, 0)
        assert _widget(service).is_indeterminate()
