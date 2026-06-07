"""CLI 機械可読 (JSONL) 出力ヘルパー (ADR 0057 §1/§2)。

stdout は機械可読 JSONL 専用。1 行 = 1 つの valid JSON object。ログ・進捗・装飾は
stderr に出す (本モジュールは stdout のみ扱う)。``kind`` は ``item`` / ``result`` /
``error`` の 3 種に閉じる (進捗用 ``event`` kind は採用しない、ADR 0057 §2)。

シリアライズは単一の :func:`_emit` を経由し ``json.dumps(..., ensure_ascii=False,
allow_nan=False, default=str)`` で行う:

- ``ensure_ascii=False``: 日本語タグ等を UTF-8 のまま保持する。
- ``allow_nan=False``: 非有限 float (``NaN`` / ``Infinity``) は標準 JSON で不正なため弾く。
  混入しても stdout 行を壊さないよう :func:`_emit` が emit 前に ``None`` へ正規化する。
- ``default=_json_default``: 非自明値のフォールバック。``datetime`` / ``date`` は ISO 8601
  (``isoformat()``) で安定化し (#669)、``Path`` 等はそれ以外は ``str()`` に委ねる。``default=str``
  だけだと ``datetime`` が ``str(datetime)`` (空白区切り・非 ISO) に劣化するため使わない。

``kind`` と エラー ``code`` は :class:`enum.StrEnum` で定義する。``StrEnum`` は ``str``
派生のため ``json.dumps`` が ``"item"`` のような安定 wire 値へ直接シリアライズする
(通常の ``Enum`` を ``default=str`` に頼ると ``"Kind.ITEM"`` のような不安定値になり、
``code`` で分岐するエージェントが壊れるため使わない、ADR 0057 §1)。
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class Kind(StrEnum):
    """stdout JSONL の ``kind``。3 種に閉じる (ADR 0057 §2)。"""

    ITEM = "item"
    RESULT = "result"
    ERROR = "error"


def _normalize_non_finite(value: Any) -> Any:
    """``NaN`` / ``Infinity`` を ``None`` へ再帰的に正規化する。

    非有限 float は標準 JSON で表現できない。score / metric に混入し得るため、
    ``allow_nan=False`` で弾く前に ``None`` へ寄せて stdout 行の JSON 妥当性を守る。

    Args:
        value: 任意の JSON シリアライズ対象値。

    Returns:
        非有限 float を ``None`` に置換した同型の値。
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _normalize_non_finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_non_finite(item) for item in value]
    return value


def _json_default(value: Any) -> str:
    """``json.dumps`` の非自明値フォールバック (ADR 0057 §1、#669)。

    ``datetime`` / ``date`` は ISO 8601 (``isoformat()``) へ正規化し、機械可読 JSONL の
    日時を ``str(datetime)`` (空白区切り・タイムゾーンなし) へ劣化させない。それ以外
    (``Path`` 等) は ``str()`` に委ねる。

    Args:
        value: ``json.dumps`` が直接シリアライズできなかった値。

    Returns:
        JSON 文字列としてそのまま埋め込めるシリアライズ結果。
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _emit(line: dict[str, Any]) -> None:
    """1 行 = 1 つの valid JSON object を stdout へ出力する (JSONL)。

    Args:
        line: stdout に 1 行で出力する JSON object。
    """
    safe = _normalize_non_finite(line)
    print(json.dumps(safe, ensure_ascii=False, allow_nan=False, default=_json_default))


def _to_payload(record: object) -> Any:
    """``item`` payload を取り出す。Pydantic モデルは ``model_dump(mode="json")``。

    Args:
        record: dict / Pydantic モデル / その他のスカラ。

    Returns:
        JSON シリアライズ可能な payload。
    """
    model_dump = getattr(record, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return record


def emit_item(record: object) -> None:
    """per-record 出力の 1 レコードを ``kind=item`` で 1 行出力する。

    巨大配列を 1 行に詰めずレコードごとに改行する。dict は展開し、スカラは
    ``value`` キーに包む。最終行のサマリは :func:`emit_result` で別途出す。

    Args:
        record: 出力する 1 レコード (dict / Pydantic モデル / スカラ)。
    """
    payload = _to_payload(record)
    if isinstance(payload, dict):
        _emit({"kind": Kind.ITEM, **payload})
    else:
        _emit({"kind": Kind.ITEM, "value": payload})


def emit_result(message: str, **output: Any) -> None:
    """成功時の最終行 ``kind=result`` を出力する。

    Args:
        message: 人間可読のサマリ文。
        **output: 件数メタ等の追加フィールド (``count`` / ``total`` / ``processed`` 等)。
    """
    _emit({"kind": Kind.RESULT, "ok": True, "message": message, **output})


def emit_error(
    code: str,
    message: str,
    *,
    retryable: bool,
    user_action_required: bool,
    hint: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """失敗時の最終行 ``kind=error`` を出力する。

    stderr の文字列パースに依存させず、stdout の JSONL 最終行に構造化エラーを出す。
    エージェントは ``code`` / ``retryable`` / ``user_action_required`` で分岐する。

    Args:
        code: 安定エラーコード (:class:`lorairo.cli._errors.ErrorCode`)。
        message: 人間可読のエラー文。
        retryable: 同一/調整後の再試行で成功し得るか。
        user_action_required: 入力/設定の変更が必要か。
        hint: 任意の対処ヒント。
        details: 任意の追加情報 (``{"limit": 500, "matched": 1234}`` 等)。
    """
    line: dict[str, Any] = {
        "kind": Kind.ERROR,
        "ok": False,
        "code": code,
        "message": message,
        "retryable": retryable,
        "user_action_required": user_action_required,
    }
    if hint:
        line["hint"] = hint
    if details:
        line["details"] = details
    _emit(line)
