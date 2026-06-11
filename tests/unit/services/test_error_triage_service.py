# tests/unit/services/test_error_triage_service.py
"""ErrorTriageService のユニットテスト。"""

from datetime import UTC, datetime, timedelta

import pytest

from lorairo.services.error_triage_service import (
    ErrorFilter,
    ErrorGroup,
    ErrorRow,
    ErrorStatusFilter,
    ErrorTriageService,
    ErrorTriageSummary,
)

pytestmark = pytest.mark.unit


_UNSET = object()


def _row(
    error_id: int,
    *,
    operation_type: str = "annotation",
    error_type: str = "TimeoutError",
    error_message: str = "timed out",
    model_name: str | None = "gpt-4o",
    image_id: int | None = 1,
    resolved: bool = False,
    created_at: datetime | None | object = _UNSET,
) -> ErrorRow:
    """テスト用 ErrorRow を組み立てる。

    ``created_at`` を省略した場合は現在時刻 (UTC)、明示的に ``None`` を渡した
    場合は ``None`` を保持する (last_24h の None 除外検証用)。
    """
    resolved_created_at = datetime.now(UTC) if created_at is _UNSET else created_at
    assert resolved_created_at is None or isinstance(resolved_created_at, datetime)
    return ErrorRow(
        error_id=error_id,
        image_id=image_id,
        operation_type=operation_type,
        error_type=error_type,
        error_message=error_message,
        model_name=model_name,
        resolved=resolved,
        created_at=resolved_created_at,
    )


class TestApplyFilter:
    """apply_filter のテスト。"""

    @pytest.fixture
    def service(self) -> ErrorTriageService:
        return ErrorTriageService()

    def test_status_all_returns_all_rows(self, service: ErrorTriageService) -> None:
        rows = [_row(1, resolved=False), _row(2, resolved=True)]
        result = service.apply_filter(rows, ErrorFilter(status=ErrorStatusFilter.ALL))
        assert [r.error_id for r in result] == [1, 2]

    def test_status_unresolved_returns_only_unresolved(self, service: ErrorTriageService) -> None:
        rows = [_row(1, resolved=False), _row(2, resolved=True), _row(3, resolved=False)]
        result = service.apply_filter(rows, ErrorFilter(status=ErrorStatusFilter.UNRESOLVED))
        assert [r.error_id for r in result] == [1, 3]

    def test_status_resolved_returns_only_resolved(self, service: ErrorTriageService) -> None:
        rows = [_row(1, resolved=False), _row(2, resolved=True)]
        result = service.apply_filter(rows, ErrorFilter(status=ErrorStatusFilter.RESOLVED))
        assert [r.error_id for r in result] == [2]

    def test_operation_type_filter(self, service: ErrorTriageService) -> None:
        rows = [
            _row(1, operation_type="annotation"),
            _row(2, operation_type="registration"),
        ]
        result = service.apply_filter(
            rows, ErrorFilter(status=ErrorStatusFilter.ALL, operation_type="registration")
        )
        assert [r.error_id for r in result] == [2]

    def test_error_type_filter(self, service: ErrorTriageService) -> None:
        rows = [_row(1, error_type="TimeoutError"), _row(2, error_type="ValueError")]
        result = service.apply_filter(
            rows, ErrorFilter(status=ErrorStatusFilter.ALL, error_type="ValueError")
        )
        assert [r.error_id for r in result] == [2]

    def test_model_name_filter(self, service: ErrorTriageService) -> None:
        rows = [_row(1, model_name="gpt-4o"), _row(2, model_name="claude")]
        result = service.apply_filter(rows, ErrorFilter(status=ErrorStatusFilter.ALL, model_name="claude"))
        assert [r.error_id for r in result] == [2]

    def test_combined_and_filter(self, service: ErrorTriageService) -> None:
        rows = [
            _row(1, operation_type="annotation", error_type="TimeoutError", resolved=False),
            _row(2, operation_type="annotation", error_type="ValueError", resolved=False),
            _row(3, operation_type="annotation", error_type="TimeoutError", resolved=True),
        ]
        result = service.apply_filter(
            rows,
            ErrorFilter(
                status=ErrorStatusFilter.UNRESOLVED,
                operation_type="annotation",
                error_type="TimeoutError",
            ),
        )
        assert [r.error_id for r in result] == [1]

    def test_empty_input_returns_empty(self, service: ErrorTriageService) -> None:
        assert service.apply_filter([], ErrorFilter()) == []


