"""CLI 早期初期化 (Issue #254) test。

`lorairo.cli._early_init` の各 helper を Linux テスト環境で mock 検証する。
Windows 固有経路は `monkeypatch.setattr(sys, "platform", "win32")` で擬装。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# --- stdio reconfigure ---


@pytest.mark.unit
@pytest.mark.cli
def test_reconfigure_stdio_utf8_reconfigures_cp932(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: cp932 stream は UTF-8 に reconfigure される。"""
    import io
    import sys

    from lorairo.cli._early_init import _reconfigure_stdio_utf8

    mock_stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp932")
    mock_stderr = io.TextIOWrapper(io.BytesIO(), encoding="cp932")
    monkeypatch.setattr(sys, "stdout", mock_stdout)
    monkeypatch.setattr(sys, "stderr", mock_stderr)

    _reconfigure_stdio_utf8()

    assert sys.stdout.encoding.lower() == "utf-8"
    assert sys.stderr.encoding.lower() == "utf-8"


@pytest.mark.unit
@pytest.mark.cli
def test_reconfigure_stdio_utf8_no_op_for_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: 既に UTF-8 環境では reconfigure を呼ばない (no-op)。"""
    import io
    import sys

    from lorairo.cli._early_init import _reconfigure_stdio_utf8

    mock_stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", mock_stdout)

    called: list[tuple] = []
    original_reconfigure = mock_stdout.reconfigure

    def spy_reconfigure(*args, **kwargs):
        called.append((args, kwargs))
        return original_reconfigure(*args, **kwargs)

    monkeypatch.setattr(mock_stdout, "reconfigure", spy_reconfigure)

    _reconfigure_stdio_utf8()

    assert called == []  # reconfigure 未呼び出し


@pytest.mark.unit
@pytest.mark.cli
def test_reconfigure_stdio_utf8_handles_missing_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: encoding 属性が None の stream は skip して落ちない。"""
    import sys

    from lorairo.cli._early_init import _reconfigure_stdio_utf8

    mock_stdout = MagicMock(spec=["encoding", "reconfigure"])
    mock_stdout.encoding = None
    monkeypatch.setattr(sys, "stdout", mock_stdout)

    # 例外で落ちないこと
    _reconfigure_stdio_utf8()
    mock_stdout.reconfigure.assert_not_called()


@pytest.mark.unit
@pytest.mark.cli
def test_reconfigure_stdio_utf8_handles_missing_reconfigure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: reconfigure 不能な stream (pytest capture 等) も skip。"""
    import sys

    from lorairo.cli._early_init import _reconfigure_stdio_utf8

    # reconfigure attribute を持たない stream
    mock_stdout = MagicMock(spec=["encoding"])
    mock_stdout.encoding = "cp932"
    monkeypatch.setattr(sys, "stdout", mock_stdout)

    # 例外で落ちないこと (reconfigure 不在をハンドル)
    _reconfigure_stdio_utf8()


# --- Windows console code page 切替 ---


@pytest.mark.unit
@pytest.mark.cli
def test_set_windows_console_utf8_skips_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: 非 Windows 環境では何もせずに return する。"""
    import sys

    from lorairo.cli._early_init import _set_windows_console_utf8

    monkeypatch.setattr(sys, "platform", "linux")
    # 例外で落ちないこと (ctypes.windll を参照しない)
    _set_windows_console_utf8()


