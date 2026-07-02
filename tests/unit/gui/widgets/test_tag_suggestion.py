# tests/unit/gui/widgets/test_tag_suggestion.py
"""TagSuggestionWidget の単独 qtbot テスト (ADR 0036 §5)。"""

from unittest.mock import MagicMock

import pytest
import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCompleter, QLineEdit

from lorairo.gui.widgets.tag_suggestion import TagSuggestionWidget, _TagSuggestionTask


@pytest.fixture()
def widget(qtbot) -> TagSuggestionWidget:
    """TagSuggestionWidget の独立インスタンスを作る。"""
    w = TagSuggestionWidget()
    qtbot.addWidget(w)
    return w


@pytest.fixture()
def attached_widget(qtbot) -> tuple[TagSuggestionWidget, QLineEdit]:
    """QLineEdit に attach 済みの TagSuggestionWidget を作る。"""
    line_edit = QLineEdit()
    qtbot.addWidget(line_edit)
    w = TagSuggestionWidget()
    qtbot.addWidget(w)
    w.attach_line_edit(line_edit, is_enabled_provider=lambda: True)
    return w, line_edit


class TestExtractLastToken:
    """_extract_last_token (静的ヘルパー) のテスト。"""

    def test_single_token(self) -> None:
        assert TagSuggestionWidget._extract_last_token("1girl") == "1girl"

    def test_comma_separated_returns_last(self) -> None:
        assert TagSuggestionWidget._extract_last_token("1girl, blue") == "blue"

    def test_trailing_comma_returns_empty(self) -> None:
        assert TagSuggestionWidget._extract_last_token("1girl, ") == ""

    def test_empty_string(self) -> None:
        assert TagSuggestionWidget._extract_last_token("") == ""

    def test_multiple_tokens(self) -> None:
        assert TagSuggestionWidget._extract_last_token("1girl, solo, bl") == "bl"


class TestAttachLineEdit:
    """attach_line_edit のテスト。"""

    def test_attach_sets_completer(self, widget: TagSuggestionWidget, qtbot) -> None:
        line_edit = QLineEdit()
        qtbot.addWidget(line_edit)

        widget.attach_line_edit(line_edit)

        assert isinstance(line_edit.completer(), QCompleter)
        assert line_edit.completer() is widget._tag_completer

    def test_completer_case_insensitive(self, widget: TagSuggestionWidget) -> None:
        assert widget._tag_completer.caseSensitivity() == Qt.CaseSensitivity.CaseInsensitive

    def test_attach_with_enabled_provider(self, widget: TagSuggestionWidget, qtbot) -> None:
        line_edit = QLineEdit()
        qtbot.addWidget(line_edit)
        provider = MagicMock(return_value=False)

        widget.attach_line_edit(line_edit, is_enabled_provider=provider)

        assert widget._is_enabled_provider is provider


class TestTagSuggestionServiceInjection:
    """set_tag_suggestion_service のテスト。"""

    def test_initial_service_is_none(self, widget: TagSuggestionWidget) -> None:
        assert widget.tag_suggestion_service is None

    def test_set_service(self, widget: TagSuggestionWidget) -> None:
        mock_service = MagicMock()
        widget.set_tag_suggestion_service(mock_service)

        assert widget.tag_suggestion_service is mock_service

    def test_set_service_none(self, widget: TagSuggestionWidget) -> None:
        widget.set_tag_suggestion_service(None)
        assert widget.tag_suggestion_service is None


class TestOnTagCompletionActivated:
    """_on_tag_completion_activated のテスト。"""

    def test_single_token_replacement(
        self,
        attached_widget: tuple[TagSuggestionWidget, QLineEdit],
    ) -> None:
        widget, line_edit = attached_widget
        line_edit.setText("bl")

        widget._on_tag_completion_activated("blue_hair")

        assert line_edit.text() == "blue_hair, "

    def test_comma_separated_last_token_replacement(
        self,
        attached_widget: tuple[TagSuggestionWidget, QLineEdit],
    ) -> None:
        widget, line_edit = attached_widget
        line_edit.setText("1girl, bl")

        widget._on_tag_completion_activated("blue_hair")

        result = line_edit.text()
        assert result.startswith("1girl, blue_hair")

    def test_cursor_placed_at_end(
        self,
        attached_widget: tuple[TagSuggestionWidget, QLineEdit],
    ) -> None:
        widget, line_edit = attached_widget
        line_edit.setText("1girl, bl")

        widget._on_tag_completion_activated("blue_hair")

        assert line_edit.cursorPosition() == len(line_edit.text())


