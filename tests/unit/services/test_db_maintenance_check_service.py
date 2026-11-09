"""Read-only DB maintenance checks against isolated in-memory SQLite (ADR 0099)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lorairo.database.repository.image import ImageRepository
from lorairo.database.repository.provider_batch import ProviderBatchRepository
from lorairo.database.schema import (
    Base,
    Image,
    ProcessedImage,
    ProviderBatchItem,
    ProviderBatchJob,
)
from lorairo.public_api.exceptions import (
    APIKeyNotConfiguredError,
    InvalidInputError,
    ResultSetTooLargeError,
)
from lorairo.services.db_maintenance_check_service import (
    CHECK_DEFINITIONS,
    DEFAULT_SCOPES,
    MAX_PROVIDER_CHECK_JOBS,
    DbMaintenanceCheckService,
    validate_check_options,
)
from lorairo.services.provider_batch_service import (
    ProviderBatchJobNotFoundError,
    ProviderBatchStatus,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def _image(image_id: int) -> Image:
    return Image(
        id=image_id,
        uuid=f"synthetic-{image_id}",
        phash=f"synthetic-{image_id}",
        original_image_path=f"source/{image_id}.png",
        stored_image_path=f"image_dataset/{image_id}.png",
        width=32,
        height=32,
        format="PNG",
        extension=".png",
    )


def _processed(processed_id: int, image_id: int) -> ProcessedImage:
    return ProcessedImage(
        id=processed_id,
        image_id=image_id,
        stored_image_path=f"image_dataset/512/{processed_id}.webp",
        width=16,
        height=16,
        has_alpha=False,
    )


def _job(job_id: int, status: str, **fields: object) -> ProviderBatchJob:
    return ProviderBatchJob(
        id=job_id, provider="openai", provider_job_id=f"batch_{job_id}", status=status, **fields
    )


def _item(item_id: int, job_id: int, image_id: int | None, status: str = "submitted") -> ProviderBatchItem:
    return ProviderBatchItem(
        id=item_id,
        job_id=job_id,
        custom_id=f"c{item_id}",
        image_id=image_id,
        task_type="tags",
        status=status,
    )


@pytest.fixture
def database():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    yield factory
    engine.dispose()


def _service(database, root: Path) -> DbMaintenanceCheckService:
    return DbMaintenanceCheckService(
        ImageRepository(database),
        ProviderBatchRepository(database),
        path_resolver=lambda stored: root / stored,
        now=lambda: NOW,
    )


def _by_check(report):
    return {finding.check: finding for finding in report.checks}


def test_batch_checks_report_each_inconsistency_from_db_only(database, tmp_path):
    with database() as session:
        session.add_all([_image(1), _image(2)])
        session.add_all(
            [
                _job(1, "running", expires_at=NOW + timedelta(hours=1)),
                _job(2, "mystery"),
                _job(3, "imported"),  # imported_at が無い
                _job(4, "completed", imported_at=NOW),  # status と imported_at が矛盾
                _job(5, "imported", imported_at=NOW),
                # SQLite が返す naive datetime も UTC として比較する
                _job(6, "validating", expires_at=(NOW - timedelta(minutes=1)).replace(tzinfo=None)),
                _job(7, "expired", expires_at=NOW - timedelta(days=1)),
                _job(8, "completed"),
                _job(9, "failed"),
            ]
        )
        session.flush()
        session.add_all(
            [
                _item(1, 1, 1),
                _item(2, 8, None),  # 未取込み job で画像参照が失われた
                _item(3, 8, None),
                _item(4, 5, None, status="imported"),  # 取込み済み job は対象外
                _item(5, 9, None),  # 終端失敗 job は対象外
                _item(6, 1, 2, status="imported"),
            ]
        )
        session.commit()

    report = _service(database, tmp_path).check(["batch"])

    findings = _by_check(report)
    assert report.scopes == ["batch"] and report.checked_batch_jobs == 9
    assert report.checked_images is None and report.checked_processed_images is None
    assert findings["batch_unknown_status"].ids == [2]
    assert findings["batch_import_marker_mismatch"].ids == [3, 4]
    assert findings["batch_active_past_expiry"].ids == [6]
    assert findings["batch_unlinked_items"].ids == [8]
    assert findings["batch_unlinked_items"].count == 1
    assert {finding.scope for finding in report.checks} == {"batch"}
    assert report.issue_count == 5
    summary = report.summary()
    assert summary["issues_found"] is True and summary["provider_queried"] is False
    assert summary["failing_checks"] == [
        "batch_unknown_status",
        "batch_import_marker_mismatch",
        "batch_active_past_expiry",
        "batch_unlinked_items",
    ]


def test_file_checks_count_missing_originals_and_processed_per_image(database, tmp_path):
    (tmp_path / "image_dataset" / "512").mkdir(parents=True)
    for image_id in (1, 3):
        (tmp_path / "image_dataset" / f"{image_id}.png").write_bytes(b"x")
    (tmp_path / "image_dataset" / "512" / "10.webp").write_bytes(b"x")
    # ディレクトリは実ファイルとみなさない
    (tmp_path / "image_dataset" / "4.png").mkdir()
    with database() as session:
        session.add_all([_image(i) for i in (1, 2, 3, 4)])
        session.flush()
        session.add_all([_processed(10, 1), _processed(11, 1), _processed(12, 3), _processed(13, 3)])
        session.commit()

    report = _service(database, tmp_path).check(["files"])

    findings = _by_check(report)
    assert (report.checked_images, report.checked_processed_images) == (4, 4)
    assert report.checked_batch_jobs is None
    assert findings["image_file_missing"].ids == [2, 4]
    assert findings["processed_file_missing"].ids == [1, 3]
    assert findings["processed_file_missing"].id_type == "image_id"


def test_limit_caps_ids_but_not_counts_and_repository_scans_across_chunks(database, tmp_path):
    with database() as session:
        session.add_all([_image(i) for i in range(1, 8)])
        session.commit()
    repository = ImageRepository(database)
    assert [image_id for image_id, _ in repository.iter_stored_image_paths(chunk_size=3)] == list(
        range(1, 8)
    )

    report = _service(database, tmp_path).check(["files"], limit=2)

    finding = _by_check(report)["image_file_missing"]
    assert finding.count == 7 and finding.ids == [1, 2] and finding.ids_truncated is True


def test_clean_project_runs_all_checks_with_zero_findings(database, tmp_path):
    report = _service(database, tmp_path).check()
    assert report.scopes == ["batch", "files"]
    assert report.provider_queried is False and report.repaired is False
    assert [finding.check for finding in report.checks] == [
        d.check for d in CHECK_DEFINITIONS if d.scope in DEFAULT_SCOPES
    ]
    assert report.issue_count == 0 and report.summary()["issues_found"] is False
    assert all(finding.ids == [] and not finding.ids_truncated for finding in report.checks)


@pytest.mark.parametrize(
    ("scopes", "limit", "field"),
    [(["batch"], 0, "limit"), (["batch"], 501, "limit"), (["sqlite"], 10, "scope")],
)
def test_invalid_options_are_rejected(scopes, limit, field):
    with pytest.raises(InvalidInputError) as excinfo:
        validate_check_options(scopes, limit)
    assert field in str(excinfo.value)


def test_scopes_are_deduplicated_in_canonical_order():
    assert validate_check_options(["files", "batch", "files"], 1) == ("batch", "files")
    assert validate_check_options(["provider", "batch"], 1) == ("batch", "provider")
    assert validate_check_options([], 1) == ("batch", "files")


def test_provider_scope_detects_status_missing_and_counts_mismatches_without_mutating_db(
    database, tmp_path
):
    with database() as session:
        session.add_all(
            [
                _job(1, "submitted", succeeded_count=0, failed_count=0),
                _job(2, "completed", succeeded_count=2, failed_count=0),
                _job(3, "running", succeeded_count=0, failed_count=0),
                _job(4, "completed", succeeded_count=5, failed_count=0),
                _job(5, "imported", imported_at=NOW, succeeded_count=3, failed_count=0),
            ]
        )
        session.commit()

    remote_by_id = {
        1: ProviderBatchStatus(
            provider_job_id="batch_1",
            provider_status="completed",
            succeeded_count=0,
            failed_count=0,
        ),
        2: ProviderBatchStatus(
            provider_job_id="batch_2",
            provider_status="failed",
            succeeded_count=2,
            failed_count=0,
        ),
        4: ProviderBatchStatus(
            provider_job_id="batch_4",
            provider_status="completed",
            succeeded_count=4,
            failed_count=1,
        ),
        5: ProviderBatchStatus(
            provider_job_id="batch_5",
            provider_status="completed",
            succeeded_count=3,
            failed_count=0,
        ),
    }

    def fake_fetcher(job):
        if job.job_id == 3:
            raise ProviderBatchJobNotFoundError("404 batch not found")
        return remote_by_id[job.job_id]

    service = DbMaintenanceCheckService(
        ImageRepository(database),
        ProviderBatchRepository(database),
        path_resolver=lambda stored: tmp_path / stored,
        now=lambda: NOW,
        remote_status_fetcher=fake_fetcher,
    )
    report = service.check(["provider"])

    findings = _by_check(report)
    assert report.scopes == ["provider"]
    assert report.provider_queried is True and report.repaired is False
    assert report.status == "success"
    assert report.checked_batch_jobs == 5
    assert findings["provider_status_mismatch"].ids == [1, 2]
    assert findings["provider_job_missing"].ids == [3]
    assert findings["provider_counts_mismatch"].ids == [4]

    # DB rows must remain untouched (read-only guarantee)
    repo = ProviderBatchRepository(database)
    assert [(j.job_id, j.status, j.succeeded_count, j.failed_count) for j in repo.list_job_states()] == [
        (1, "submitted", 0, 0),
        (2, "completed", 2, 0),
        (3, "running", 0, 0),
        (4, "completed", 5, 0),
        (5, "imported", 3, 0),
    ]


def test_provider_scope_enforces_500_job_upper_bound_before_querying_provider(database, tmp_path):
    with database() as session:
        session.add_all([_job(i, "submitted") for i in range(1, MAX_PROVIDER_CHECK_JOBS + 2)])
        session.commit()

    called = False

    def forbidden_fetcher(_job):
        nonlocal called
        called = True
        raise AssertionError("Provider API must not be called when jobs exceed 500")

    service = DbMaintenanceCheckService(
        ImageRepository(database),
        ProviderBatchRepository(database),
        path_resolver=lambda stored: tmp_path / stored,
        now=lambda: NOW,
        remote_status_fetcher=forbidden_fetcher,
    )
    with pytest.raises(ResultSetTooLargeError) as exc_info:
        service.check(["provider"])
    assert exc_info.value.matched == MAX_PROVIDER_CHECK_JOBS + 1
    assert exc_info.value.limit == MAX_PROVIDER_CHECK_JOBS
    assert called is False


def test_provider_scope_partial_failure_returns_partial_success(database, tmp_path):
    with database() as session:
        session.add_all([_job(1, "submitted"), _job(2, "running")])
        session.commit()

    def flaky_fetcher(job):
        if job.job_id == 1:
            return ProviderBatchStatus(provider_job_id="batch_1", provider_status="completed")
        raise ConnectionError("provider connection reset")

    service = DbMaintenanceCheckService(
        ImageRepository(database),
        ProviderBatchRepository(database),
        path_resolver=lambda stored: tmp_path / stored,
        now=lambda: NOW,
        remote_status_fetcher=flaky_fetcher,
    )
    report = service.check(["provider"])
    findings = _by_check(report)
    assert report.status == "partial_success"
    assert report.provider_queried is True and report.repaired is False
    assert findings["provider_status_mismatch"].ids == [1]


def test_provider_scope_raises_on_auth_error_or_total_failure(database, tmp_path):
    with database() as session:
        session.add_all([_job(1, "submitted"), _job(2, "running")])
        session.commit()

    auth_service = DbMaintenanceCheckService(
        ImageRepository(database),
        ProviderBatchRepository(database),
        path_resolver=lambda stored: tmp_path / stored,
        now=lambda: NOW,
        remote_status_fetcher=lambda _job: (_ for _ in ()).throw(APIKeyNotConfiguredError("openai")),
    )
    with pytest.raises(APIKeyNotConfiguredError):
        auth_service.check(["provider"])

    net_service = DbMaintenanceCheckService(
        ImageRepository(database),
        ProviderBatchRepository(database),
        path_resolver=lambda stored: tmp_path / stored,
        now=lambda: NOW,
        remote_status_fetcher=lambda _job: (_ for _ in ()).throw(ConnectionError("offline")),
    )
    with pytest.raises(ConnectionError):
        net_service.check(["provider"])
