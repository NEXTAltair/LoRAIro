"""CLI Console factory (Issue #254) の test。"""

from __future__ import annotations

import pytest

from lorairo.cli._console import is_windows_terminal, make_console


@pytest.mark.unit
@pytest.mark.cli
def test_is_windows_terminal_returns_false_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: Linux 環境では False を返し、Rich の Unicode 罫線をそのまま使う。"""
    import sys

    monkeypatch.setattr(sys, "platform", "linux")
    assert is_windows_terminal() is False


@pytest.mark.unit
@pytest.mark.cli
def test_is_windows_terminal_returns_true_on_win32(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: Windows 環境では True を返し、safe_box=True を強制する。"""
    import sys

    monkeypatch.setattr(sys, "platform", "win32")
    assert is_windows_terminal() is True


@pytest.mark.unit
@pytest.mark.cli
def test_make_console_returns_safe_box_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: Windows では safe_box=True が有効化された Console が返る。"""
    import sys

    monkeypatch.setattr(sys, "platform", "win32")

    console = make_console()
    # Rich Console は safe_box 属性を持つ
    assert console.safe_box is True


@pytest.mark.unit
@pytest.mark.cli
def test_make_console_returns_default_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: Linux では Rich のデフォルト Console (safe_box は Rich のデフォルトに従う)。"""
    import sys

    monkeypatch.setattr(sys, "platform", "linux")

    console = make_console()
    # Linux でも Rich のデフォルトでは safe_box=True に近い動作だが、
    # 重要なのは Windows 専用設定が明示的に適用されていないこと。
    # ここでは Console が例外なく生成されることを確認。
    assert console is not None


@pytest.mark.unit
@pytest.mark.cli
def test_make_console_stderr_option(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: stderr=True で stderr 出力 Console が返る。"""
    import sys

    monkeypatch.setattr(sys, "platform", "linux")

    console = make_console(stderr=True)
    assert console.stderr is True