class TestClearTagSuggestions:
    """_clear_tag_suggestions のテスト。"""

    def test_clears_model_string_list(self, widget: TagSuggestionWidget) -> None:
        widget._tag_completer_model.setStringList(["1girl", "solo"])
        widget._clear_tag_suggestions()

        assert widget._tag_completer_model.stringList() == []

    def test_stops_timer(self, widget: TagSuggestionWidget) -> None:
        widget._tag_suggestion_timer.start(5000)
        assert widget._tag_suggestion_timer.isActive()

        widget._clear_tag_suggestions()
        assert not widget._tag_suggestion_timer.isActive()

    def test_clears_pending_token(self, widget: TagSuggestionWidget) -> None:
        widget._pending_tag_token = "blue"
        widget._clear_tag_suggestions()

        assert widget._pending_tag_token is None


class TestCacheFirstAutocomplete:
    """キャッシュ優先動作のテスト。"""

    def test_cached_suggestions_shown_without_timer(
        self,
        attached_widget: tuple[TagSuggestionWidget, QLineEdit],
    ) -> None:
        widget, _line_edit = attached_widget
        mock_service = MagicMock()
        mock_service.min_chars = 2
        mock_service.get_cached_suggestions.return_value = ["blue_hair", "blush"]
        widget.set_tag_suggestion_service(mock_service)

        widget.on_search_text_edited("bl")

        assert widget._tag_completer_model.stringList() == ["blue_hair", "blush"]
        assert not widget._tag_suggestion_timer.isActive()

    def test_timer_starts_on_cache_miss(
        self,
        attached_widget: tuple[TagSuggestionWidget, QLineEdit],
    ) -> None:
        widget, _line_edit = attached_widget
        mock_service = MagicMock()
        mock_service.min_chars = 2
        mock_service.get_cached_suggestions.return_value = None
        widget.set_tag_suggestion_service(mock_service)

        widget.on_search_text_edited("bl")

        assert widget._tag_suggestion_timer.isActive()


class _FakeAsyncSuggestionService:
    """非同期テスト用の fake service。"""

    def __init__(self, *, cached: list[str] | None = None, async_result: list[str] | None = None) -> None:
        self.min_chars = 2
        self._cached = cached
        self._async_result = async_result or []

    def get_cached_suggestions(self, _query: str) -> list[str] | None:
        return self._cached

    def get_suggestions(self, _query: str) -> list[str]:
        return self._async_result


class TestAsyncTagLookup:
    """非同期タグ候補取得のテスト。"""

    def test_background_lookup_updates_model(
        self,
        attached_widget: tuple[TagSuggestionWidget, QLineEdit],
        qtbot,
    ) -> None:
        widget, line_edit = attached_widget
        line_edit.setText("blue")
        widget.set_tag_suggestion_service(
            _FakeAsyncSuggestionService(cached=None, async_result=["blue_hair"])
        )

        widget._update_tag_completions()
        qtbot.waitUntil(
            lambda: widget._tag_completer_model.stringList() == ["blue_hair"],
            timeout=2000,
        )
        assert not widget._tag_lookup_in_flight

    def test_queues_pending_while_in_flight(
        self,
        attached_widget: tuple[TagSuggestionWidget, QLineEdit],
    ) -> None:
        widget, line_edit = attached_widget
        mock_service = MagicMock()
        mock_service.min_chars = 2
        mock_service.get_cached_suggestions.return_value = None
        widget.set_tag_suggestion_service(mock_service)
        widget._tag_lookup_in_flight = True
        line_edit.setText("blue")

        widget._update_tag_completions()

        assert widget._pending_tag_token == "blue"


class _FakeFailingSuggestionService:
    """get_suggestions が必ず例外送出する fake service (失敗系テスト用)。"""

    def __init__(self) -> None:
        self.min_chars = 2

    def get_cached_suggestions(self, _query: str) -> list[str] | None:
        return None

    def get_suggestions(self, _query: str) -> list[str]:
        raise ValueError("boom")


