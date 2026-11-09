"""ServiceContainer の SQLAlchemy Engine 明示破棄テスト (#1498)。"""

from __future__ import annotations

import tomllib
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_core import create_project_session_factory
from lorairo.database.repository.image import ImageRepository
from lorairo.services.project_management_service import ProjectManagementService
from lorairo.services.service_container import ServiceContainer, service_container_scope


@pytest.mark.unit
def test_reset_for_testing_disposes_session_factory_bound_engine() -> None:
    """ServiceContainer.reset_for_testing() が session_factory に紐づく Engine を dispose する。"""
    mock_engine = MagicMock()
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=mock_engine)

    container = ServiceContainer()
    container._image_repository = ImageRepository(session_factory=session_factory)

    ServiceContainer.reset_for_testing()

    mock_engine.dispose.assert_called_once_with()
    assert ServiceContainer._instance is None


@pytest.mark.unit
def test_reset_for_testing_deduplicates_shared_engine_across_repo_and_manager() -> None:
    """image_repository と db_manager が同一 Engine を共有していても dispose は 1 回だけ呼ぶ。"""
    mock_engine = MagicMock()
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=mock_engine)

    container = ServiceContainer()
    container._image_repository = ImageRepository(session_factory=session_factory)
    _ = container.db_manager

    ServiceContainer.reset_for_testing()

    mock_engine.dispose.assert_called_once_with()


@pytest.mark.unit
def test_set_active_project_disposes_previous_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """set_active_project 再呼び出し時に旧 Engine が dispose されてリークしない。"""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    original_init = ProjectManagementService.__init__

    def patched_init(self: ProjectManagementService, projects_base_dir: Path | None = None) -> None:
        original_init(self, projects_base_dir=projects_dir)

    monkeypatch.setattr(ProjectManagementService, "__init__", patched_init)

    container = ServiceContainer()
    container.project_management_service.create_project("proj-a")
    container.set_active_project("proj-a")

    first_repo = container._image_repository
    assert first_repo is not None
    first_engine = first_repo.session_factory.kw["bind"]  # type: ignore[attr-defined]
    dispose_spy = MagicMock(wraps=first_engine.dispose)
    monkeypatch.setattr(first_engine, "dispose", dispose_spy)

    # CLI images register 経路と同様に再度 set_active_project が呼ばれた場合を検証
    container.set_active_project("proj-a")

    dispose_spy.assert_called_once_with()


@pytest.mark.unit
def test_service_container_scope_disposes_engine_on_exit(tmp_path: Path) -> None:
    """service_container_scope 終了時にスコープ内で初期化された Engine を dispose する。"""
    db_path = tmp_path / "scoped_project" / "image_database.db"
    session_factory = create_project_session_factory(db_path)
    engine = session_factory.kw["bind"]
    dispose_spy = MagicMock(wraps=engine.dispose)
    engine.dispose = dispose_spy  # type: ignore[method-assign]

    with service_container_scope() as scoped:
        scoped._image_repository = ImageRepository(session_factory=session_factory)

    dispose_spy.assert_called_once_with()


@pytest.mark.unit
def test_pyproject_configures_faulthandler_timeout() -> None:
    """pyproject.toml に faulthandler_timeout = 60 が設定されている (#1498)。"""
    pyproject_path = Path(__file__).resolve().parents[3] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    pytest_opts = data["tool"]["pytest"]["ini_options"]
    assert pytest_opts.get("faulthandler_timeout") == 60
