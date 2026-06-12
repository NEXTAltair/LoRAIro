# src/lorairo/gui/widgets/filter_search/count_estimate.py
"""件数見積もり Widget (ADR 0036 §6)。

フィルター変更時に SearchFilterService.get_estimated_count をデバウンス + 非同期で実行する。

Parent (FilterSearchPanel) は SearchConditions を構築するコールバックを
渡し、このウィジェットはタイマーと QThreadPool を保持する。
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from ....utils.log import logger
from ... import theme

if TYPE_CHECKING:
    from ....services.search_models import SearchConditions
    from ...services.search_filter_service import SearchFilterService


class _CountEstimateTaskSignals(QObject):
    """件数見積もりタスク用シグナル。"""

    finished = Signal(int, int)  # request_id, estimated_count
    failed = Signal(int, str)  # request_id, error_message


class _CountEstimateTask(QRunnable):
    """SearchFilterService.get_estimated_count をバックグラウンド実行するタスク。"""

    def __init__(
        self,
        request_id: int,
        conditions: "SearchConditions",
        service: "SearchFilterService",
    ) -> None:
        super().__init__()
        self._request_id = request_id
        self._conditions = conditions
        self._service = service
        self.signals = _CountEstimateTaskSignals()

    def run(self) -> None:
        """バックグラウンドで件数を取得して UI スレッドへ通知する。"""
        try:
            estimated_count = self._service.get_estimated_count(self._conditions)
            self.signals.finished.emit(self._request_id, estimated_count)
        except Exception as e:
            self.signals.failed.emit(self._request_id, str(e))


ConditionsBuilder = Callable[[], "SearchConditions | None"]


class CountEstimateWidget(QWidget):
    """件数見積もりのデバウンスと非同期実行を担う Widget。

    "該当件数: X 件" を表示する `QLabel` を内包する。
    Parent は `set_search_filter_service()` でサービスを設定し、
    `set_conditions_builder()` で SearchConditions を構築するコールバックを渡す。
    """

    # シグナル
    count_updated = Signal(int)  # estimated_count
    estimation_failed = Signal(str)  # error_message

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.search_filter_service: SearchFilterService | None = None
        self._conditions_builder: ConditionsBuilder | None = None

        # UI: ラベル 1 個
        self._estimated_count_label = QLabel("該当件数: -")
        self._estimated_count_label.setStyleSheet(f"color: {theme.INFO}; font-size: 11px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._estimated_count_label)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # デバウンスタイマー
        self._realtime_count_timer = QTimer(self)
        self._realtime_count_timer.setSingleShot(True)
        self._realtime_count_timer.setInterval(500)
        self._realtime_count_timer.timeout.connect(self._update_realtime_count)

        # 非同期実行用 QThreadPool
        self._count_estimate_pool = QThreadPool(self)
        self._count_estimate_pool.setMaxThreadCount(1)
        self._count_estimate_request_seq = 0
        self._latest_count_estimate_request_id = 0
        self._active_count_estimate_request_id = 0
        self._count_estimate_in_flight = False
        self._pending_count_estimate: tuple[int, SearchConditions] | None = None

    # === Public API ===

    @property
    def label(self) -> QLabel:
        """件数表示用 QLabel への参照を返す (parent からスタイル変更時など用)。"""
        return self._estimated_count_label

    def set_search_filter_service(self, service: "SearchFilterService | None") -> None:
        """SearchFilterService を設定する。"""
        self.search_filter_service = service

    def set_conditions_builder(self, builder: ConditionsBuilder) -> None:
        """SearchConditions を構築するコールバックを設定する。

        Args:
            builder: SearchConditions または None を返す callable。
                None を返した場合はラベルを "該当件数: -" に戻す。
        """
        self._conditions_builder = builder

    def schedule_update(self) -> None:
        """フィルター変更時の更新予約。デバウンス後に件数更新を実行する。"""
        if not self.search_filter_service:
            return
        self._pending_count_estimate = None
        self._invalidate_count_estimate_requests()
        self._realtime_count_timer.start()

    def reset(self) -> None:
        """ラベルをリセットし、保留中のリクエストを無効化する。"""
        self._realtime_count_timer.stop()
        self._estimated_count_label.setText("該当件数: -")
        self._pending_count_estimate = None
        self._invalidate_count_estimate_requests()

    def cleanup(self) -> None:
        """ウィジェット破棄時のクリーンアップ。"""
        self._realtime_count_timer.stop()
        self._pending_count_estimate = None
        self._count_estimate_pool.clear()
        self._count_estimate_pool.waitForDone(1000)

    # === Internal ===

    def _update_realtime_count(self) -> None:
        """現在のフィルター条件に対する推定件数を更新する。"""
        if not self.search_filter_service or self._conditions_builder is None:
            return

        try:
            conditions = self._conditions_builder()
            if conditions is None:
                self._estimated_count_label.setText("該当件数: -")
                self._pending_count_estimate = None
                self._invalidate_count_estimate_requests()
                return

            self._estimated_count_label.setText("該当件数: 計算中...")
            self._request_count_estimate(conditions)
        except Exception as e:
            logger.debug(f"推定件数更新に失敗: {e}")
            self._estimated_count_label.setText("該当件数: -")

    def _request_count_estimate(self, conditions: "SearchConditions") -> None:
        """件数見積もりをバックグラウンド実行する。実行中なら最新条件だけ保留する。"""
        if self.search_filter_service is None:
            return

        self._count_estimate_request_seq += 1
        request_id = self._count_estimate_request_seq
        self._latest_count_estimate_request_id = request_id

        if self._count_estimate_in_flight:
            self._pending_count_estimate = (request_id, conditions)
            return

        self._start_count_estimate_task(request_id, conditions)

    def _invalidate_count_estimate_requests(self) -> None:
        """実行中・保留中の件数見積もり結果を無効化する。"""
        self._count_estimate_request_seq += 1
        self._latest_count_estimate_request_id = self._count_estimate_request_seq

    def _start_count_estimate_task(self, request_id: int, conditions: "SearchConditions") -> None:
        """件数見積もりタスクを開始する。"""
        if self.search_filter_service is None:
            return

        self._count_estimate_in_flight = True
        self._active_count_estimate_request_id = request_id

        task = _CountEstimateTask(request_id, conditions, self.search_filter_service)
        task.signals.finished.connect(self._on_count_estimate_finished)
        task.signals.failed.connect(self._on_count_estimate_failed)
        self._count_estimate_pool.start(task)

    def _on_count_estimate_finished(self, request_id: int, estimated_count: int) -> None:
        """件数見積もり完了時、最新リクエストだけ UI に反映する。"""
        if request_id == self._latest_count_estimate_request_id:
            self._estimated_count_label.setText(f"該当件数: {estimated_count:,}件")
            self.count_updated.emit(estimated_count)

        self._finish_count_estimate_request(request_id)

    def _on_count_estimate_failed(self, request_id: int, error_message: str) -> None:
        """件数見積もり失敗時、最新リクエストだけ UI に反映する。"""
        logger.debug(f"推定件数更新に失敗: {error_message}")
        if request_id == self._latest_count_estimate_request_id:
            self._estimated_count_label.setText("該当件数: -")
            self.estimation_failed.emit(error_message)

        self._finish_count_estimate_request(request_id)

    def _finish_count_estimate_request(self, request_id: int) -> None:
        """完了した件数見積もりの後処理と保留中リクエストの起動を行う。"""
        if request_id != self._active_count_estimate_request_id:
            return

        self._count_estimate_in_flight = False
        self._active_count_estimate_request_id = 0

        if self._pending_count_estimate is None:
            return

        pending_request_id, pending_conditions = self._pending_count_estimate
        self._pending_count_estimate = None
        self._start_count_estimate_task(pending_request_id, pending_conditions)
