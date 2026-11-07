# tests/unit/gui/widgets/test_tag_suggestion.py
"""TagSuggestionWidget の単独 qtbot テスト (ADR 0036 §5)。"""

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCompleter, QLineEdit, QWidget

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

        assert isinstance(widget._tag_completer, QCompleter)
        assert widget._tag_completer.widget() is line_edit
        # QLineEdit 自身の completer にはしない (入力全体の自動置換を避ける、PR #1447 P2)
        assert line_edit.completer() is None

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


class TestSingleTagMode:
    """1 タグ入力モード (`multi_tag=False`) のテスト (Issue #1439)。"""

    @pytest.fixture()
    def single_widget(self, qtbot) -> tuple[TagSuggestionWidget, QLineEdit]:
        line_edit = QLineEdit()
        qtbot.addWidget(line_edit)
        w = TagSuggestionWidget()
        qtbot.addWidget(w)
        w.attach_line_edit(line_edit, multi_tag=False, connect_text_edited=True)
        return w, line_edit

    def test_activation_replaces_whole_text_without_separator(
        self, single_widget: tuple[TagSuggestionWidget, QLineEdit]
    ) -> None:
        widget, line_edit = single_widget
        line_edit.setText("blu")

        widget._on_tag_completion_activated("blue_hair")

        assert line_edit.text() == "blue_hair"
        assert line_edit.cursorPosition() == len("blue_hair")

    def test_token_is_whole_text_even_with_comma(
        self, single_widget: tuple[TagSuggestionWidget, QLineEdit]
    ) -> None:
        widget, _line_edit = single_widget
        mock_service = MagicMock()
        mock_service.min_chars = 2
        mock_service.get_cached_suggestions.return_value = ["a, b"]
        widget.set_tag_suggestion_service(mock_service)

        widget.on_search_text_edited(" a, b ")

        mock_service.get_cached_suggestions.assert_called_once_with("a, b")

    def test_connect_text_edited_triggers_lookup_on_typing(
        self, single_widget: tuple[TagSuggestionWidget, QLineEdit], qtbot
    ) -> None:
        widget, line_edit = single_widget
        widget.set_tag_suggestion_service(_FakeAsyncSuggestionService(cached=["blue_hair"]))

        qtbot.keyClicks(line_edit, "bl")

        assert widget._tag_completer_model.stringList() == ["blue_hair"]

    def test_default_attach_keeps_multi_tag_mode(
        self, attached_widget: tuple[TagSuggestionWidget, QLineEdit]
    ) -> None:
        widget, line_edit = attached_widget
        line_edit.setText("1girl, bl")

        widget._on_tag_completion_activated("blue_hair")

        assert line_edit.text() == "1girl, blue_hair, "


def test_widget_is_hidden_so_it_does_not_overlay_parent(qtbot) -> None:
    """レイアウト外の子として持つため、親表示時に自動表示されない (Issue #1439)。"""
    parent = QWidget()
    qtbot.addWidget(parent)
    child = TagSuggestionWidget(parent)

    parent.show()

    assert child.isHidden()


# ─── 各タグ入力欄が共通部品で補完される回帰テスト (Issue #1439) ─────────────


def _tag_panel_input(qtbot) -> tuple[QWidget, QLineEdit, Callable[[object], None]]:
    from lorairo.gui.widgets.tag_panel_widget import TagPanelWidget

    w = TagPanelWidget()
    w.set_tag_edit_enabled(True)
    return w, w._tag_add_input, w.set_tag_suggestion_service


def _quick_tag_input(qtbot) -> tuple[QWidget, QLineEdit, Callable[[object], None]]:
    from lorairo.gui.widgets.quick_tag_dialog import QuickTagDialog

    service = _FakeAsyncSuggestionService(cached=["blue_hair"])
    w = QuickTagDialog([1], tag_suggestion_service=service)
    return w, w._tag_input, lambda _s: None


def _batch_tag_input(qtbot) -> tuple[QWidget, QLineEdit, Callable[[object], None]]:
    from lorairo.gui.widgets.batch_tag_add_widget import BatchTagAddWidget

    w = BatchTagAddWidget()
    return w, w.ui.lineEditTag, w.set_tag_suggestion_service


def _staging_replace_input(qtbot) -> tuple[QWidget, QLineEdit, Callable[[object], None]]:
    from lorairo.gui.widgets.staging_tag_panel import StagingTagPanel

    w = StagingTagPanel()
    return w, w._replace_to_edit, w.set_tag_suggestion_service


def _review_candidate_tags_input(qtbot) -> tuple[QWidget, QLineEdit, Callable[[object], None]]:
    from lorairo.gui.widgets.annotation_review_batch_widget import AnnotationReviewBatchWidget

    w = AnnotationReviewBatchWidget()
    # 関連タグ入力は「追加候補を探す」有効時のみ編集可能
    w.candidate_checkbox.setChecked(True)
    return w, w.candidate_tags_edit, w.set_tag_suggestion_service