class TestTagSuggestionTaskSignalSafety:
    """`_TagSuggestionTask` の emit 安全性テスト (#1040 回帰防止)。

    `TagSuggestionWidget` 側の Python 参照が破棄されると `task.signals`
    (親なし QObject) の C++ 実体が GC で解放され、run() 内の emit が
    `RuntimeError: Signal source has been deleted` を送出しうる。
    `shiboken6.delete()` で signals の C++ 実体を明示的に破棄し、
    その状態を再現して run() が例外を漏らさないことを検証する。
    """

    def test_run_survives_deleted_signals_on_success(self) -> None:
        service = _FakeAsyncSuggestionService(cached=None, async_result=["blue_hair"])
        task = _TagSuggestionTask(1, "bl", service)
        shiboken6.delete(task.signals)

        # 例外が漏れなければ成功 (漏れれば pytest がテスト失敗として検出する)
        task.run()

    def test_run_survives_deleted_signals_on_failure(self) -> None:
        task = _TagSuggestionTask(1, "bl", _FakeFailingSuggestionService())
        shiboken6.delete(task.signals)

        task.run()


class TestInFlightTaskReferenceHolding:
    """`_inflight_tasks` による task 参照保持テスト (#1040 回帰防止)。"""

    def test_start_tag_lookup_registers_task_before_pool_start(
        self,
        attached_widget: tuple[TagSuggestionWidget, QLineEdit],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        widget, _line_edit = attached_widget
        widget.set_tag_suggestion_service(
            _FakeAsyncSuggestionService(cached=None, async_result=["blue_hair"])
        )
        captured: list[_TagSuggestionTask] = []
        monkeypatch.setattr(widget._tag_lookup_pool, "start", captured.append)

        widget._start_tag_lookup("bl")

        assert len(captured) == 1
        assert widget._inflight_tasks[widget._latest_tag_request_id] is captured[0]

    def test_finished_handler_discards_inflight_task(
        self,
        attached_widget: tuple[TagSuggestionWidget, QLineEdit],
        qtbot,
    ) -> None:
        widget, line_edit = attached_widget
        line_edit.setText("blue")
        widget.set_tag_suggestion_service(
            _FakeAsyncSuggestionService(cached=None, async_result=["blue_hair"])
        )

        widget._update_tag_completions()

        qtbot.waitUntil(lambda: not widget._inflight_tasks, timeout=2000)

    def test_failed_handler_discards_inflight_task(
        self,
        attached_widget: tuple[TagSuggestionWidget, QLineEdit],
        qtbot,
    ) -> None:
        widget, line_edit = attached_widget
        line_edit.setText("blue")
        widget.set_tag_suggestion_service(_FakeFailingSuggestionService())

        widget._update_tag_completions()

        qtbot.waitUntil(lambda: not widget._inflight_tasks, timeout=2000)

    def test_cleanup_clears_inflight_tasks(
        self,
        attached_widget: tuple[TagSuggestionWidget, QLineEdit],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        widget, _line_edit = attached_widget
        widget.set_tag_suggestion_service(
            _FakeAsyncSuggestionService(cached=None, async_result=["blue_hair"])
        )
        monkeypatch.setattr(widget._tag_lookup_pool, "start", lambda _task: None)
        widget._start_tag_lookup("bl")
        assert widget._inflight_tasks

        widget.cleanup()

        assert not widget._inflight_tasks


class TestEnabledProvider:
    """is_enabled_provider のテスト。"""

    def test_disabled_clears_suggestions(
        self,
        widget: TagSuggestionWidget,
        qtbot,
    ) -> None:
        line_edit = QLineEdit()
        qtbot.addWidget(line_edit)
        widget.attach_line_edit(line_edit, is_enabled_provider=lambda: False)
        widget._tag_completer_model.setStringList(["1girl", "solo"])

        widget.on_search_text_edited("bl")

        assert widget._tag_completer_model.stringList() == []


class TestCleanup:
    """cleanup のテスト。"""

    def test_cleanup_stops_timer(self, widget: TagSuggestionWidget) -> None:
        widget._tag_suggestion_timer.start(5000)
        widget._pending_tag_token = "blue"

        widget.cleanup()

        assert not widget._tag_suggestion_timer.isActive()
        assert widget._pending_tag_token is None