@pytest.mark.unit
@pytest.mark.cli
def test_set_windows_console_utf8_calls_set_console_output_cp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: cp932 console で SetConsoleOutputCP(65001) と SetConsoleCP(65001) が呼ばれる。"""
    import ctypes
    import sys

    monkeypatch.setattr(sys, "platform", "win32")

    kernel32 = MagicMock()
    kernel32.GetConsoleOutputCP.return_value = 932
    kernel32.GetConsoleCP.return_value = 932
    kernel32.SetConsoleOutputCP.return_value = 1  # 成功 (non-zero)

    windll = MagicMock()
    windll.kernel32 = kernel32
    monkeypatch.setattr(ctypes, "windll", windll, raising=False)

    registered: list = []
    monkeypatch.setattr("atexit.register", lambda f: registered.append(f))

    from lorairo.cli._early_init import _set_windows_console_utf8

    _set_windows_console_utf8()

    kernel32.SetConsoleOutputCP.assert_called_once_with(65001)
    kernel32.SetConsoleCP.assert_called_once_with(65001)
    assert len(registered) == 1  # 復元 callback が atexit に登録される


@pytest.mark.unit
@pytest.mark.cli
def test_set_windows_console_utf8_noop_when_already_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: 既に code page 65001 の console では SetConsoleOutputCP を呼ばない。"""
    import ctypes
    import sys

    monkeypatch.setattr(sys, "platform", "win32")

    kernel32 = MagicMock()
    kernel32.GetConsoleOutputCP.return_value = 65001
    kernel32.GetConsoleCP.return_value = 65001

    windll = MagicMock()
    windll.kernel32 = kernel32
    monkeypatch.setattr(ctypes, "windll", windll, raising=False)

    registered: list = []
    monkeypatch.setattr("atexit.register", lambda f: registered.append(f))

    from lorairo.cli._early_init import _set_windows_console_utf8

    _set_windows_console_utf8()

    kernel32.SetConsoleOutputCP.assert_not_called()
    kernel32.SetConsoleCP.assert_not_called()
    assert registered == []


@pytest.mark.unit
@pytest.mark.cli
def test_set_windows_console_utf8_skips_on_set_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: SetConsoleOutputCP が 0 (失敗) を返す場合は atexit 復元を登録しない。"""
    import ctypes
    import sys

    monkeypatch.setattr(sys, "platform", "win32")

    kernel32 = MagicMock()
    kernel32.GetConsoleOutputCP.return_value = 932
    kernel32.GetConsoleCP.return_value = 932
    kernel32.SetConsoleOutputCP.return_value = 0  # 失敗 (console 不在等)

    windll = MagicMock()
    windll.kernel32 = kernel32
    monkeypatch.setattr(ctypes, "windll", windll, raising=False)

    registered: list = []
    monkeypatch.setattr("atexit.register", lambda f: registered.append(f))

    from lorairo.cli._early_init import _set_windows_console_utf8

    _set_windows_console_utf8()

    kernel32.SetConsoleOutputCP.assert_called_once_with(65001)
    kernel32.SetConsoleCP.assert_not_called()  # output 失敗時は input も呼ばない
    assert registered == []  # 復元 callback も登録しない


@pytest.mark.unit
@pytest.mark.cli
def test_set_windows_console_utf8_restores_original_on_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: atexit hook が元の code page を SetConsoleOutputCP / SetConsoleCP で復元する。"""
    import ctypes
    import sys

    monkeypatch.setattr(sys, "platform", "win32")

    kernel32 = MagicMock()
    kernel32.GetConsoleOutputCP.return_value = 932
    kernel32.GetConsoleCP.return_value = 850  # 異なる initial CP
    kernel32.SetConsoleOutputCP.return_value = 1

    windll = MagicMock()
    windll.kernel32 = kernel32
    monkeypatch.setattr(ctypes, "windll", windll, raising=False)

    registered: list = []
    monkeypatch.setattr("atexit.register", lambda f: registered.append(f))

    from lorairo.cli._early_init import _set_windows_console_utf8

    _set_windows_console_utf8()

    # 切替直後: SetConsoleOutputCP(65001), SetConsoleCP(65001)
    assert kernel32.SetConsoleOutputCP.call_args_list == [((65001,),)]
    assert kernel32.SetConsoleCP.call_args_list == [((65001,),)]

    # 登録された atexit callback を実行 → 元の code page に戻る
    assert len(registered) == 1
    registered[0]()

    # SetConsoleOutputCP / SetConsoleCP の最終呼び出しが original
    kernel32.SetConsoleOutputCP.assert_called_with(932)
    kernel32.SetConsoleCP.assert_called_with(850)


