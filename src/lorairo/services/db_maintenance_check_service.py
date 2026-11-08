"""Read-only DB maintenance checks for provider batch state and image files (ADR 0099).

Checks only the project DB and local files. No provider API is called and nothing is
repaired; reported IDs are meant to be passed to existing commands.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from lorairo.public_api.exceptions import InvalidInputError
from lorairo.services.provider_batch_service import COMMON_BATCH_STATUSES

if TYPE_CHECKING:
    from lorairo.database.repository.image import ImageRepository
    from lorairo.database.repository.provider_batch import ProviderBatchRepository

SCOPES: tuple[str, ...] = ("batch", "files")
DEFAULT_SAMPLE_LIMIT = 100
MAX_SAMPLE_LIMIT = 500

# provider 側でまだ進行中とみなす共通 status (ADR 0038)。
_ACTIVE_BATCH_STATUSES = frozenset({"submitted", "validating", "running", "canceling"})
# item の画像参照が失われても結果反映に影響しない job status。
_SETTLED_BATCH_STATUSES = frozenset({"imported", "failed", "canceled", "expired"})


@dataclass(frozen=True)
class MaintenanceCheckDefinition:
    """1 種類の点検の固定メタデータ。"""

    check: str
    scope: str
    id_type: str
    description: str


CHECK_DEFINITIONS: tuple[MaintenanceCheckDefinition, ...] = (
    MaintenanceCheckDefinition(
        "batch_unknown_status",
        "batch",
        "job_id",
        "Job status is outside the shared provider batch vocabulary.",
    ),
    MaintenanceCheckDefinition(
        "batch_import_marker_mismatch",
        "batch",
        "job_id",
        "Job status 'imported' and imported_at disagree.",
    ),
    MaintenanceCheckDefinition(
        "batch_active_past_expiry",
        "batch",
        "job_id",
        "Job is still active in the DB after its recorded expires_at; refresh with batch status.",
    ),
    MaintenanceCheckDefinition(
        "batch_unlinked_items",
        "batch",
        "job_id",
        "Unimported items lost their image reference, so their results cannot be saved.",
    ),
    MaintenanceCheckDefinition(
        "image_file_missing",
        "files",
        "image_id",
        "Stored original image file does not exist.",
    ),
    MaintenanceCheckDefinition(
        "processed_file_missing",
        "files",
        "image_id",
        "At least one processed image file of the image does not exist.",
    ),
)
_DEFINITIONS_BY_CHECK = {definition.check: definition for definition in CHECK_DEFINITIONS}


def validate_check_options(scopes: Sequence[str], limit: int) -> tuple[str, ...]:
    """Reject invalid options before DB access; return de-duplicated scopes in canonical order."""
    if type(limit) is not int or not 1 <= limit <= MAX_SAMPLE_LIMIT:
        raise InvalidInputError("limit", f"Specify an integer from 1 to {MAX_SAMPLE_LIMIT}.")
    unknown = sorted(set(scopes) - set(SCOPES))
    if unknown:
        raise InvalidInputError("scope", f"Unknown scope {unknown}; choose from {list(SCOPES)}.")
    selected = set(scopes) or set(SCOPES)
    return tuple(scope for scope in SCOPES if scope in selected)


@dataclass(frozen=True)
class MaintenanceFinding:
    """1 種類の点検結果。``count`` は全体件数、``ids`` は昇順の先頭 ``limit`` 件。"""

    check: str
    scope: str
    id_type: str
    count: int
    ids: list[int]
    ids_truncated: bool
    description: str


@dataclass(frozen=True)
class MaintenanceReport:
    """点検全体の結果。対象外 scope の走査件数は ``None``。"""

    scopes: list[str]
    limit: int
    checks: list[MaintenanceFinding]
    checked_batch_jobs: int | None
    checked_images: int | None
    checked_processed_images: int | None
    provider_queried: bool = False
    repaired: bool = False

    @property
    def issue_count(self) -> int:
        return sum(finding.count for finding in self.checks)

    def summary(self) -> dict[str, object]:
        """Per-check records stay in their own JSONL items."""
        data = {key: value for key, value in asdict(self).items() if key != "checks"}
        data.update(
            checks_run=len(self.checks),
            issue_count=self.issue_count,
            issues_found=self.issue_count > 0,
            failing_checks=[finding.check for finding in self.checks if finding.count],
        )
        return data


def _finding(check: str, ids: Iterable[int], limit: int) -> MaintenanceFinding:
    definition = _DEFINITIONS_BY_CHECK[check]
    unique = sorted(set(ids))
    return MaintenanceFinding(
        check=check,
        scope=definition.scope,
        id_type=definition.id_type,
        count=len(unique),
        ids=unique[:limit],
        ids_truncated=len(unique) > limit,
        description=definition.description,
    )


def _as_utc(value: datetime) -> datetime:
    # SQLite 由来の datetime は naive で返るため UTC とみなして比較する。
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class DbMaintenanceCheckService:
    """Run read-only consistency checks through repositories.

    Args:
        image_repository: 画像/処理済み画像のパス走査に使う Repository。
        provider_batch_repository: Provider Batch 状態の取得に使う Repository。
        path_resolver: DB の stored path を実ファイルパスへ解決する関数。
        now: 期限比較に使う現在時刻 (UTC aware)。
    """

    def __init__(
        self,
        image_repository: ImageRepository,
        provider_batch_repository: ProviderBatchRepository,
        *,
        path_resolver: Callable[[str], Path],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._images = image_repository
        self._batches = provider_batch_repository
        self._resolve = path_resolver
        self._now = now

    def check(
        self, scopes: Sequence[str] = SCOPES, *, limit: int = DEFAULT_SAMPLE_LIMIT
    ) -> MaintenanceReport:
        """Run the selected scopes; counts always cover the whole project."""
        selected = validate_check_options(scopes, limit)
        findings: list[MaintenanceFinding] = []
        checked_jobs = checked_images = checked_processed = None
        if "batch" in selected:
            checked_jobs, batch_findings = self._check_batch(limit)
            findings.extend(batch_findings)
        if "files" in selected:
            checked_images, checked_processed, file_findings = self._check_files(limit)
            findings.extend(file_findings)
        return MaintenanceReport(
            scopes=list(selected),
            limit=limit,
            checks=findings,
            checked_batch_jobs=checked_jobs,
            checked_images=checked_images,
            checked_processed_images=checked_processed,
        )

    def _check_batch(self, limit: int) -> tuple[int, list[MaintenanceFinding]]:
        jobs = self._batches.list_job_states()
        now = self._now()
        unknown = [job.job_id for job in jobs if job.status not in COMMON_BATCH_STATUSES]
        marker = [job.job_id for job in jobs if (job.status == "imported") != (job.imported_at is not None)]
        expired = [
            job.job_id
            for job in jobs
            if job.status in _ACTIVE_BATCH_STATUSES
            and job.expires_at is not None
            and _as_utc(job.expires_at) < now
        ]
        unlinked = self._batches.list_job_ids_with_unlinked_items(_SETTLED_BATCH_STATUSES)
        return len(jobs), [
            _finding("batch_unknown_status", unknown, limit),
            _finding("batch_import_marker_mismatch", marker, limit),
            _finding("batch_active_past_expiry", expired, limit),
            _finding("batch_unlinked_items", unlinked, limit),
        ]

    def _check_files(self, limit: int) -> tuple[int, int, list[MaintenanceFinding]]:
        checked_images = 0
        missing_images: list[int] = []
        for image_id, stored_path in self._images.iter_stored_image_paths():
            checked_images += 1
            if not self._resolve(stored_path).is_file():
                missing_images.append(image_id)
        checked_processed = 0
        missing_processed: set[int] = set()
        for _processed_id, image_id, stored_path in self._images.iter_processed_image_paths():
            checked_processed += 1
            if not self._resolve(stored_path).is_file():
                missing_processed.add(image_id)
        return (
            checked_images,
            checked_processed,
            [
                _finding("image_file_missing", missing_images, limit),
                _finding("processed_file_missing", missing_processed, limit),
            ],
        )
