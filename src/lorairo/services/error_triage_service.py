"""エラーレコードの同一原因グルーピング・サマリ・フィルタサービス (Qt-free)。

Wireframes v11 Frame 4 (Errors) のトリアージで使用する。
``(operation_type, error_type, model_name)`` を同一原因として集約し、
status / operation / error_type / model のクロスフィルタとサマリを提供する。

アクションは resolve / bulk resolve のみ (ADR 0033: 自動 retry 廃止)。
ignore は resolve に統合 (``resolved_at`` のみで状態管理)。
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum


class ErrorStatusFilter(Enum):
    """status クロスフィルタの 3 値。"""

    ALL = "all"
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class ErrorRow:
    """1 エラーレコード (ORM 非依存の表示用 dataclass)。"""

    error_id: int
    image_id: int | None
    operation_type: str
    error_type: str
    error_message: str
    model_name: str | None
    resolved: bool
    created_at: datetime | None


@dataclass(frozen=True)
class ErrorFilter:
    """クロスフィルタの選択状態。None = 全て。"""

    status: ErrorStatusFilter = ErrorStatusFilter.UNRESOLVED
    operation_type: str | None = None
    error_type: str | None = None
    model_name: str | None = None


@dataclass(frozen=True)
class ErrorGroup:
    """同一原因 (operation_type, error_type, model_name) で集約したグループ。"""

    operation_type: str
    error_type: str
    model_name: str | None
    count: int
    unresolved_count: int
    sample_message: str
    image_ids: list[int] = field(default_factory=list)  # 影響画像 (重複排除・None 除外)
    error_ids: list[int] = field(default_factory=list)  # bulk resolve 用 (全件)
    unresolved_error_ids: list[int] = field(default_factory=list)  # bulk resolve 用 (未解決のみ)


@dataclass(frozen=True)
class ErrorTriageSummary:
    """エラー全体のサマリ。"""

    total: int
    unresolved: int
    resolved: int
    last_24h: int
    by_error_type: dict[str, int]  # error_type ごとの件数 (未解決基準)


class ErrorTriageService:
    """エラーレコードを同一原因にグルーピングし triage する (Qt-free)。"""

    def apply_filter(self, rows: list[ErrorRow], error_filter: ErrorFilter) -> list[ErrorRow]:
        """フィルタ条件に一致する行のみ返す。

        Args:
            rows: 全エラー行。
            error_filter: status / operation_type / error_type / model_name の選択状態。

        Returns:
            条件 (AND) に一致する行のリスト。
        """
        result: list[ErrorRow] = []
        for row in rows:
            # status フィルタ
            if error_filter.status is ErrorStatusFilter.UNRESOLVED and row.resolved:
                continue
            if error_filter.status is ErrorStatusFilter.RESOLVED and not row.resolved:
                continue
            # operation_type / error_type / model_name フィルタ (None はスキップ)
            if (
                error_filter.operation_type is not None
                and row.operation_type != error_filter.operation_type
            ):
                continue
            if error_filter.error_type is not None and row.error_type != error_filter.error_type:
                continue
            if error_filter.model_name is not None and row.model_name != error_filter.model_name:
                continue
            result.append(row)
        return result

    def group_errors(self, rows: list[ErrorRow]) -> list[ErrorGroup]:
        """行を (operation_type, error_type, model_name) で集約する。

        Args:
            rows: グルーピング対象の行 (通常は ``apply_filter`` 済み)。

        Returns:
            ``unresolved_count`` 降順 → ``count`` 降順で並んだグループのリスト。
        """
        # キーごとに出現順を保つため dict を使う (Python 3.7+ は挿入順保証)
        buckets: dict[tuple[str, str, str | None], list[ErrorRow]] = {}
        for row in rows:
            key = (row.operation_type, row.error_type, row.model_name)
            buckets.setdefault(key, []).append(row)

        groups: list[ErrorGroup] = []
        for (operation_type, error_type, model_name), bucket in buckets.items():
            unresolved_rows = [r for r in bucket if not r.resolved]
            # image_ids: None 除外・重複排除 (出現順)
            image_ids: list[int] = []
            seen: set[int] = set()
            for r in bucket:
                if r.image_id is not None and r.image_id not in seen:
                    seen.add(r.image_id)
                    image_ids.append(r.image_id)
            groups.append(
                ErrorGroup(
                    operation_type=operation_type,
                    error_type=error_type,
                    model_name=model_name,
                    count=len(bucket),
                    unresolved_count=len(unresolved_rows),
                    sample_message=bucket[0].error_message,
                    image_ids=image_ids,
                    error_ids=[r.error_id for r in bucket],
                    unresolved_error_ids=[r.error_id for r in unresolved_rows],
                )
            )

        # unresolved_count 降順 → count 降順
        groups.sort(key=lambda g: (g.unresolved_count, g.count), reverse=True)
        return groups

    def summarize(self, rows: list[ErrorRow]) -> ErrorTriageSummary:
        """全行 (フィルタ前) からサマリを算出する。

        Args:
            rows: 全エラー行。

        Returns:
            total / unresolved / resolved / last_24h / by_error_type を含むサマリ。
        """
        total = len(rows)
        unresolved_rows = [r for r in rows if not r.resolved]
        unresolved = len(unresolved_rows)
        resolved = total - unresolved

        # last_24h: created_at >= now(UTC)-24h (created_at None は除外)
        threshold = datetime.now(UTC) - timedelta(hours=24)
        last_24h = sum(1 for r in rows if r.created_at is not None and r.created_at >= threshold)

        # by_error_type: 未解決行の error_type ごと件数
        by_error_type: dict[str, int] = {}
        for r in unresolved_rows:
            by_error_type[r.error_type] = by_error_type.get(r.error_type, 0) + 1

        return ErrorTriageSummary(
            total=total,
            unresolved=unresolved,
            resolved=resolved,
            last_24h=last_24h,
            by_error_type=by_error_type,
        )