# --- LiteLLM debug 抑制 ---


@pytest.mark.unit
@pytest.mark.cli
def test_suppress_litellm_debug_sets_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: LiteLLM Provider List スパムを抑制する環境変数が設定される。"""
    monkeypatch.delenv("LITELLM_LOG", raising=False)
    monkeypatch.delenv("LITELLM_SUPPRESS_DEBUG_INFO", raising=False)

    from lorairo.cli._early_init import _suppress_litellm_debug

    _suppress_litellm_debug()

    import os

    assert os.environ.get("LITELLM_LOG") == "ERROR"
    assert os.environ.get("LITELLM_SUPPRESS_DEBUG_INFO") == "true"


@pytest.mark.unit
@pytest.mark.cli
def test_suppress_litellm_debug_does_not_override_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: 既存環境変数を上書きせず尊重する (setdefault 動作)。"""
    monkeypatch.setenv("LITELLM_LOG", "DEBUG")

    from lorairo.cli._early_init import _suppress_litellm_debug

    _suppress_litellm_debug()

    import os

    assert os.environ.get("LITELLM_LOG") == "DEBUG"  # 上書きしない


# --- loguru default sink クリア ---


@pytest.mark.unit
@pytest.mark.cli
def test_clear_default_loguru_sink_calls_remove() -> None:
    """Issue #254: loguru の default sink が削除される (initialize_logging 前の漏れ出し防止)。"""
    from loguru import logger

    # 検証用に sink を 1 つ追加してから clear
    sink_id = logger.add(lambda msg: None, level=0)
    assert sink_id is not None

    from lorairo.cli._early_init import _clear_default_loguru_sink

    _clear_default_loguru_sink()

    # 削除済 sink への logger.remove は ValueError を返すため、それで確認
    with pytest.raises(ValueError):
        logger.remove(sink_id)


# --- early_init() top-level ---


@pytest.mark.unit
@pytest.mark.cli
def test_early_init_invokes_all_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: early_init() は 4 つの helper を順次呼ぶ (Linux platform で確認)。"""
    import sys

    import lorairo.cli._early_init as ei

    monkeypatch.setattr(sys, "platform", "linux")
    calls: list[str] = []
    monkeypatch.setattr(ei, "_suppress_litellm_debug", lambda: calls.append("litellm"))
    monkeypatch.setattr(ei, "_reconfigure_stdio_utf8", lambda: calls.append("stdio"))
    monkeypatch.setattr(ei, "_set_windows_console_utf8", lambda: calls.append("cp"))
    monkeypatch.setattr(ei, "_clear_default_loguru_sink", lambda: calls.append("loguru"))

    ei.early_init()

    # Linux なので set_windows_console_utf8 は呼ばれない
    assert calls == ["litellm", "stdio", "loguru"]


@pytest.mark.unit
@pytest.mark.cli
def test_early_init_invokes_windows_console_on_win32(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #254: Windows platform では _set_windows_console_utf8 も呼ばれる。"""
    import sys

    import lorairo.cli._early_init as ei

    monkeypatch.setattr(sys, "platform", "win32")
    calls: list[str] = []
    monkeypatch.setattr(ei, "_suppress_litellm_debug", lambda: calls.append("litellm"))
    monkeypatch.setattr(ei, "_reconfigure_stdio_utf8", lambda: calls.append("stdio"))
    monkeypatch.setattr(ei, "_set_windows_console_utf8", lambda: calls.append("cp"))
    monkeypatch.setattr(ei, "_clear_default_loguru_sink", lambda: calls.append("loguru"))

    ei.early_init()

    assert calls == ["litellm", "stdio", "cp", "loguru"]
