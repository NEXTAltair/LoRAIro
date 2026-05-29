"""`_select_image_records` ヘルパーの unit test (Issue #538)。

CLI 起動を介さず `_select_image_records` を直接呼ぶ。レコードは軽量 dict の
リストで構成し、適用順序 (image-id → offset → limit) と warning 出力を検証する。
"""

from typing import Any

import pytest

from lorairo.cli.commands import annotate
from lorairo.cli.commands.annotate import _select_image_records


def _make_records(count: int) -> list[dict[str, Any]]:
    """id が 1..count、stored_image_path が "{id}.jpg" の軽量レコードを作る。"""
    return [{"id": i, "stored_image_path": f"{i}.jpg"} for i in range(1, count + 1)]


@pytest.mark.unit
def test_limit_returns_at_most_n_leading_records() -> None:
    records = _make_records(5)

    result = _select_image_records(records, limit=3, offset=0, image_ids=None)

    assert len(result) <= 3
    assert [r["id"] for r in result] == [1, 2, 3]


@pytest.mark.unit
def test_offset_and_limit_select_deterministic_slice() -> None:
    records = _make_records(10)

    result = _select_image_records(records, limit=3, offset=2, image_ids=None)

    # records[2:2+3] 相当 (sharding の決定的継続)
    assert [r["id"] for r in result] == [3, 4, 5]


@pytest.mark.unit
def test_image_ids_returns_only_matching_records_in_db_order() -> None:
    records = _make_records(5)

    # 要求順は [4, 2] だが DB レコード順 (2, 4) が保持される
    result = _select_image_records(records, limit=None, offset=0, image_ids=[4, 2])

    assert [r["id"] for r in result] == [2, 4]


@pytest.mark.unit
def test_partial_missing_ids_returns_found_and_warns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = _make_records(3)
    warnings: list[str] = []
    monkeypatch.setattr(annotate.console, "print", lambda msg: warnings.append(str(msg)))

    result = _select_image_records(records, limit=None, offset=0, image_ids=[1, 99])

    assert [r["id"] for r in result] == [1]
    assert len(warnings) == 1
    assert "not found in project" in warnings[0]
    assert "99" in warnings[0]


@pytest.mark.unit
def test_all_ids_missing_returns_empty_without_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = _make_records(3)
    warnings: list[str] = []
    monkeypatch.setattr(annotate.console, "print", lambda msg: warnings.append(str(msg)))

    result = _select_image_records(records, limit=None, offset=0, image_ids=[100, 200])

    assert result == []
    assert len(warnings) == 1
    assert "100" in warnings[0] and "200" in warnings[0]


@pytest.mark.unit
def test_image_ids_applied_before_offset_and_limit() -> None:
    records = _make_records(10)

    # image-id フィルタで [2,3,4,5,6] → offset 1 で [3,4,5,6] → limit 2 で [3,4]
    result = _select_image_records(records, limit=2, offset=1, image_ids=[2, 3, 4, 5, 6])

    assert [r["id"] for r in result] == [3, 4]


@pytest.mark.unit
def test_no_selection_passes_all_records_through() -> None:
    records = _make_records(4)

    result = _select_image_records(records, limit=None, offset=0, image_ids=None)

    assert [r["id"] for r in result] == [1, 2, 3, 4]


@pytest.mark.unit
def test_empty_image_ids_list_passes_all_records_through() -> None:
    records = _make_records(4)

    result = _select_image_records(records, limit=None, offset=0, image_ids=[])

    assert [r["id"] for r in result] == [1, 2, 3, 4]


@pytest.mark.unit
def test_duplicate_ids_dedup_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    records = _make_records(3)
    warnings: list[str] = []
    monkeypatch.setattr(annotate.console, "print", lambda msg: warnings.append(str(msg)))

    # 99 を重複指定 → warning は dedup され 99 を 1 回だけ列挙
    result = _select_image_records(records, limit=None, offset=0, image_ids=[1, 99, 99])

    assert [r["id"] for r in result] == [1]
    assert len(warnings) == 1
    assert warnings[0].count("99") == 1


@pytest.mark.unit
def test_offset_beyond_range_returns_empty() -> None:
    records = _make_records(3)

    result = _select_image_records(records, limit=None, offset=10, image_ids=None)

    assert result == []
