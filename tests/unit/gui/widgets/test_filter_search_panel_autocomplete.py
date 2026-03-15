# tests/unit/gui/widgets/test_filter_search_panel_autocomplete.py
# FilterSearchPanel のタグオートコンプリート機能テスト。

import pytest
from PySide6.QtWidgets import QCompleter

from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel


@pytest.fixture()
def panel(qtbot):
    """FilterSearchPanel インスタンスを作成して qtbot に登録する。"""
    widget = FilterSearchPanel()
    qtbot.addWidget(widget)
    return widget


class TestExtractLastToken:
    """_extract_last_token の動作テスト。"""

    def test_single_token(self, panel):
        assert panel._extract_last_token("1girl") == "1girl"

    def test_comma_separated_returns_last(self, panel):
        assert panel._extract_last_token("1girl, blue") == "blue"

    def test_trailing_comma_returns_empty(self, panel):
        assert panel._extract_last_token("1girl, ") == ""

    def test_empty_string(self, panel):
        assert panel._extract_last_token("") == ""

    def test_multiple_tokens(self, panel):
        assert panel._extract_last_token("1girl, solo, bl") == "bl"


class TestTagCompletionActivated:
    """_on_tag_completion_activated の動作テスト。"""

    def test_single_token_replacement(self, panel):
        """単一トークンの置換。"""
        panel.ui.lineEditSearch.setText("bl")
        panel._on_tag_completion_activated("blue_hair")

        assert panel.ui.lineEditSearch.text() == "blue_hair, "

    def test_comma_separated_last_token_replacement(self, panel):
        """カンマ区切りの最後のトークンのみ置換される。"""
        panel.ui.lineEditSearch.setText("1girl, bl")
        panel._on_tag_completion_activated("blue_hair")

        result = panel.ui.lineEditSearch.text()
        assert result.startswith("1girl, blue_hair")
        assert "bl" not in result.split(",")[-1] or "blue" in result

    def test_cursor_placed_at_end(self, panel):
        """カーソルがテキスト末尾に配置される。"""
        panel.ui.lineEditSearch.setText("1girl, bl")
        panel._on_tag_completion_activated("blue_hair")

        text = panel.ui.lineEditSearch.text()
        assert panel.ui.lineEditSearch.cursorPosition() == len(text)


class TestTagSuggestionServiceInjection:
    """TagSuggestionService の依存注入テスト。"""

    def test_initial_service_is_none(self, panel):
        """初期状態で tag_suggestion_service は None。"""
        assert panel.tag_suggestion_service is None

    def test_set_tag_suggestion_service(self, panel):
        """set_tag_suggestion_service でサービスが設定される。"""
        from unittest.mock import MagicMock

        mock_service = MagicMock()
        panel.set_tag_suggestion_service(mock_service)

        assert panel.tag_suggestion_service is mock_service

    def test_set_tag_suggestion_service_none(self, panel):
        """None を設定しても問題ない。"""
        panel.set_tag_suggestion_service(None)
        assert panel.tag_suggestion_service is None


class TestCompleterSetup:
    """QCompleter の設定テスト。"""

    def test_completer_attached_to_line_edit(self, panel):
        """lineEditSearch に QCompleter が設定されている。"""
        completer = panel.ui.lineEditSearch.completer()
        assert completer is not None
        assert isinstance(completer, QCompleter)

    def test_completer_is_case_insensitive(self, panel):
        """QCompleter が大文字小文字を区別しない。"""
        from PySide6.QtCore import Qt

        completer = panel.ui.lineEditSearch.completer()
        assert completer.caseSensitivity() == Qt.CaseSensitivity.CaseInsensitive


class TestClearTagSuggestions:
    """_clear_tag_suggestions の動作テスト。"""

    def test_clears_model_string_list(self, panel):
        """_clear_tag_suggestions 呼び出しでモデルのリストが空になる。"""
        panel._tag_completer_model.setStringList(["1girl", "solo"])
        panel._clear_tag_suggestions()

        assert panel._tag_completer_model.stringList() == []

    def test_stops_timer(self, panel):
        """_clear_tag_suggestions でデバウンスタイマーが停止する。"""
        panel._tag_suggestion_timer.start(5000)
        assert panel._tag_suggestion_timer.isActive()

        panel._clear_tag_suggestions()
        assert not panel._tag_suggestion_timer.isActive()
