# tests/unit/gui/widgets/filter_search/test_count_estimate.py
"""CountEstimateWidget の単独 qtbot テスト (ADR 0036 §5)。"""

from unittest.mock import MagicMock

import pytest

from lorairo.gui.widgets.filter_search.count_estimate import CountEstimateWidget


@pytest.fixture()
def widget(qtbot) -> CountEstimateWidget:
    """CountEstimateWidget の独立インスタンスを作る。"""
    w = CountEstimateWidget()
    qtbot.addWidget(w)
    return w


class TestInitialState:
    """初期状態のテスト。"""

    def test_initial_label(self, widget: CountEstimateWidget) -> None:
        assert widget.label.text() == "該当件数: -"

    def test_service_is_none(self, widget: CountEstimateWidget) -> None:
        assert widget.search_filter_service is None


class TestSetters:
    """setter のテスト。"""

    def test_set_search_filter_service(self, widget: CountEstimateWidget) -> None:
        service = MagicMock()
        widget.set_search_filter_service(service)
        assert widget.search_filter_service is service

    def test_set_conditions_builder(self, widget: CountEstimateWidget) -> None:
        builder = MagicMock(return_value=None)
        widget.set_conditions_builder(builder)
        assert widget._conditions_builder is builder


class TestScheduleUpdate:
    """schedule_update のテスト。"""

    def test_schedule_starts_timer_when_service_set(
        self,
        widget: CountEstimateWidget,
    ) -> None:
        widget.set_search_filter_service(MagicMock())
        widget.schedule_update()

        assert widget._realtime_count_timer.isActive()

    def test_schedule_noop_when_service_missing(
        self,
        widget: CountEstimateWidget,
    ) -> None:
        widget.schedule_update()

        assert not widget._realtime_count_timer.isActive()

    def test_schedule_invalidates_requests(self, widget: CountEstimateWidget) -> None:
        widget.set_search_filter_service(MagicMock())
        widget._latest_count_estimate_request_id = 5
        widget._count_estimate_request_seq = 5

        widget.schedule_update()

        # _invalidate_count_estimate_requests により seq が更新される
        assert widget._count_estimate_request_seq > 5


class TestReset:
    """reset のテスト。"""

    def test_reset_label(self, widget: CountEstimateWidget) -> None:
        widget._estimated_count_label.setText("該当件数: 100件")
        widget.reset()
        assert widget.label.text() == "該当件数: -"

    def test_reset_stops_timer(self, widget: CountEstimateWidget) -> None:
        widget._realtime_count_timer.start(5000)
        widget.reset()
        assert not widget._realtime_count_timer.isActive()


class TestUpdateRealtimeCount:
    """_update_realtime_count のテスト。"""

    def test_builder_returns_none_resets_label(
        self,
        widget: CountEstimateWidget,
    ) -> None:
        widget.set_search_filter_service(MagicMock())
        widget.set_conditions_builder(lambda: None)
        widget._estimated_count_label.setText("該当件数: 100件")

        widget._update_realtime_count()

        assert widget.label.text() == "該当件数: -"

    def test_builder_returns_conditions_starts_calculation(
        self,
        widget: CountEstimateWidget,
    ) -> None:
        service = MagicMock()
        service.get_estimated_count = MagicMock(return_value=42)
        widget.set_search_filter_service(service)
        conditions = MagicMock()
        widget.set_conditions_builder(lambda: conditions)

        widget._update_realtime_count()

        # 計算開始時のラベル
        assert widget.label.text() in ("該当件数: 計算中...", "該当件数: 42件")
        assert widget._count_estimate_in_flight or (widget._latest_count_estimate_request_id > 0)

    def test_noop_when_service_missing(self, widget: CountEstimateWidget) -> None:
        widget.set_conditions_builder(lambda: MagicMock())

        widget._update_realtime_count()

        # service 未設定なので何も起こらない
        assert widget.label.text() == "該当件数: -"

    def test_builder_exception_resets_label(self, widget: CountEstimateWidget) -> None:
        widget.set_search_filter_service(MagicMock())

        def raising_builder():
            raise ValueError("test error")

        widget.set_conditions_builder(raising_builder)
        widget._update_realtime_count()

        assert widget.label.text() == "該当件数: -"


class _FakeService:
    """非同期テスト用 fake service。"""

    def __init__(self, *, count: int = 42, should_fail: bool = False) -> None:
        self._count = count
        self._should_fail = should_fail
        self.call_count = 0

    def get_estimated_count(self, _conditions) -> int:
        self.call_count += 1
        if self._should_fail:
            raise RuntimeError("simulated failure")
        return self._count


class TestAsyncCountEstimate:
    """非同期件数見積もりのテスト。"""

    def test_count_emit_and_label_update(
        self,
        widget: CountEstimateWidget,
        qtbot,
    ) -> None:
        service = _FakeService(count=123)
        widget.set_search_filter_service(service)
        conditions = MagicMock()
        widget.set_conditions_builder(lambda: conditions)

        with qtbot.waitSignal(widget.count_updated, timeout=2000) as blocker:
            widget._update_realtime_count()

        assert blocker.args == [123]
        assert widget.label.text() == "該当件数: 123件"

    def test_failed_emits_error_signal(
        self,
        widget: CountEstimateWidget,
        qtbot,
    ) -> None:
        service = _FakeService(should_fail=True)
        widget.set_search_filter_service(service)
        conditions = MagicMock()
        widget.set_conditions_builder(lambda: conditions)

        with qtbot.waitSignal(widget.estimation_failed, timeout=2000):
            widget._update_realtime_count()

        assert widget.label.text() == "該当件数: -"

    def test_pending_request_queued_while_in_flight(
        self,
        widget: CountEstimateWidget,
    ) -> None:
        widget.set_search_filter_service(MagicMock())
        widget._count_estimate_in_flight = True
        conditions = MagicMock()

        widget._request_count_estimate(conditions)

        assert widget._pending_count_estimate is not None
        assert widget._pending_count_estimate[1] is conditions


class TestCleanup:
    """cleanup のテスト。"""

    def test_cleanup_stops_timer(self, widget: CountEstimateWidget) -> None:
        widget._realtime_count_timer.start(5000)
        widget._pending_count_estimate = (1, MagicMock())

        widget.cleanup()

        assert not widget._realtime_count_timer.isActive()
        assert widget._pending_count_estimate is None
