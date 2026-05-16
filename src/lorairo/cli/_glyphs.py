r"""CLI 出力用 glyph 定数 (Issue #254)。

Windows cp932 環境で UTF-8 bytes が cp932 として再解釈され mojibake する問題を
回避するため、``✓`` / ``✗`` 等の Unicode glyph を ASCII 表記に統一する。

UTF-8 console (Linux / macOS / Windows Terminal) でも視認性は劣化しない。

## Rich markup escape

各 glyph 値は ``[`` を ``\[`` で escape している。Rich ``Console.print`` および
``Table`` cell は値を markup として parse するため、``[OK]`` のような bracketed
text を素のまま渡すと未知タグとして strip / ``MarkupError`` する (PR #263 codex
review 指摘)。``\[OK]`` 形式にしておけば Rich は literal ``[OK]`` として描画する。

非 Rich context (素の ``print()`` 等) で使う場合は ``\`` が visible になるため、
本定数は Rich Console 出力専用。``rich.markup.escape("[OK]")`` と等価。
"""

from __future__ import annotations

OK = r"\[OK]"
"""操作成功 / 設定確認 OK のマーカー (旧 ``✓`` の代替)。Rich-escaped。"""

FAIL = r"\[--]"
"""操作失敗 / 設定未確認 のマーカー (旧 ``✗`` の代替)。Rich-escaped。"""

WARN = r"\[!]"
"""警告マーカー (旧 ``⚠`` の代替)。Rich-escaped。"""

INFO = r"\[i]"
"""情報マーカー (旧 ``ℹ`` の代替)。Rich-escaped。"""
