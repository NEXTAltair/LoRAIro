"""Always-read-only tag health report for an existing compatible project."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from lorairo.services.tag_health_service import (
    TagHealthReport,
    TagHealthService,
    validate_health_options,
)


def report_tag_health(
    project_name: str, expected_tags: Sequence[str] = (), *, limit: int = 100
) -> TagHealthReport:
    """Inspect accepted tags without correction, migration, tag DB setup, or inference.

    Expected tags apply to every image only when explicitly supplied. Comparison
    uses format cleanup and casefold, not semantic aliases. Returned rows and each
    missing-ID sample are capped by ``limit``; counts cover the entire project.
    """
    validate_health_options(expected_tags, limit)
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
        service = TagHealthService(container.image_repository.session_factory)
        return service.report(expected_tags, limit=limit)
