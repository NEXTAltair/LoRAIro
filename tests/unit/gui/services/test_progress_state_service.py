"""ProgressStateService ユニットテスト。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from lorairo.gui.services.progress_state_service import ProgressStateService


@pytest.fixture
def service_no_statusbar():
    return ProgressStateService(status_bar=None)


@pytest.fixture
def mock_statusbar():
    return MagicMock()


@pytest.fixture
def service_with_statusbar(mock_statusbar):
    return ProgressStateService(status_bar=mock_statusbar)


class TestProgressStateServiceInit:
    def test_init_without_statusbar(self):
        svc = ProgressStateService()
        assert svc.status_bar is None

    def test_init_with_statusbar(self, mock_statusbar):
        svc = ProgressStateService(status_bar=mock_statusbar)
        assert svc.status_bar is mock_statusbar


class TestBatchRegistrationStarted:
    def test_no_statusbar(self, service_no_statusbar):
        service_no_statusbar.on_batch_registration_started("worker_001")

    def test_with_statusbar(self, service_with_statusbar, mock_statusbar):
        service_with_statusbar.on_batch_registration_started("worker_001")
        mock_statusbar.showMessage.assert_called_once()


class TestBatchRegistrationError:
    def test_no_statusbar(self, service_no_statusbar):
        service_no_statusbar.on_batch_registration_error("テストエラー")

    def test_with_statusbar(self, service_with_statusbar, mock_statusbar):
        service_with_statusbar.on_batch_registration_error("テストエラー")
        mock_statusbar.showMessage.assert_called_once()
        args = mock_statusbar.showMessage.call_args[0]
        assert "テストエラー" in args[0]


class TestWorkerProgressUpdated:
    def test_no_statusbar_returns_early(self, service_no_statusbar):
        progress = SimpleNamespace(current=5, total=10)
        service_no_statusbar.on_worker_progress_updated("w1", progress)

    def test_with_statusbar_and_progress(self, service_with_statusbar, mock_statusbar):
        progress = SimpleNamespace(current=3, total=10)
        service_with_statusbar.on_worker_progress_updated("w1", progress)
        mock_statusbar.showMessage.assert_called_once()

    def test_with_statusbar_no_current_total(self, service_with_statusbar, mock_statusbar):
        progress = SimpleNamespace(percentage=50)
        service_with_statusbar.on_worker_progress_updated("w1", progress)
        # current/total 属性がない場合はデバッグログのみ

    def test_with_statusbar_zero_total(self, service_with_statusbar, mock_statusbar):
        progress = SimpleNamespace(current=0, total=0)
        service_with_statusbar.on_worker_progress_updated("w1", progress)
        mock_statusbar.showMessage.assert_called_once()
        msg = mock_statusbar.showMessage.call_args[0][0]
        assert "0%" in msg


class TestWorkerBatchProgress:
    def test_no_statusbar_returns_early(self, service_no_statusbar):
        service_no_statusbar.on_worker_batch_progress("w1", 2, 10, "file.jpg")

    def test_with_statusbar(self, service_with_statusbar, mock_statusbar):
        service_with_statusbar.on_worker_batch_progress("w1", 2, 10, "file.jpg")
        mock_statusbar.showMessage.assert_called_once()
        msg = mock_statusbar.showMessage.call_args[0][0]
        assert "file.jpg" in msg
        assert "2/10" in msg

    def test_zero_total(self, service_with_statusbar, mock_statusbar):
        service_with_statusbar.on_worker_batch_progress("w1", 0, 0, "file.jpg")
        mock_statusbar.showMessage.assert_called_once()


class TestBatchAnnotationStarted:
    def test_no_statusbar(self, service_no_statusbar):
        service_no_statusbar.on_batch_annotation_started(50)

    def test_with_statusbar(self, service_with_statusbar, mock_statusbar):
        service_with_statusbar.on_batch_annotation_started(50)
        mock_statusbar.showMessage.assert_called_once()
        msg = mock_statusbar.showMessage.call_args[0][0]
        assert "50" in msg


class TestBatchAnnotationProgress:
    def test_no_statusbar_returns_early(self, service_no_statusbar):
        service_no_statusbar.on_batch_annotation_progress(5, 10)

    def test_with_statusbar(self, service_with_statusbar, mock_statusbar):
        service_with_statusbar.on_batch_annotation_progress(5, 10)
        mock_statusbar.showMessage.assert_called_once()
        msg = mock_statusbar.showMessage.call_args[0][0]
        assert "5/10" in msg
        assert "50%" in msg

    def test_zero_total(self, service_with_statusbar, mock_statusbar):
        service_with_statusbar.on_batch_annotation_progress(0, 0)
        mock_statusbar.showMessage.assert_called_once()
