"""Always-read-only duplicate candidates for an existing compatible project."""

from __future__ import annotations

from pathlib import Path

from lorairo.services.duplicate_report_service import (
    DEFAULT_MAX_DISTANCE,
    DuplicateReport,
    DuplicateReportService,
    validate_duplicate_options,
)


def report_duplicates(
    project_name: str, *, max_distance: int = DEFAULT_MAX_DISTANCE, limit: int = 100
) -> DuplicateReport:
    """Report connected candidates using saved hashes; never prepare DBs or open images."""
    validate_duplicate_options(max_distance, limit)
    from lorairo.database.access_policy import read_only_scope
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
        service = DuplicateReportService(container.image_repository.session_factory)
        return service.report(max_distance=max_distance, limit=limit)
