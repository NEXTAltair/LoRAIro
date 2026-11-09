"""Always-read-only DB maintenance checks for an existing compatible project (ADR 0099)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from lorairo.services.db_maintenance_check_service import (
    DEFAULT_SAMPLE_LIMIT,
    DEFAULT_SCOPES,
    DbMaintenanceCheckService,
    MaintenanceReport,
    validate_check_options,
)


def check_database(
    project_name: str,
    scopes: Sequence[str] = DEFAULT_SCOPES,
    *,
    limit: int = DEFAULT_SAMPLE_LIMIT,
) -> MaintenanceReport:
    """Report DB/file/provider inconsistencies without repair or migration.

    Default scopes (`batch`, `files`) do not call any provider API. When `provider`
    is included in `scopes`, remote batch status is queried in read-only mode.
    Counts cover the whole project; each check returns at most ``limit`` ascending IDs.
    """
    validated = validate_check_options(scopes, limit)
    from lorairo.database.access_policy import read_only_scope
    from lorairo.database.db_core import resolve_stored_path
    from lorairo.database.repository.image import ImageRepository
    from lorairo.database.repository.provider_batch import ProviderBatchRepository
    from lorairo.services.service_container import service_container_scope
    from lorairo.utils.config import (
        DEFAULT_CONFIG_PATH,
        RuntimeConfiguration,
        get_config,
        get_runtime_configuration,
        runtime_configuration_scope,
    )

    configuration = get_runtime_configuration() or RuntimeConfiguration(
        Path.cwd(), DEFAULT_CONFIG_PATH, get_config()
    )
    with (
        runtime_configuration_scope(configuration),
        read_only_scope(),
        service_container_scope() as container,
    ):
        container.set_active_project(project_name)
        session_factory = container.image_repository.session_factory
        remote_fetcher = (
            (lambda job: container.provider_batch_workflow_service.fetch_remote_status_readonly(job))
            if "provider" in validated
            else None
        )
        service = DbMaintenanceCheckService(
            ImageRepository(session_factory),
            ProviderBatchRepository(session_factory),
            path_resolver=resolve_stored_path,
            remote_status_fetcher=remote_fetcher,
        )
        return service.check(validated, limit=limit)
