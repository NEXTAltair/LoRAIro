"""CLI 出力モード解決 (ADR 0058 §1)。

出力モードは tri-state ``--json`` / ``--no-json`` グローバルフラグ + env
``LORAIRO_CLI_JSON`` で決まる。解決順序は **明示フラグ > env > 既定 rich**:
``--json`` / ``--no-json`` が指定されればそれが勝ち、未指定のときだけ env を見る。
env が JSONL を有効化していても ``--no-json`` で rich に上書きできる。

モードは中央エラー境界が raw ``sys.argv`` / env から **Click のパース前に** 解決する。
Click は callback より前に context を構築・パースするため、``--json`` を callback
option としてだけ扱うと parse 時 usage error がモード確定前に境界へ到達し JSONL で
返せない。よって argv を先読み (prescan) してモードを確定する。
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence

_ENV_VAR = "LORAIRO_CLI_JSON"
_JSON_FLAG = "--json"
_NO_JSON_FLAG = "--no-json"
_FALSEY_ENV = frozenset({"", "0", "false", "no", "off"})

# 中央境界が解決したモードを保持する (コマンド本体が参照する)。
_json_mode: bool = False
_prescanned_mode: bool = False


def _scan_explicit_flag(argv: Sequence[str]) -> bool | None:
    """argv を先読みして明示フラグを解決する (位置非依存、後勝ち)。

    ``--json`` / ``--no-json`` はグローバル位置でもサブコマンド後でも受理する。
    両方が現れた場合は後に現れた方を採用する。

    Args:
        argv: プログラム名を除いた引数列 (``sys.argv[1:]`` 相当)。

    Returns:
        ``--json`` なら ``True``、``--no-json`` なら ``False``、どちらも無ければ ``None``。
    """
    explicit: bool | None = None
    for token in argv:
        if token == _JSON_FLAG:
            explicit = True
        elif token == _NO_JSON_FLAG:
            explicit = False
        elif token == "--":
            # ``--`` 以降は位置引数。フラグ走査を止める。
            break
    return explicit


def _env_enables_json(env: Mapping[str, str]) -> bool:
    """env ``LORAIRO_CLI_JSON`` が JSONL を有効化しているか。"""
    return env.get(_ENV_VAR, "").strip().lower() not in _FALSEY_ENV


def resolve_output_mode(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> bool:
    """JSONL 機械可読モードか判定する。

    解決順序は「明示フラグ > env > 既定 rich」。

    Args:
        argv: 引数列 (省略時は ``sys.argv[1:]``)。
        env: 環境変数 (省略時は ``os.environ``)。

    Returns:
        JSONL モードなら ``True``、rich 人間向けモードなら ``False``。
    """
    tokens = list(sys.argv[1:] if argv is None else argv)
    environ = os.environ if env is None else env
    explicit = _scan_explicit_flag(tokens)
    if explicit is not None:
        return explicit
    return _env_enables_json(environ)


def strip_mode_flags(argv: Sequence[str]) -> list[str]:
    """argv から ``--json`` / ``--no-json`` を除去する (``--`` 以降は保持)。

    モードは :func:`resolve_output_mode` が prescan 済みのため、Click パース前に
    これらを取り除くことでサブコマンド後位置 (例: ``images list --json``) でも
    "no such option" にならず受理できる (ADR 0058 §1 の位置非依存を実現)。

    Args:
        argv: プログラム名を除いた引数列。

    Returns:
        モードフラグを除いた引数列。
    """
    stripped: list[str] = []
    passthrough = False
    for token in argv:
        if passthrough:
            stripped.append(token)
            continue
        if token == "--":
            passthrough = True
            stripped.append(token)
        elif token not in (_JSON_FLAG, _NO_JSON_FLAG):
            stripped.append(token)
    return stripped


def set_json_mode(value: bool, *, prescanned: bool = False) -> None:
    """解決済みの出力モードを保存する (中央境界が呼ぶ)。"""
    global _json_mode, _prescanned_mode
    _json_mode = value
    _prescanned_mode = prescanned


def is_json_mode() -> bool:
    """現在の出力モードが JSONL かを返す (コマンド本体が参照する)。"""
    return _json_mode


def has_prescanned_mode() -> bool:
    """``main()`` が Click parse 前に出力モードを確定済みなら ``True``。"""
    return _prescanned_mode
