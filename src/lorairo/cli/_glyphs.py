"""CLI 出力用 glyph 定数 (Issue #254)。

Windows cp932 環境で UTF-8 bytes が cp932 として再解釈され mojibake する問題を
回避するため、``✓`` / ``✗`` 等の Unicode glyph を ASCII 表記に統一する。

UTF-8 console (Linux / macOS / Windows Terminal) でも視認性は劣化しない。
"""

from __future__ import annotations

OK = "[OK]"
"""操作成功 / 設定確認 OK のマーカー (旧 ``✓`` の代替)。"""

FAIL = "[--]"
"""操作失敗 / 設定未確認 のマーカー (旧 ``✗`` の代替)。"""

WARN = "[!]"
"""警告マーカー (旧 ``⚠`` の代替)。"""

INFO = "[i]"
"""情報マーカー (旧 ``ℹ`` の代替)。"""
