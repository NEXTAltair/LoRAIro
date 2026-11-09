"""Read-only DB maintenance checks for provider batch state and image files (ADR 0099).

Default scopes (`batch`, `files`) check only the project DB and local files without
calling any provider API. When `--scope provider` is explicitly requested, provider
batch jobs are compared against remote provider status in read-only mode (`repaired=False`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from lorairo.public_api.exceptions import (
    APIKeyNotConfiguredError,
    InvalidInputError,
    ResultSetTooLargeError,
)
from lorairo.services.provider_batch_service import (
    COMMON_BATCH_STATUSES,
    ProviderBatchError,
    ProviderBatchJobNotFoundError,
    ProviderBatchJobService,
    ProviderBatchStatus,
)

if TYPE_CHECKING:
    from lorairo.database.repository.image import ImageRepository
    from lorairo.database.repository.provider_batch import (
        ProviderBatchJobState,
        ProviderBatchRepository,
    )

DEFAULT_SCOPES: tuple[str, ...] = ("batch", "files")
SCOPES: tuple[str, ...] = ("batch", "files", "provider")
DEFAULT_SAMPLE_LIMIT = 100
MAX_SAMPLE_LIMIT = 500
MAX_PROVIDER_CHECK_JOBS = 500

# provider 側でまだ進行中とみなす共通 status (ADR 0038)。
_ACTIVE_BATCH_STATUSES = frozenset({"submitted", "validating", "running", "canceling"})
_IN_PROGRESS_DB_STATUSES = _ACTIVE_BATCH_STATUSES | frozenset({"in_progress", "finalizing", "cancelling"})
_TERMINAL_PROVIDER_STATUSES = frozenset({"completed", "failed", "canceled", "expired"})
_TERMINAL_DB_STATUSES = frozenset({"completed", "failed", "canceled", "expired", "imported"})
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
    MaintenanceCheckDefinition(
        "provider_status_mismatch",
        "provider",
        "job_id",
        "DB job status disagrees with the provider batch status; refresh with batch status.",
    ),
    MaintenanceCheckDefinition(
        "provider_job_missing",
        "provider",
        "job_id",
        "Provider batch job ID does not exist on the provider side.",
    ),
    MaintenanceCheckDefinition(
        "provider_counts_mismatch",
        "provider",
        "job_id",
        "DB succeeded/failed counts disagree with the provider batch counts.",
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
    selected = set(scopes) or set(DEFAULT_SCOPES)
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
    status: Literal["success", "partial_success"] = "success"

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


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def _is_provider_job_missing_error(exc: BaseException) -> bool:
    if isinstance(exc, ProviderBatchJobNotFoundError):
        return True
    for item in _iter_exception_chain(exc):
        if isinstance(item, ProviderBatchJobNotFoundError):
            return True
        details = getattr(item, "details", None)
        if isinstance(details, dict) and details.get("reason") == "provider_job_missing":
            return True
        if any(
            cls.__name__ in {"NotFoundError", "ProviderBatchJobNotFoundError"} for cls in type(item).__mro__
        ):
            return True
        if getattr(item, "status_code", None) == 404:
            return True
        code = str(getattr(item, "code", "") or "").lower()
        if code in {"not_found", "job_not_found", "batch_not_found", "batch_job_not_found"}:
            return True
        message = str(getattr(item, "message", "") or item).lower()
        if "file" not in message and any(
            hint in message
            for hint in (
                "no such batch",
                "batch not found",
                "job not found",
                "does not exist",
                "404",
                "not found",
            )
        ):
            return True
    return False


def _is_auth_failure(exc: BaseException) -> bool:
    if isinstance(exc, APIKeyNotConfiguredError):
        return True
    for item in _iter_exception_chain(exc):
        if isinstance(item, APIKeyNotConfiguredError):
            return True
        if any(
            cls.__name__ in {"APIKeyNotConfiguredError", "AuthenticationError", "PermissionDeniedError"}
            for cls in type(item).__mro__
            if cls is not PermissionError
        ):
            return True
        code = str(getattr(item, "code", "") or "").lower()
        if code in {
            "auth_error",
            "authentication_error",
            "authentication_failed",
            "unauthorized",
            "invalid_api_key",
        }:
            return True
    return False


def _normalize_remote_status(provider: str, remote_status: ProviderBatchStatus | Any) -> str:
    raw = getattr(remote_status, "status", None) or getattr(remote_status, "provider_status", None) or ""
    raw_str = str(raw).strip()
    if not raw_str:
        return ""
    try:
        return ProviderBatchJobService.normalize_status(provider or "openai", raw_str)
    except ProviderBatchError:
        return raw_str.lower()


def _has_provider_status_mismatch(
    job: ProviderBatchJobState, remote_status: ProviderBatchStatus | Any
) -> bool:
    normalized_remote = _normalize_remote_status(job.provider, remote_status)
    if not normalized_remote:
        return False
    db_status = job.status.strip()
    if db_status in _IN_PROGRESS_DB_STATUSES:
        return normalized_remote in _TERMINAL_PROVIDER_STATUSES
    if db_status in _TERMINAL_DB_STATUSES:
        expected_remote = "completed" if db_status == "imported" else db_status
        return normalized_remote != expected_remote
    return normalized_remote != db_status


def _has_provider_counts_mismatch(
    job: ProviderBatchJobState, remote_status: ProviderBatchStatus | Any
) -> bool:
    remote_succeeded = getattr(remote_status, "succeeded_count", None)
    remote_failed = getattr(remote_status, "failed_count", None)
    if (
        remote_succeeded is not None
        and job.succeeded_count is not None
        and int(remote_succeeded) != int(job.succeeded_count)
    ):
        return True
    return bool(
        remote_failed is not None
        and job.failed_count is not None
        and int(remote_failed) != int(job.failed_count)
    )


class DbMaintenanceCheckService:
    """Run read-only consistency checks through repositories.

    Args:
        image_repository: 画像/処理済み画像のパス走査に使う Repository。
        provider_batch_repository: Provider Batch 状態の取得に使う Repository。
        path_resolver: DB の stored path を実ファイルパスへ解決する関数。
        now: 期限比較に使う現在時刻 (UTC aware)。
        remote_status_fetcher: ``--scope provider`` 時に remote job status を read-only で取得する関数。
        provider_batch_service: ``fetch_remote_status_readonly`` / ``inspect_remote_job`` を持つ service。
    """

    def __init__(
        self,
        image_repository: ImageRepository,
        provider_batch_repository: ProviderBatchRepository,
        *,
        path_resolver: Callable[[str], Path],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        remote_status_fetcher: Callable[[ProviderBatchJobState], ProviderBatchStatus | None] | None = None,
        provider_batch_service: Any | None = None,
    ) -> None:
        self._images = image_repository
        self._batches = provider_batch_repository
        self._resolve = path_resolver
        self._now = now
        if remote_status_fetcher is not None:
            self._fetch_remote_status: (
                Callable[[ProviderBatchJobState], ProviderBatchStatus | None] | None
            ) = remote_status_fetcher
        elif provider_batch_service is not None:
            self._fetch_remote_status = getattr(
                provider_batch_service,
                "fetch_remote_status_readonly",
                getattr(provider_batch_service, "inspect_remote_job", None),
            )
        else:
            self._fetch_remote_status = None

    def check(
        self, scopes: Sequence[str] = DEFAULT_SCOPES, *, limit: int = DEFAULT_SAMPLE_LIMIT
    ) -> MaintenanceReport:
        """Run the selected scopes; counts always cover the whole project."""
        selected = validate_check_options(scopes, limit)
        findings: list[MaintenanceFinding] = []
        checked_jobs = checked_images = checked_processed = None
        provider_queried = "provider" in selected
        status: Literal["success", "partial_success"] = "success"
        jobs: list[ProviderBatchJobState] | None = None

        if "batch" in selected or provider_queried:
            jobs = self._batches.list_job_states()
            checked_jobs = len(jobs)
            if provider_queried and len(jobs) > MAX_PROVIDER_CHECK_JOBS:
                raise ResultSetTooLargeError(len(jobs), MAX_PROVIDER_CHECK_JOBS)

        if "batch" in selected:
            _, batch_findings = self._check_batch(limit, jobs=jobs)
            findings.extend(batch_findings)
        if "files" in selected:
            checked_images, checked_processed, file_findings = self._check_files(limit)
            findings.extend(file_findings)
        if provider_queried:
            status, provider_findings = self._check_provider(limit, jobs=jobs)
            findings.extend(provider_findings)
        return MaintenanceReport(
            scopes=list(selected),
            limit=limit,
            checks=findings,
            checked_batch_jobs=checked_jobs,
            checked_images=checked_images,
            checked_processed_images=checked_processed,
            provider_queried=provider_queried,
            repaired=False,
            status=status,
        )

    def _check_batch(
        self, limit: int, *, jobs: list[ProviderBatchJobState] | None = None
    ) -> tuple[int, list[MaintenanceFinding]]:
        if jobs is None:
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

    def _probe_provider_job(
        self, job: ProviderBatchJobState
    ) -> tuple[bool, ProviderBatchStatus | None, BaseException | None]:
        """Return ``(is_missing, remote_status, probe_error)`` for a single job."""
        assert self._fetch_remote_status is not None
        try:
            remote_status = self._fetch_remote_status(job)
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)) or _is_auth_failure(exc):
                raise
            if _is_provider_job_missing_error(exc):
                return True, None, None
            return False, None, exc
        if remote_status is None:
            return True, None, None
        return False, remote_status, None

    def _check_provider(
        self, limit: int, *, jobs: list[ProviderBatchJobState] | None = None
    ) -> tuple[Literal["success", "partial_success"], list[MaintenanceFinding]]:
        all_jobs = jobs if jobs is not None else self._batches.list_job_states()
        target_jobs = [job for job in all_jobs if job.provider_job_id is not None]
        if max(len(target_jobs), len(all_jobs)) > MAX_PROVIDER_CHECK_JOBS:
            raise ResultSetTooLargeError(max(len(target_jobs), len(all_jobs)), MAX_PROVIDER_CHECK_JOBS)
        if target_jobs and self._fetch_remote_status is None:
            raise ProviderBatchError("Provider status fetcher is not configured for --scope provider.")

        status_mismatch: list[int] = []
        missing_jobs: list[int] = []
        counts_mismatch: list[int] = []
        succeeded_probes = 0
        probe_errors: list[BaseException] = []

        for job in target_jobs:
            is_missing, remote_status, probe_error = self._probe_provider_job(job)
            if probe_error is not None:
                probe_errors.append(probe_error)
                continue
            succeeded_probes += 1
            if is_missing or remote_status is None:
                missing_jobs.append(job.job_id)
                continue
            if _has_provider_status_mismatch(job, remote_status):
                status_mismatch.append(job.job_id)
            if _has_provider_counts_mismatch(job, remote_status):
                counts_mismatch.append(job.job_id)

        if probe_errors and succeeded_probes == 0:
            raise probe_errors[0]

        report_status: Literal["success", "partial_success"] = (
            "partial_success" if probe_errors else "success"
        )
        return report_status, [
            _finding("provider_status_mismatch", status_mismatch, limit),
            _finding("provider_job_missing", missing_jobs, limit),
            _finding("provider_counts_mismatch", counts_mismatch, limit),
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
