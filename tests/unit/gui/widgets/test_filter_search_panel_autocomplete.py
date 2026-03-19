# tests/unit/gui/widgets/test_filter_search_panel_autocomplete.py
# FilterSearchPanel のタグオートコンプリート機能テスト。

from unittest.mock import MagicMock

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

    def test_clears_pending_token(self, panel):
        """_clear_tag_suggestions で保留中トークンがクリアされる。"""
        panel._pending_tag_token = "blue"
        panel._clear_tag_suggestions()
        assert panel._pending_tag_token is None


class TestCacheFirstAutocomplete:
    """キャッシュ優先で候補表示する動作テスト。"""

    def test_cached_suggestions_shown_without_timer(self, panel):
        """キャッシュヒット時はタイマーを経由せず即時表示する。"""
        mock_service = MagicMock()
        mock_service.min_chars = 2
        mock_service.get_cached_suggestions.return_value = ["blue_hair", "blush"]
        panel.set_tag_suggestion_service(mock_service)
        panel.ui.checkboxTags.setChecked(True)
        panel.ui.lineEditSearch.setEnabled(True)

        panel._on_search_text_edited("bl")

        assert panel._tag_completer_model.stringList() == ["blue_hair", "blush"]
        assert not panel._tag_suggestion_timer.isActive()

    def test_timer_starts_on_cache_miss(self, panel):
        """キャッシュミス時はデバウンスタイマーが起動する。"""
        mock_service = MagicMock()
        mock_service.min_chars = 2
        mock_service.get_cached_suggestions.return_value = None
        panel.set_tag_suggestion_service(mock_service)
        panel.ui.checkboxTags.setChecked(True)
        panel.ui.lineEditSearch.setEnabled(True)

        panel._on_search_text_edited("bl")

        assert panel._tag_suggestion_timer.isActive()


class _FakeAsyncSuggestionService:
    """非同期テスト用のフェイクサービス。"""

    def __init__(self, *, cached: list[str] | None = None, async_result: list[str] | None = None):
        self.min_chars = 2
        self._cached = cached
        self._async_result = async_result or []

    def get_cached_suggestions(self, _query: str) -> list[str] | None:
        return self._cached

    def get_suggestions(self, _query: str) -> list[str]:
        return self._async_result


class TestAsyncTagLookup:
    """非同期タグ候補取得の動作テスト。"""

    def test_background_lookup_updates_model(self, panel, qtbot):
        """非同期取得完了後にモデルが更新される。"""
        panel.ui.checkboxTags.setChecked(True)
        panel.ui.lineEditSearch.setText("blue")
        panel.set_tag_suggestion_service(
            _FakeAsyncSuggestionService(cached=None, async_result=["blue_hair"])
        )

        panel._update_tag_completions()
        qtbot.waitUntil(lambda: panel._tag_completer_model.stringList() == ["blue_hair"], timeout=2000)
        assert not panel._tag_lookup_in_flight

    def test_queues_pending_while_in_flight(self, panel):
        """検索中に新しいリクエストが来ると保留される。"""
        mock_service = MagicMock()
        mock_service.min_chars = 2
        mock_service.get_cached_suggestions.return_value = None
        panel.set_tag_suggestion_service(mock_service)
        panel._tag_lookup_in_flight = True
        panel.ui.lineEditSearch.setText("blue")

        panel._update_tag_completions()

        assert panel._pending_tag_token == "blue"


class TestWidgetCloseCleanup:
    """closeEvent 時のクリーンアップ動作。"""

    def test_close_event_stops_timer_and_clears_pending(self, panel):
        """close時にタイマー停止と保留トークンクリアが行われる。"""
        panel._pending_tag_token = "blue"
        panel._tag_suggestion_timer.start(5000)

        panel.close()

        assert panel._pending_tag_token is None
        assert not panel._tag_suggestion_timer.isActive()
