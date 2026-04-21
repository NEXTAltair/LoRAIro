"""ErrorNotificationWidget 単体テスト"""

from unittest.mock import Mock

import pytest

from lorairo.gui.widgets.error_notification_widget import ErrorNotificationWidget


@pytest.fixture
def mock_db_manager():
    db = Mock()
    db.repository = Mock()
    db.repository.get_error_count_unresolved.return_value = 0
    return db


@pytest.fixture
def widget_no_db(qtbot):
    w = ErrorNotificationWidget()
    qtbot.addWidget(w)
    return w


@pytest.fixture
def widget_with_db(qtbot, mock_db_manager):
    w = ErrorNotificationWidget(db_manager=mock_db_manager)
    qtbot.addWidget(w)
    return w


class TestErrorNotificationWidgetInit:
    def test_initialization_without_db_manager(self, widget_no_db):
        assert widget_no_db.db_manager is None
        assert widget_no_db.unresolved_count == 0
        assert "-- 件" in widget_no_db.text()

    def test_initialization_with_db_manager(self, widget_with_db, mock_db_manager):
        assert widget_with_db.db_manager is mock_db_manager
        assert "0 件" in widget_with_db.text()

    def test_has_clicked_signal(self, widget_no_db):
        assert hasattr(widget_no_db, "clicked")


class TestErrorNotificationWidgetUpdateCount:
    def test_zero_errors_shows_green(self, widget_with_db, mock_db_manager):
        mock_db_manager.repository.get_error_count_unresolved.return_value = 0
        widget_with_db.update_error_count()
        assert "0 件" in widget_with_db.text()
        assert "green" in widget_with_db.styleSheet()

    def test_few_errors_shows_orange(self, widget_with_db, mock_db_manager):
        mock_db_manager.repository.get_error_count_unresolved.return_value = 5
        widget_with_db.update_error_count()
        assert "5 件" in widget_with_db.text()
        assert "orange" in widget_with_db.styleSheet()

    def test_many_errors_shows_red(self, widget_with_db, mock_db_manager):
        mock_db_manager.repository.get_error_count_unresolved.return_value = 15
        widget_with_db.update_error_count()
        assert "15 件" in widget_with_db.text()
        assert "red" in widget_with_db.styleSheet()

    def test_db_error_shows_fallback(self, widget_with_db, mock_db_manager):
        mock_db_manager.repository.get_error_count_unresolved.side_effect = Exception("DB error")
        widget_with_db.update_error_count()
        assert "取得失敗" in widget_with_db.text()

    def test_set_db_manager_triggers_update(self, qtbot, mock_db_manager):
        w = ErrorNotificationWidget()
        qtbot.addWidget(w)
        mock_db_manager.repository.get_error_count_unresolved.return_value = 3
        w.set_db_manager(mock_db_manager)
        assert "3 件" in w.text()


class TestErrorNotificationWidgetClickSignal:
    def test_click_emits_signal(self, widget_no_db, qtbot):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        with qtbot.waitSignal(widget_no_db.clicked, timeout=1000):
            qtbot.mouseClick(widget_no_db, Qt.MouseButton.LeftButton)
