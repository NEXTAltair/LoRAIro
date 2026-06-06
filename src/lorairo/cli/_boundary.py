"""コマンド本体を包む構造化エラー境界 (ADR 0057 §5/§6/§7)。

各コマンドに散在していた ``except ... -> console.print("[red]Error") -> typer.Exit``
を撤廃し、エラー整形を単一の :func:`command_boundary` に集約する。コマンド本体は
型付き例外を raise / 伝播するだけにし、本境界が:

1. :func:`lorairo.cli._errors.classify_exception` で安定コードへ分類し、
2. JSONL モードなら :func:`lorairo.cli._emit.emit_error`、rich モードなら stderr に
   人間向けエラーを出し (stdout の JSONL 純度を保つ)、
3. :class:`typer.Exit` を分類由来の exit code (0/2/1) で送出する。

``main:main`` の最上位境界 (ADR 0057 §7) と整合する: ``main`` 経由でも CliRunner 経由
でも同一の整形ロジックが 1 箇所で適用される (``main`` 境界は本境界をすり抜けた想定外
例外の安全網として残る)。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import typer

from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_error
from lorairo.cli._errors import classify_exception, hint_for
from lorairo.cli._output_mode import is_json_mode

# エラー/装飾は stderr へ (stdout は機械可読 JSONL 専用、ADR 0057 §1)。
_console_err = make_console(stderr=True)


@contextmanager
def command_boundary() -> Iterator[None]:
    """コマンド本体を包み、伝播した例外を構造化エラー + exit code に写す。

    ``typer.Exit`` / ``typer.Abort`` (コマンドが意図的に送出する正常な制御フロー) は
    そのまま素通しする。それ以外の例外は分類し、出力モードに応じて整形してから
    分類由来の exit code で ``typer.Exit`` を送出する。

    Yields:
        None: ``with`` ブロック内でコマンド本体を実行する。

    Raises:
        typer.Exit: 例外発生時、分類コードの exit code で送出する。
    """
    try:
        yield
    except (typer.Exit, typer.Abort):
        raise
    except Exception as exc:
        info = classify_exception(exc)
        message = str(exc) or type(exc).__name__
        if is_json_mode():
            emit_error(
                info.code,
                message,
                retryable=info.retryable,
                user_action_required=info.user_action_required,
                hint=hint_for(info.code),
            )
        else:
            _console_err.print(f"[red]Error:[/red] {message}")
        raise typer.Exit(code=info.exit_code) from exc
