"""TRACE レベルのレベル解析・フィルタ動作テスト (Issue #584 / ADR 0046)。

per-item firehose を TRACE に分離し、通常 DEBUG では抑制、config で明示有効化できる
ことを保証する。``_parse_log_levels`` / ``_level_filter`` は純粋関数なので直接検証する。
"""

import pytest

from lorairo.utils.log import LEVEL_NAME_TO_NO, _level_filter, _parse_log_levels


class _Level:
    """loguru Record の ``record["level"].no`` を模した最小スタブ。"""

    def __init__(self, no: int) -> None:
        self.no = no


def _record(name: str, level_no: int) -> dict:
    return {"name": name, "level": _Level(level_no)}


@pytest.mark.unit
def test_level_name_to_no_has_trace() -> None:
    """TRACE が DEBUG(10) より下位の 5 として登録されている。"""
    assert LEVEL_NAME_TO_NO["TRACE"] == 5
    assert LEVEL_NAME_TO_NO["TRACE"] < LEVEL_NAME_TO_NO["DEBUG"]


@pytest.mark.unit
def test_parse_log_levels_accepts_trace_default() -> None:
    """config の level="TRACE" が数値 5 に解決される。"""
    default_no, module_nos = _parse_log_levels({"level": "TRACE"}, LEVEL_NAME_TO_NO)
    assert default_no == 5
    assert module_nos == {}


@pytest.mark.unit
def test_parse_log_levels_module_prefix_trace() -> None:
    """[log.levels] のモジュール別 TRACE 指定が解決される。"""
    config = {"level": "INFO", "levels": {"lorairo.database.db_core": "TRACE"}}
    default_no, module_nos = _parse_log_levels(config, LEVEL_NAME_TO_NO)
    assert default_no == LEVEL_NAME_TO_NO["INFO"]
    assert module_nos == {"lorairo.database.db_core": 5}


@pytest.mark.unit
def test_trace_record_filtered_at_debug_default() -> None:
    """既定 DEBUG では TRACE レコードは抑制される（firehose を出さない）。"""
    record = _record("lorairo.database.db_core", level_no=5)
    assert _level_filter(record, default_level_no=10, module_level_nos={}) is False


@pytest.mark.unit
def test_trace_record_passes_at_trace_default() -> None:
    """level="TRACE" 指定時は TRACE レコードが通過する。"""
    record = _record("lorairo.database.db_core", level_no=5)
    assert _level_filter(record, default_level_no=5, module_level_nos={}) is True


@pytest.mark.unit
def test_module_prefix_trace_enables_only_target_module() -> None:
    """モジュール別 TRACE 指定で対象モジュールのみ TRACE が通る。"""
    module_nos = {"lorairo.database": 5}

    target = _record("lorairo.database.db_core", level_no=5)
    other = _record("lorairo.gui.widgets.model_checkbox_widget", level_no=5)

    # 対象モジュールは TRACE 通過 (5 >= 5)
    assert _level_filter(target, default_level_no=10, module_level_nos=module_nos) is True
    # 非対象モジュールは既定 DEBUG(10) 適用で TRACE 抑制 (5 >= 10 は False)
    assert _level_filter(other, default_level_no=10, module_level_nos=module_nos) is False
