"""エラーレコードの同一原因グルーピング・サマリ・フィルタサービス (Qt-free)。

Wireframes v11 Frame 4 (Errors) のトリアージで使用する。
``(operation_type, error_type, model_name)`` を同一原因として集約し、
status / operation / error_type / model のクロスフィルタとサマリを提供する。

アクションは resolve / bulk resolve のみ (ADR 0033: 自動 retry 廃止)。
ignore は resolve に統合 (``resolved_at`` のみで状態管理)。
"""

from dataclasses import dataclass, field
from datetime import datetime
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
        raise NotImplementedError

    def group_errors(self, rows: list[ErrorRow]) -> list[ErrorGroup]:
        """行を (operation_type, error_type, model_name) で集約する。

        Args:
            rows: グルーピング対象の行 (通常は ``apply_filter`` 済み)。

        Returns:
            ``unresolved_count`` 降順 → ``count`` 降順で並んだグループのリスト。
        """
        raise NotImplementedError

    def summarize(self, rows: list[ErrorRow]) -> ErrorTriageSummary:
        """全行 (フィルタ前) からサマリを算出する。

        Args:
            rows: 全エラー行。

        Returns:
            total / unresolved / resolved / last_24h / by_error_type を含むサマリ。
        """
        raise NotImplementedError
