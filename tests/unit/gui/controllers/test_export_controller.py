"""ExportController 単体テスト"""

from unittest.mock import Mock, patch

import pytest

from lorairo.gui.controllers.export_controller import ExportController


@pytest.fixture
def mock_selection_state_service():
    service = Mock()
    service.get_current_selected_images.return_value = [1, 2, 3]
    return service


@pytest.fixture
def mock_service_container():
    container = Mock()
    container.dataset_export_service = Mock()
    return container


@pytest.fixture
def mock_parent():
    return Mock()


@pytest.fixture
def controller(mock_selection_state_service, mock_service_container, mock_parent):
    return ExportController(
        selection_state_service=mock_selection_state_service,
        service_container=mock_service_container,
        parent=mock_parent,
    )


@pytest.fixture
def controller_no_service(mock_service_container, mock_parent):
    return ExportController(
        selection_state_service=None,
        service_container=mock_service_container,
        parent=mock_parent,
    )


class TestExportControllerInit:
    def test_initialization(self, controller, mock_selection_state_service):
        assert controller.selection_state_service is mock_selection_state_service

    def test_initialization_without_selection_service(self, controller_no_service):
        assert controller_no_service.selection_state_service is None


class TestExportControllerValidateServices:
    def test_validate_services_with_valid_service(self, controller):
        assert controller._validate_services() is True

    def test_validate_services_without_service_returns_false(self, controller_no_service):
        assert controller_no_service._validate_services() is False

    def test_validate_services_shows_warning_when_missing(self, controller_no_service, monkeypatch):
        from unittest.mock import Mock

        from PySide6.QtWidgets import QMessageBox

        mock_warning = Mock(return_value=QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "warning", mock_warning)
        controller_no_service._validate_services()
        mock_warning.assert_called_once()


class TestExportControllerGetCurrentSelectedImages:
    def test_returns_image_ids(self, controller, mock_selection_state_service):
        mock_selection_state_service.get_current_selected_images.return_value = [1, 2, 3]
        result = controller._get_current_selected_images()
        assert result == [1, 2, 3]

    def test_returns_empty_when_no_service(self, controller_no_service):
        result = controller_no_service._get_current_selected_images()
        assert result == []


class TestExportControllerOpenExportDialog:
    def test_open_dialog_shows_warning_when_no_images(
        self, controller, mock_selection_state_service, mock_parent
    ):
        mock_selection_state_service.get_current_selected_images.return_value = []
        controller.open_export_dialog()
        # QMessageBox.warning は autouse の auto_mock_qmessagebox でモック済み

    def test_open_dialog_creates_export_widget_when_images_present(
        self, controller, mock_service_container
    ):
        with patch("lorairo.gui.widgets.dataset_export_widget.DatasetExportWidget") as mock_widget_class:
            mock_widget = Mock()
            mock_widget_class.return_value = mock_widget
            mock_widget.exec.return_value = None
            mock_widget.export_completed = Mock()
            mock_widget.export_completed.connect = Mock()

            controller.open_export_dialog()

            mock_widget_class.assert_called_once()
            mock_widget.exec.assert_called_once()

    def test_on_export_completed_logs_path(self, controller):
        """export完了ハンドラが例外なく実行される"""
        controller._on_export_completed("/some/path")


class TestExportControllerStagingProvider:
    """staged_ids_provider 注入時の対象解決（ADR 0055・PR #620 案A）。"""

    def test_provider_resolves_staged_ids_as_target(
        self, mock_selection_state_service, mock_service_container, mock_parent
    ):
        """provider 注入時はステージング集合を対象にする。"""
        controller = ExportController(
            selection_state_service=mock_selection_state_service,
            service_container=mock_service_container,
            parent=mock_parent,
            staged_ids_provider=lambda: [10, 20, 30],
        )
        assert controller._get_current_selected_images() == [10, 20, 30]

    def test_provider_takes_precedence_over_selection(
        self, mock_selection_state_service, mock_service_container, mock_parent
    ):
        """provider 注入時はサムネ選択ではなくステージング集合を読む。"""
        mock_selection_state_service.get_current_selected_images.return_value = [1, 2, 3]
        controller = ExportController(
            selection_state_service=mock_selection_state_service,
            service_container=mock_service_container,
            parent=mock_parent,
            staged_ids_provider=lambda: [99],
        )
        result = controller._get_current_selected_images()
        assert result == [99]
        # 選択ベースの解決は呼ばれない
        mock_selection_state_service.get_current_selected_images.assert_not_called()

    def test_provider_returns_empty_when_staging_empty(self, mock_service_container, mock_parent):
        """ステージングが空なら空リストを返す（None 安全）。"""
        controller = ExportController(
            selection_state_service=None,
            service_container=mock_service_container,
            parent=mock_parent,
            staged_ids_provider=lambda: [],
        )
        assert controller._get_current_selected_images() == []

    def test_open_dialog_shows_staging_warning_when_empty(
        self, mock_service_container, mock_parent, monkeypatch
    ):
        """ステージング空時はステージング誘導の警告を出しダイアログを開かない。"""
        from PySide6.QtWidgets import QMessageBox

        mock_warning = Mock(return_value=QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "warning", mock_warning)

        controller = ExportController(
            selection_state_service=None,
            service_container=mock_service_container,
            parent=mock_parent,
            staged_ids_provider=lambda: [],
        )
        controller.open_export_dialog()

        mock_warning.assert_called_once()
        message = mock_warning.call_args[0][2]
        assert "ステージング" in message

    def test_open_dialog_creates_widget_with_staged_ids(self, mock_service_container, mock_parent):
        """ステージングに画像があればその ID でエクスポートダイアログを開く。"""
        controller = ExportController(
            selection_state_service=None,
            service_container=mock_service_container,
            parent=mock_parent,
            staged_ids_provider=lambda: [5, 6],
        )
        with patch("lorairo.gui.widgets.dataset_export_widget.DatasetExportWidget") as mock_widget_class:
            mock_widget = Mock()
            mock_widget_class.return_value = mock_widget
            mock_widget.exec.return_value = None
            mock_widget.export_completed = Mock()

            controller.open_export_dialog()

            mock_widget_class.assert_called_once()
            assert mock_widget_class.call_args.kwargs["initial_image_ids"] == [5, 6]
            mock_widget.exec.assert_called_once()

    def test_no_provider_falls_back_to_selection(
        self, mock_selection_state_service, mock_service_container, mock_parent
    ):
        """provider 未注入時は従来の選択ベース解決にフォールバックする（後方互換）。"""
        mock_selection_state_service.get_current_selected_images.return_value = [7, 8]
        controller = ExportController(
            selection_state_service=mock_selection_state_service,
            service_container=mock_service_container,
            parent=mock_parent,
        )
        assert controller._get_current_selected_images() == [7, 8]
        mock_selection_state_service.get_current_selected_images.assert_called_once()
