# src/lorairo/gui/widgets/tag_suggestion.py
"""タグオートコンプリート Widget (ADR 0036 §6)。

`TagSuggestionWidget` は `QLineEdit` に QCompleter を取り付け、
キャッシュ優先 + 非同期取得でタグ候補を提供する。

`_TagSuggestionTask` (QRunnable) を内包し、`_tag_lookup_pool`
(QThreadPool) でバックグラウンド実行する。

ADR 0036 §3 のシグナル流通ルール: Parent (FilterSearchPanel) は
このウィジェットを composition で保持し、`tags_search_enabled()` 等の
親側状態判定をコールバックで受け取る。
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRunnable, QStringListModel, Qt, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import QCompleter, QLineEdit, QWidget

from ...utils.log import logger

if TYPE_CHECKING:
    from ...services.tag_suggestion_service import TagSuggestionService


class _TagSuggestionTaskSignals(QObject):
    """タグ候補非同期取得タスク用シグナル。"""

    finished = Signal(int, str, list)  # request_id, token, suggestions
    failed = Signal(int, str, str)  # request_id, token, error_message


class _TagSuggestionTask(QRunnable):
    """TagSuggestionService をバックグラウンドで実行するタスク。"""

    def __init__(self, request_id: int, query: str, service: "TagSuggestionService") -> None:
        super().__init__()
        self._request_id = request_id
        self._query = query
        self._service = service
        self.signals = _TagSuggestionTaskSignals()

    def run(self) -> None:
        """バックグラウンドで候補取得して UI スレッドへ通知する。"""
        try:
            suggestions = self._service.get_suggestions(self._query)
            self.signals.finished.emit(self._request_id, self._query, suggestions)
        except Exception as e:
            self.signals.failed.emit(self._request_id, self._query, str(e))


class TagSuggestionWidget(QWidget):
    """タグオートコンプリートの状態とロジックを保持する Widget。

    QLineEdit に QCompleter を取り付け、cache-first + デバウンス + 非同期で候補を提供する。
    Parent は `attach_line_edit()` で QLineEdit を渡し、`is_enabled_provider`
    で「いまタグ候補を出してよいか」の判定を委ねる。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._line_edit: QLineEdit | None = None
        self._is_enabled_provider: Callable[[], bool] = lambda: True

        # TagSuggestionService (依存注入)
        self.tag_suggestion_service: TagSuggestionService | None = None

        self._tag_completer_model = QStringListModel(self)
        self._tag_completer = QCompleter(self._tag_completer_model, self)
        self._tag_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._tag_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._tag_completer.setFilterMode(Qt.MatchFlag.MatchContains)

        self._tag_suggestion_timer = QTimer(self)
        self._tag_suggestion_timer.setSingleShot(True)
        self._tag_suggestion_timer.setInterval(300)
        self._tag_suggestion_timer.timeout.connect(self._update_tag_completions)

        self._tag_lookup_pool = QThreadPool(self)
        self._tag_lookup_pool.setMaxThreadCount(1)
        self._tag_lookup_in_flight = False
        self._tag_request_seq = 0
        self._latest_tag_request_id = 0
        self._pending_tag_token: str | None = None

        self._tag_completer.activated.connect(self._on_tag_completion_activated)

    # === Public API ===

    def attach_line_edit(
        self,
        line_edit: QLineEdit,
        is_enabled_provider: Callable[[], bool] | None = None,
    ) -> None:
        """対象 QLineEdit に completer を取り付け、有効判定コールバックを設定する。

        Args:
            line_edit: 入力ターゲットの QLineEdit。
            is_enabled_provider: 「いまタグ候補を出してよいか」を返す callable。
                未指定の場合は常時 True。
        """
        self._line_edit = line_edit
        line_edit.setCompleter(self._tag_completer)
        if is_enabled_provider is not None:
            self._is_enabled_provider = is_enabled_provider

    def set_tag_suggestion_service(self, service: "TagSuggestionService | None") -> None:
        """TagSuggestionService を設定する (依存注入)。

        Args:
            service: TagSuggestionService インスタンス。None で無効化。
        """
        self.tag_suggestion_service = service
        logger.debug("TagSuggestionService set: {}", type(service).__name__ if service else "None")

    def cleanup(self) -> None:
        """ウィジェット破棄時のクリーンアップ。"""
        self._tag_suggestion_timer.stop()
        self._pending_tag_token = None
        self._tag_lookup_pool.clear()
        self._tag_lookup_pool.waitForDone(1000)

    # === Static helpers ===

    @staticmethod
    def _extract_last_token(text: str) -> str:
        """カンマ区切り入力の最後のトークンを取得する。

        Args:
            text: 検索入力テキスト (例: "1girl, bl")。

        Returns:
            最後のトークン (例: "bl")。
        """
        return text.rsplit(",", 1)[-1].strip()

    # === Event handlers ===

    def on_search_text_edited(self, text: str) -> None:
        """検索入力編集時にタグ候補取得をデバウンス実行する。

        Args:
            text: 現在の入力テキスト。
        """
        if self._line_edit is None:
            return

        if not self._is_enabled_provider() or not self._line_edit.isEnabled():
            self._clear_tag_suggestions()
            return

        token = self._extract_last_token(text)
        if self.tag_suggestion_service is None or len(token) < self.tag_suggestion_service.min_chars:
            self._clear_tag_suggestions()
            return

        # cache-first: キャッシュヒット時はタイマーを経由せず即時表示
        cached = self.tag_suggestion_service.get_cached_suggestions(token)
        if cached is not None:
            self._show_tag_suggestions(token, cached)
            return

        self._tag_suggestion_timer.start()

    def _update_tag_completions(self) -> None:
        """デバウンスタイマー発火後にタグ候補の非同期取得を開始する。"""
        if self.tag_suggestion_service is None or self._line_edit is None:
            return

        token = self._extract_last_token(self._line_edit.text())
        if len(token) < self.tag_suggestion_service.min_chars:
            self._clear_tag_suggestions()
            return

        if self._tag_lookup_in_flight:
            self._pending_tag_token = token
            return

        self._start_tag_lookup(token)

    def _start_tag_lookup(self, token: str) -> None:
        """非同期タグ候補検索を開始する。"""
        if self.tag_suggestion_service is None:
            return

        self._tag_request_seq += 1
        request_id = self._tag_request_seq
        self._latest_tag_request_id = request_id
        self._tag_lookup_in_flight = True

        task = _TagSuggestionTask(request_id, token, self.tag_suggestion_service)
        task.signals.finished.connect(self._on_tag_lookup_finished)
        task.signals.failed.connect(self._on_tag_lookup_failed)
        self._tag_lookup_pool.start(task)

    def _on_tag_lookup_finished(self, request_id: int, token: str, suggestions: list[str]) -> None:
        """非同期タグ候補取得の完了ハンドラ。"""
        self._tag_lookup_in_flight = False

        if request_id == self._latest_tag_request_id and self._line_edit is not None:
            current_token = self._extract_last_token(self._line_edit.text())
            if current_token.casefold() == token.casefold():
                self._show_tag_suggestions(token, suggestions)

        self._dispatch_pending_lookup()

    def _on_tag_lookup_failed(self, request_id: int, token: str, error_message: str) -> None:
        """非同期タグ候補取得のエラーハンドラ。"""
        self._tag_lookup_in_flight = False
        if request_id == self._latest_tag_request_id:
            logger.warning(
                "タグ候補非同期取得に失敗: request_id={}, token='{}', error={}",
                request_id,
                token,
                error_message,
            )
            self._clear_tag_suggestions()
        self._dispatch_pending_lookup()

    def _dispatch_pending_lookup(self) -> None:
        """保留中クエリがあれば次の非同期検索を起動する。"""
        pending = self._pending_tag_token
        self._pending_tag_token = None
        if not pending or self.tag_suggestion_service is None:
            return
        if len(pending) < self.tag_suggestion_service.min_chars:
            return
        self._start_tag_lookup(pending)

    def _show_tag_suggestions(self, token: str, suggestions: list[str]) -> None:
        """候補をモデルに反映し、必要に応じてポップアップ表示する。"""
        self._tag_completer_model.setStringList(suggestions)
        if suggestions and self._line_edit is not None and self._line_edit.hasFocus():
            self._tag_completer.setCompletionPrefix(token)
            self._tag_completer.complete()

    def _clear_tag_suggestions(self) -> None:
        """タグ候補をクリアしてデバウンスタイマーを停止する。"""
        self._tag_suggestion_timer.stop()
        self._latest_tag_request_id = self._tag_request_seq
        self._pending_tag_token = None
        self._tag_completer_model.setStringList([])

    def _on_tag_completion_activated(self, selected_tag: str) -> None:
        """候補選択時にカンマ区切り入力の最後のトークンを置換する。

        Args:
            selected_tag: 選択されたタグ候補。
        """
        if self._line_edit is None:
            return

        current_text = self._line_edit.text()
        if "," in current_text:
            prefix, _ = current_text.rsplit(",", 1)
            new_text = f"{prefix.rstrip()}, {selected_tag}, "
        else:
            new_text = f"{selected_tag}, "

        self._line_edit.setText(new_text)
        self._line_edit.setCursorPosition(len(new_text))
