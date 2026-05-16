"""CLI 起動時の最早期初期化 (Issue #254)。

import される他モジュール (Rich Console / loguru / image-annotator-lib / LiteLLM 等) より
**前** に stdio reconfigure / Windows console code page 切替 / LiteLLM 抑制 /
loguru default sink 削除を行う。

`src/lorairo/cli/main.py` の module-level top から ``early_init()`` を呼び、
後続の ``from typer import ...`` / ``from rich.console import Console`` / commands
imports よりも先に sys.stdout/stderr の encoding を UTF-8 に固定する。
"""

from __future__ import annotations

import os
import sys


def early_init() -> None:
    """CLI 起動最早期の初期化エントリポイント。

    順序:
        1. LiteLLM 由来の Provider List スパムを抑制する環境変数を設定
        2. sys.stdout / sys.stderr を UTF-8 に reconfigure
        3. Windows console code page を 65001 (UTF-8) に切替 (atexit で復元)
        4. loguru の default sink を削除し、import 時 INFO ログの漏れ出しを防止

    依存 module のロードを最小化するため、関数本体内で遅延 import する。
    ``initialize_logging()`` 呼び出し前に lib が emit するログを抑制することで、
    PR #262 で残っていた image-annotator-lib 初期化ログ mojibake を防ぐ。
    """
    _suppress_litellm_debug()
    _reconfigure_stdio_utf8()
    if sys.platform == "win32":
        _set_windows_console_utf8()
    _clear_default_loguru_sink()


def _suppress_litellm_debug() -> None:
    """LiteLLM の Provider List スパム / debug 出力を ERROR レベルに抑制する。

    LiteLLM は import 時に provider 一覧を stderr に dump する debug 出力を持つ。
    CLI 利用ではこれが赤字 spam として邪魔になるため、import 前の env var で抑制する。
    """
    os.environ.setdefault("LITELLM_LOG", "ERROR")
    os.environ.setdefault("LITELLM_SUPPRESS_DEBUG_INFO", "true")


def _reconfigure_stdio_utf8() -> None:
    """sys.stdout / sys.stderr を UTF-8 ``TextIOWrapper`` に切替。

    Windows cp932 / 他 non-UTF-8 環境で ``UnicodeEncodeError`` を防ぐ。Linux/macOS
    の UTF-8 環境では no-op。``errors="replace"`` で encode 不能文字を ``?`` に
    置換する (起動失敗より表示劣化を優先)。
    """
    for stream in (sys.stdout, sys.stderr):
        encoding = getattr(stream, "encoding", None)
        if encoding is None or encoding.lower() == "utf-8":
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            # 想定外の stream 種別 (pytest capture 等) は skip
            continue
        reconfigure(encoding="utf-8", errors="replace")


def _set_windows_console_utf8() -> None:
    """Windows console output/input code page を UTF-8 (65001) に切替、atexit で復元。

    Caller (``early_init``) で ``sys.platform == "win32"`` チェック済の前提。
    ``SetConsoleOutputCP`` が失敗した場合は silent skip し復元 hook も登録しない。
    既に 65001 の console (Windows Terminal の utf-8 default 等) では no-op。
    """
    if sys.platform != "win32":
        return

    import atexit
    import ctypes

    kernel32 = ctypes.windll.kernel32
    utf8_cp = 65001

    original_output_cp = kernel32.GetConsoleOutputCP()
    original_input_cp = kernel32.GetConsoleCP()

    if original_output_cp == utf8_cp and original_input_cp == utf8_cp:
        return

    if not kernel32.SetConsoleOutputCP(utf8_cp):
        # console 不在 (redirect 中等) で失敗 → 何もせず復元 hook も登録しない
        return
    kernel32.SetConsoleCP(utf8_cp)

    def _restore_console_cp() -> None:
        kernel32.SetConsoleOutputCP(original_output_cp)
        kernel32.SetConsoleCP(original_input_cp)

    atexit.register(_restore_console_cp)


def _clear_default_loguru_sink() -> None:
    """loguru の default sink (stderr / INFO level) を削除する。

    image-annotator-lib 等が module import 時に ``logger.info(...)`` を呼ぶと、
    LoRAIro の ``initialize_logging()`` が呼ばれる前のため default sink を
    通って stderr に流れ、Windows cp932 console で mojibake する。
    早期に default sink を削除しておくことで、これらの import 時ログを
    破棄する。``initialize_logging()`` 内で必要な sink が再登録される。
    """
    try:
        from loguru import logger
    except ImportError:
        return
    logger.remove()