class TestGroupErrors:
    """group_errors のテスト。"""

    @pytest.fixture
    def service(self) -> ErrorTriageService:
        return ErrorTriageService()

    def test_grouping_aggregates_by_key(self, service: ErrorTriageService) -> None:
        rows = [
            _row(
                1,
                operation_type="annotation",
                error_type="TimeoutError",
                model_name="gpt-4o",
                image_id=10,
                error_message="first",
                resolved=False,
            ),
            _row(
                2,
                operation_type="annotation",
                error_type="TimeoutError",
                model_name="gpt-4o",
                image_id=11,
                error_message="second",
                resolved=True,
            ),
            _row(
                3,
                operation_type="annotation",
                error_type="TimeoutError",
                model_name="gpt-4o",
                image_id=10,
                error_message="third",
                resolved=False,
            ),
        ]
        groups = service.group_errors(rows)
        assert len(groups) == 1
        g = groups[0]
        assert g.operation_type == "annotation"
        assert g.error_type == "TimeoutError"
        assert g.model_name == "gpt-4o"
        assert g.count == 3
        assert g.unresolved_count == 2
        assert g.sample_message == "first"  # グループ先頭行の error_message
        assert g.image_ids == [10, 11]  # 重複排除・出現順
        assert g.error_ids == [1, 2, 3]
        assert g.unresolved_error_ids == [1, 3]

    def test_image_ids_excludes_none_and_dedups(self, service: ErrorTriageService) -> None:
        rows = [
            _row(1, image_id=None),
            _row(2, image_id=5),
            _row(3, image_id=5),
            _row(4, image_id=None),
        ]
        groups = service.group_errors(rows)
        assert len(groups) == 1
        assert groups[0].image_ids == [5]

    def test_sort_by_unresolved_count_then_count(self, service: ErrorTriageService) -> None:
        # グループ A: unresolved=1, count=3
        rows_a = [
            _row(1, error_type="A", resolved=False),
            _row(2, error_type="A", resolved=True),
            _row(3, error_type="A", resolved=True),
        ]
        # グループ B: unresolved=2, count=2
        rows_b = [
            _row(4, error_type="B", resolved=False),
            _row(5, error_type="B", resolved=False),
        ]
        # グループ C: unresolved=2, count=4
        rows_c = [
            _row(6, error_type="C", resolved=False),
            _row(7, error_type="C", resolved=False),
            _row(8, error_type="C", resolved=True),
            _row(9, error_type="C", resolved=True),
        ]
        groups = service.group_errors(rows_a + rows_b + rows_c)
        # unresolved 降順 (C,B=2 > A=1)、同点は count 降順 (C=4 > B=2)
        assert [g.error_type for g in groups] == ["C", "B", "A"]

    def test_empty_input_returns_empty(self, service: ErrorTriageService) -> None:
        assert service.group_errors([]) == []


class TestSummarize:
    """summarize のテスト。"""

    @pytest.fixture
    def service(self) -> ErrorTriageService:
        return ErrorTriageService()

    def test_counts_and_by_error_type(self, service: ErrorTriageService) -> None:
        now = datetime.now(UTC)
        rows = [
            _row(1, error_type="TimeoutError", resolved=False, created_at=now),
            _row(2, error_type="TimeoutError", resolved=False, created_at=now),
            _row(3, error_type="ValueError", resolved=False, created_at=now),
            _row(4, error_type="ValueError", resolved=True, created_at=now),
        ]
        summary = service.summarize(rows)
        assert isinstance(summary, ErrorTriageSummary)
        assert summary.total == 4
        assert summary.unresolved == 3
        assert summary.resolved == 1
        # by_error_type は未解決基準
        assert summary.by_error_type == {"TimeoutError": 2, "ValueError": 1}

    def test_last_24h_boundary(self, service: ErrorTriageService) -> None:
        now = datetime.now(UTC)
        rows = [
            _row(1, created_at=now),  # 含む
            _row(2, created_at=now - timedelta(hours=23)),  # 含む
            _row(3, created_at=now - timedelta(hours=25)),  # 除外
            _row(4, created_at=None),  # created_at None は除外
        ]
        summary = service.summarize(rows)
        assert summary.last_24h == 2

    def test_empty_input(self, service: ErrorTriageService) -> None:
        summary = service.summarize([])
        assert summary.total == 0
        assert summary.unresolved == 0
        assert summary.resolved == 0
        assert summary.last_24h == 0
        assert summary.by_error_type == {}


def test_group_returns_error_group_instances() -> None:
    """group_errors が ErrorGroup インスタンスを返す。"""
    service = ErrorTriageService()
    groups = service.group_errors([_row(1)])
    assert all(isinstance(g, ErrorGroup) for g in groups)
