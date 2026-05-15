"""CLI 用 Rich ``Console`` factory (Issue #254)。

Windows 環境では Rich の罫線が UTF-8 で出力された結果を console 側 codec が
別 codec として再解釈し mojibake する事例 (例: ``â”Œâ”€``) が報告された。
``safe_box=True`` を強制することで ASCII 罫線 (``-`` / ``|`` / ``+``) に
切替え、code page 状態に依存しない安全な表示にする。

非 Windows 環境では Unicode 罫線をそのまま使用する (Linux / macOS / Codespace で
表示劣化なし)。
"""

from __future__ import annotations

import sys

from rich.console import Console


def is_windows_terminal() -> bool:
    """Windows 環境かを判定する。

    ``early_init`` で console code page を 65001 に切替済の場合でも、Rich の
    legacy renderer 経路や非 Console (pipe redirect) では mojibake の risk が
    残るため、Windows では常に safe_box を採用する保守的な方針を取る。
    """
    return sys.platform == "win32"


def make_console(*, stderr: bool = False) -> Console:
    """Platform-aware な Rich ``Console`` を生成する。

    Args:
        stderr: ``True`` の場合は ``sys.stderr`` を出力先にする ``Console`` を返す。

    Returns:
        Windows では ``safe_box=True`` を有効化した ``Console``、それ以外では
        Rich のデフォルト設定の ``Console``。
    """
    if is_windows_terminal():
        return Console(stderr=stderr, safe_box=True)
    return Console(stderr=stderr)