@pytest.mark.parametrize(
    "factory",
    [
        _tag_panel_input,
        _quick_tag_input,
        _batch_tag_input,
        _staging_replace_input,
        _review_candidate_tags_input,
    ],
    ids=["tag_panel", "quick_tag", "batch_tag", "staging_replace", "review_candidate_tags"],
)
def test_tag_inputs_show_suggestions_when_service_injected(qtbot, factory) -> None:
    """タグ入力欄へ入力すると、注入した候補ソースの候補が completer に載る。"""
    host, line_edit, inject = factory(qtbot)
    qtbot.addWidget(host)
    inject(_FakeAsyncSuggestionService(cached=["blue_hair"]))

    completers = [c for c in host.findChildren(QCompleter) if c.widget() is line_edit]
    assert len(completers) == 1
    completer = completers[0]

    qtbot.keyClicks(line_edit, "bl")

    model = completer.model()
    assert [model.index(row, 0).data() for row in range(model.rowCount())] == ["blue_hair"]


def test_tag_input_without_service_has_no_suggestions(qtbot) -> None:
    """候補ソース未注入 (MergedTagReader 不在) では候補を出さず入力だけ受け付ける。"""
    from lorairo.gui.widgets.batch_tag_add_widget import BatchTagAddWidget

    w = BatchTagAddWidget()
    qtbot.addWidget(w)

    qtbot.keyClicks(w.ui.lineEditTag, "bl")

    assert w.ui.lineEditTag.text() == "bl"
    assert w._tag_suggestion._tag_completer_model.stringList() == []


def test_selected_image_details_injects_suggestion_service_from_reader(qtbot) -> None:
    """画像詳細の set_merged_reader が手動タグ追加入力へ候補ソースを配線する。"""
    from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget
    from lorairo.services.tag_suggestion_service import TagSuggestionService

    widget = SelectedImageDetailsWidget()
    qtbot.addWidget(widget)
    reader = MagicMock()
    reader.get_tag_languages.return_value = []

    widget.set_merged_reader(reader)

    suggestion = widget.annotation_display._tag_panel._tag_add_suggestion
    assert isinstance(suggestion.tag_suggestion_service, TagSuggestionService)

    widget.set_merged_reader(None)

    assert suggestion.tag_suggestion_service is None


class TestRealPopupActivation:
    """実際の completer ポップアップ操作で確定したときの入力内容 (Codex PR #1447 P2)。

    QLineEdit.setCompleter() は completer の activated / highlighted を自前の setText に
    接続するため、カスタムハンドラを直接呼ぶテストでは既存トークンの消失を検出できない。
    """

    @staticmethod
    def _open_popup(qtbot, widget: TagSuggestionWidget, line_edit: QLineEdit, typed: str) -> QCompleter:
        widget.set_tag_suggestion_service(_FakeAsyncSuggestionService(cached=["blue_hair", "blush"]))
        line_edit.show()
        line_edit.activateWindow()
        line_edit.setFocus()
        qtbot.waitUntil(line_edit.hasFocus, timeout=2000)
        qtbot.keyClicks(line_edit, typed)
        completer = widget._tag_completer
        qtbot.waitUntil(lambda: completer.popup().isVisible(), timeout=2000)
        return completer

    def test_multi_tag_popup_selection_preserves_previous_tags(
        self, attached_widget: tuple[TagSuggestionWidget, QLineEdit], qtbot
    ) -> None:
        widget, line_edit = attached_widget
        line_edit.textEdited.connect(widget.on_search_text_edited)
        completer = self._open_popup(qtbot, widget, line_edit, "1girl, bl")
        popup = completer.popup()

        # 候補をキー操作でハイライト (QLineEdit が highlighted で本文を書き換える) してから確定する
        qtbot.keyClick(popup, Qt.Key.Key_Down)
        qtbot.keyClick(popup, Qt.Key.Key_Return)

        qtbot.waitUntil(lambda: line_edit.text() == "1girl, blue_hair, ", timeout=2000)

    def test_single_tag_popup_selection_sets_candidate(self, qtbot) -> None:
        line_edit = QLineEdit()
        qtbot.addWidget(line_edit)
        widget = TagSuggestionWidget()
        qtbot.addWidget(widget)
        widget.attach_line_edit(line_edit, multi_tag=False, connect_text_edited=True)
        completer = self._open_popup(qtbot, widget, line_edit, "bl")
        popup = completer.popup()

        qtbot.keyClick(popup, Qt.Key.Key_Down)
        qtbot.keyClick(popup, Qt.Key.Key_Return)

        qtbot.waitUntil(lambda: line_edit.text() == "blue_hair", timeout=2000)
