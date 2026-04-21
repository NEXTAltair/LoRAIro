"""ErrorLogViewerDialog 単体テスト"""

from unittest.mock import Mock

import pytest

from lorairo.gui.widgets.error_log_viewer_dialog import ErrorLogViewerDialog


@pytest.fixture
def mock_db_manager():
    db = Mock()
    db.repository = Mock()
    db.repository.get_error_records.return_value = []
    db.repository.get_error_count_total.return_value = 0
    return db


@pytest.fixture
def dialog(qtbot, mock_db_manager):
    d = ErrorLogViewerDialog(db_manager=mock_db_manager, auto_load=False)
    qtbot.addWidget(d)
    return d


class TestErrorLogViewerDialogInit:
    def test_initialization(self, dialog, mock_db_manager):
        assert dialog.db_manager is mock_db_manager
        assert dialog.windowTitle() == "エラーログビューア"

    def test_has_error_log_widget(self, dialog):
        assert hasattr(dialog, "error_log_widget")
        assert dialog.error_log_widget is not None

    def test_has_refresh_and_close_buttons(self, dialog):
        assert hasattr(dialog, "refresh_button")
        assert hasattr(dialog, "close_button")

    def test_not_modal(self, dialog):
        assert not dialog.isModal()

    def test_not_deleted_on_close(self, dialog):
        from PySide6.QtCore import Qt

        assert not dialog.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def test_auto_load_false_does_not_load(self, mock_db_manager):
        """auto_load=False では load_error_records が呼ばれない"""
        from PySide6.QtWidgets import QApplication

        d = ErrorLogViewerDialog(db_manager=mock_db_manager, auto_load=False)
        mock_db_manager.repository.get_error_records.assert_not_called()
        d.close()

    def test_auto_load_true_loads_records(self, qtbot, mock_db_manager):
        """auto_load=True（デフォルト）では load_error_records が呼ばれる"""
        d = ErrorLogViewerDialog(db_manager=mock_db_manager, auto_load=True)
        qtbot.addWidget(d)
        mock_db_manager.repository.get_error_records.assert_called()


class TestErrorLogViewerDialogSignals:
    def test_error_selected_signal_forwarded(self, dialog):
        """error_selectedシグナルはwidgetから転送される"""
        assert dialog.error_selected is dialog.error_log_widget.error_selected

    def test_error_resolved_signal_forwarded(self, dialog):
        """error_resolvedシグナルはwidgetから転送される"""
        assert dialog.error_resolved is dialog.error_log_widget.error_resolved
