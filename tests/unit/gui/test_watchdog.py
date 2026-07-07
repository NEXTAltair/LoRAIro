"""MainThreadWatchdog の停滞検知ロジック単体テスト (#1221)。

実時間に依存せず、_check へ経過値を直接渡して閾値判定だけを検証する
(固定 sleep を使わない)。
"""

from __future__ import annotations

import pytest

from lorairo.gui.watchdog import MainThreadWatchdog

pytestmark = pytest.mark.gui


@pytest.fixture
def watchdog(qtbot):
    """閾値 3000ms の watchdog (start はしない)。"""
    return MainThreadWatchdog(interval_ms=1000, threshold_ms=3000)


def test_check_warns_when_elapsed_exceeds_threshold(watchdog, monkeypatch):
    """前回 tick からの経過が閾値超過なら WARNING を出す (#1221)。"""
    messages: list[str] = []
    monkeypatch.setattr("lorairo.gui.watchdog.logger.warning", lambda msg, *a, **k: messages.append(msg))

    watchdog._check(5000)

    assert len(messages) == 1
    assert "5000" in messages[0]


def test_check_silent_within_threshold(watchdog, monkeypatch):
    """経過が閾値以内なら何も出さない (#1221)。"""
    messages: list[str] = []
    monkeypatch.setattr("lorairo.gui.watchdog.logger.warning", lambda msg, *a, **k: messages.append(msg))

    watchdog._check(1000)
    watchdog._check(3000)  # 閾値ちょうどは超過ではない

    assert messages == []


def test_on_tick_uses_elapsed_restart(watchdog, monkeypatch):
    """_on_tick は QElapsedTimer.restart の戻り値を停滞判定へ渡す (#1221)。"""
    checked: list[int] = []
    monkeypatch.setattr(watchdog._elapsed, "restart", lambda: 4200)
    monkeypatch.setattr(watchdog, "_check", checked.append)

    watchdog._on_tick()

    assert checked == [4200]
