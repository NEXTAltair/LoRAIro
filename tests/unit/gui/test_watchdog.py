"""MainThreadWatchdog の停滞検知ロジック単体テスト (#1221, #1596)。

実時間に依存せず、_check へ経過値を直接渡して閾値判定だけを検証する
(固定 sleep を使わない)。
"""

from __future__ import annotations

import pytest

from lorairo.gui.watchdog import MainThreadWatchdog

pytestmark = pytest.mark.gui


@pytest.fixture
def watchdog(qtbot):
    """既定設定 (tick 250ms / DEBUG 閾値 1000ms / WARNING 閾値 3000ms) の watchdog (start はしない)。"""
    return MainThreadWatchdog()


@pytest.fixture
def captured(monkeypatch):
    """logger.warning / logger.debug の呼び出しを記録する。"""
    calls: dict[str, list[str]] = {"warning": [], "debug": []}
    monkeypatch.setattr(
        "lorairo.gui.watchdog.logger.warning", lambda msg, *a, **k: calls["warning"].append(msg)
    )
    monkeypatch.setattr(
        "lorairo.gui.watchdog.logger.debug", lambda msg, *a, **k: calls["debug"].append(msg)
    )
    return calls


def test_default_interval_and_thresholds(watchdog):
    """既定は tick 250ms・DEBUG 閾値 1000ms・WARNING 閾値 3000ms (#1596)。"""
    assert watchdog._timer.interval() == 250
    assert watchdog._threshold_ms == 1000
    assert watchdog._warning_threshold_ms == 3000


def test_check_warns_when_elapsed_exceeds_warning_threshold(watchdog, captured):
    """前回 tick からの経過が WARNING 閾値超過なら WARNING を出す (#1221)。"""
    watchdog._check(5000)

    assert len(captured["warning"]) == 1
    assert "5000" in captured["warning"][0]
    assert captured["debug"] == []


def test_check_debug_when_elapsed_between_thresholds(watchdog, captured):
    """1〜3 秒の停滞は WARNING ではなく DEBUG で記録する (#1596)。"""
    watchdog._check(1500)
    watchdog._check(3000)  # WARNING 閾値ちょうどは WARNING 超過ではない

    assert captured["warning"] == []
    assert len(captured["debug"]) == 2
    assert "1500" in captured["debug"][0]


def test_check_silent_within_threshold(watchdog, captured):
    """経過が DEBUG 閾値以内なら何も出さない (#1221)。"""
    watchdog._check(250)
    watchdog._check(1000)  # 閾値ちょうどは超過ではない

    assert captured == {"warning": [], "debug": []}


def test_on_tick_uses_elapsed_restart(watchdog, monkeypatch):
    """_on_tick は QElapsedTimer.restart の戻り値を停滞判定へ渡す (#1221)。"""
    checked: list[int] = []
    monkeypatch.setattr(watchdog._elapsed, "restart", lambda: 4200)
    monkeypatch.setattr(watchdog, "_check", checked.append)

    watchdog._on_tick()

    assert checked == [4200]


def test_started_watchdog_ticks_on_event_loop(watchdog, monkeypatch, qtbot):
    """start 後はイベントループ上で tick し _check が呼ばれる (#1596)。"""
    checked: list[int] = []
    monkeypatch.setattr(watchdog, "_check", checked.append)

    watchdog.start()
    try:
        qtbot.waitUntil(lambda: len(checked) >= 2, timeout=3000)
    finally:
        watchdog.stop()

    assert all(elapsed >= 0 for elapsed in checked)
