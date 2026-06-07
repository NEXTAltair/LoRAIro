"""CLI JSONL emit ヘルパー (``lorairo.cli._emit``) の test (ADR 0057 §1/§2)。"""

from __future__ import annotations

import json
import math
from datetime import date, datetime

import pytest

from lorairo.cli._emit import Kind, emit_error, emit_item, emit_result


def _last_json_line(captured: str) -> dict:
    """capsys stdout の最終行を JSON として読む。"""
    lines = [line for line in captured.splitlines() if line.strip()]
    return json.loads(lines[-1])


@pytest.mark.unit
@pytest.mark.cli
def test_kind_serializes_to_stable_wire_value() -> None:
    """StrEnum の kind は ``"item"`` 等の安定 wire 値にシリアライズされる。"""
    assert json.dumps({"kind": Kind.ITEM}) == '{"kind": "item"}'
    assert Kind.RESULT == "result"
    assert Kind.ERROR == "error"


@pytest.mark.unit
@pytest.mark.cli
def test_emit_item_expands_dict(capsys: pytest.CaptureFixture[str]) -> None:
    """dict レコードは ``kind=item`` 行に展開される。"""
    emit_item({"image_id": 7, "file_path": "/a/b.png"})
    line = _last_json_line(capsys.readouterr().out)
    assert line == {"kind": "item", "image_id": 7, "file_path": "/a/b.png"}


@pytest.mark.unit
@pytest.mark.cli
def test_emit_serializes_datetime_as_iso8601(capsys: pytest.CaptureFixture[str]) -> None:
    """raw datetime は ISO 8601 (T 区切り) で emit される (#669)。

    ``str(datetime)`` の空白区切りへ劣化させない。``batch *`` の datetime フィールドが
    ``_emit`` の ``default`` 経由で出力される経路を守る。
    """
    emit_item({"image_id": 1, "imported_at": datetime(2026, 6, 3, 12, 44, 24, 797734)})
    line = _last_json_line(capsys.readouterr().out)
    assert line["imported_at"] == "2026-06-03T12:44:24.797734"
    assert " " not in line["imported_at"]  # 空白区切りの str(datetime) でないこと


@pytest.mark.unit
@pytest.mark.cli
def test_emit_serializes_date_as_iso8601(capsys: pytest.CaptureFixture[str]) -> None:
    """raw date も ISO 8601 で emit される (#669)。"""
    emit_result("ok", created=date(2026, 6, 3))
    line = _last_json_line(capsys.readouterr().out)
    assert line["created"] == "2026-06-03"


@pytest.mark.unit
@pytest.mark.cli
def test_emit_item_uses_model_dump_json_mode(capsys: pytest.CaptureFixture[str]) -> None:
    """Pydantic モデルは ``model_dump(mode="json")`` で展開される。"""

    class _FakeModel:
        def model_dump(self, *, mode: str = "python") -> dict:
            assert mode == "json"
            return {"name": "gpt4o", "score": 0.5}

    emit_item(_FakeModel())
    line = _last_json_line(capsys.readouterr().out)
    assert line == {"kind": "item", "name": "gpt4o", "score": 0.5}


@pytest.mark.unit
@pytest.mark.cli
def test_emit_item_wraps_scalar(capsys: pytest.CaptureFixture[str]) -> None:
    """スカラ値は ``value`` キーに包まれる。"""
    emit_item("hello")
    line = _last_json_line(capsys.readouterr().out)
    assert line == {"kind": "item", "value": "hello"}


@pytest.mark.unit
@pytest.mark.cli
def test_emit_result_carries_meta(capsys: pytest.CaptureFixture[str]) -> None:
    """``kind=result`` は ok/message + 件数メタを持つ。"""
    emit_result("done", processed=480, total=480)
    line = _last_json_line(capsys.readouterr().out)
    assert line == {
        "kind": "result",
        "ok": True,
        "message": "done",
        "processed": 480,
        "total": 480,
    }


@pytest.mark.unit
@pytest.mark.cli
def test_emit_error_includes_flags_and_optional_fields(capsys: pytest.CaptureFixture[str]) -> None:
    """``kind=error`` は code/flag を持ち、hint/details は任意。"""
    emit_error(
        "RESULT_SET_TOO_LARGE",
        "too many",
        retryable=False,
        user_action_required=True,
        hint="narrow it",
        details={"limit": 500, "matched": 1234},
    )
    line = _last_json_line(capsys.readouterr().out)
    assert line == {
        "kind": "error",
        "ok": False,
        "code": "RESULT_SET_TOO_LARGE",
        "message": "too many",
        "retryable": False,
        "user_action_required": True,
        "hint": "narrow it",
        "details": {"limit": 500, "matched": 1234},
    }


@pytest.mark.unit
@pytest.mark.cli
def test_emit_error_omits_falsy_optional_fields(capsys: pytest.CaptureFixture[str]) -> None:
    """hint/details が未指定なら error 行に含めない。"""
    emit_error("INVALID_INPUT", "bad", retryable=False, user_action_required=True)
    line = _last_json_line(capsys.readouterr().out)
    assert "hint" not in line
    assert "details" not in line


@pytest.mark.unit
@pytest.mark.cli
def test_emit_normalizes_non_finite_floats(capsys: pytest.CaptureFixture[str]) -> None:
    """NaN / Infinity は None へ正規化され、行は valid JSON を保つ。"""
    emit_item({"image_id": 1, "score": math.nan, "metric": math.inf})
    raw = [line for line in capsys.readouterr().out.splitlines() if line.strip()][-1]
    # 行が標準 JSON として読める (NaN/Infinity リテラルを含まない)
    assert "NaN" not in raw
    assert "Infinity" not in raw
    parsed = json.loads(raw)
    assert parsed["score"] is None
    assert parsed["metric"] is None
    assert parsed["image_id"] == 1
