"""Project API テスト。"""

from pathlib import Path

import pytest

from lorairo.api.exceptions import (
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
)
from lorairo.api.project import (
    create_project,
    delete_project,
    get_project,
    list_projects,
    update_project,
)
from lorairo.api.types import ProjectCreateRequest, ProjectInfo
from lorairo.services.project_management_service import ProjectManagementService
from lorairo.services.service_container import ServiceContainer


@pytest.fixture
def mock_projects_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """ProjectManagementService のディレクトリをモック。

    Args:
        tmp_path: 一時ディレクトリ
        monkeypatch: pytest monkeypatch フィクスチャ

    Returns:
        Path: モック後のプロジェクトディレクトリ
    """
    mock_dir = tmp_path / "projects"
    mock_dir.mkdir()

    container = ServiceContainer()
    container._project_management_service = None

    original_init = ProjectManagementService.__init__

    def patched_init(self: ProjectManagementService, projects_base_dir: Path | None = None) -> None:
        original_init(self, projects_base_dir=mock_dir)

    monkeypatch.setattr(ProjectManagementService, "__init__", patched_init)

    return mock_dir


@pytest.mark.unit
class TestCreateProject:
    """create_project API テスト。"""

    def test_success(self, mock_projects_dir: Path) -> None:
        """正常にプロジェクトを作成できる。"""
        request = ProjectCreateRequest(name="test-project", description="Test")
        result = create_project(request)

        assert isinstance(result, ProjectInfo)
        assert result.name == "test-project"
        assert result.description == "Test"
        assert result.image_count == 0
        assert result.path.exists()

    def test_without_description(self, mock_projects_dir: Path) -> None:
        """説明なしでもプロジェクト作成可能。"""
        request = ProjectCreateRequest(name="no-desc")
        result = create_project(request)

        assert result.name == "no-desc"

    def test_duplicate_raises_error(self, mock_projects_dir: Path) -> None:
        """同名プロジェクト作成で例外。"""
        request = ProjectCreateRequest(name="duplicate")
        create_project(request)

        with pytest.raises(ProjectAlreadyExistsError):
            create_project(request)

    def test_creates_directory_structure(self, mock_projects_dir: Path) -> None:
        """ディレクトリ構造が正しく作成される。"""
        request = ProjectCreateRequest(name="structure-test")
        result = create_project(request)

        assert (result.path / ".lorairo-project").exists()
        assert (result.path / "image_dataset").is_dir()
        assert (result.path / "image_dataset" / "original_images").is_dir()
        assert (result.path / "image_database.db").exists()


@pytest.mark.unit
class TestListProjects:
    """list_projects API テスト。"""

    def test_empty(self, mock_projects_dir: Path) -> None:
        """プロジェクト0件で空リスト。"""
        result = list_projects()
        assert result == []

    def test_multiple_projects(self, mock_projects_dir: Path) -> None:
        """複数プロジェクトが一覧に含まれる。"""
        for name in ["proj-a", "proj-b", "proj-c"]:
            create_project(ProjectCreateRequest(name=name))

        result = list_projects()
        names = [p.name for p in result]

        assert len(result) == 3
        assert "proj-a" in names
        assert "proj-b" in names
        assert "proj-c" in names


@pytest.mark.unit
class TestGetProject:
    """get_project API テスト。"""

    def test_success(self, mock_projects_dir: Path) -> None:
        """存在するプロジェクトを取得。"""
        create_project(ProjectCreateRequest(name="get-test"))
        result = get_project("get-test")

        assert result.name == "get-test"
        assert isinstance(result, ProjectInfo)

    def test_not_found(self, mock_projects_dir: Path) -> None:
        """存在しないプロジェクトで例外。"""
        with pytest.raises(ProjectNotFoundError):
            get_project("nonexistent")


@pytest.mark.unit
class TestDeleteProject:
    """delete_project API テスト。"""

    def test_success(self, mock_projects_dir: Path) -> None:
        """プロジェクト削除が成功。"""
        info = create_project(ProjectCreateRequest(name="delete-test"))
        assert info.path.exists()

        delete_project("delete-test")

        with pytest.raises(ProjectNotFoundError):
            get_project("delete-test")

    def test_not_found(self, mock_projects_dir: Path) -> None:
        """存在しないプロジェクト削除で例外。"""
        with pytest.raises(ProjectNotFoundError):
            delete_project("nonexistent")


@pytest.mark.unit
class TestUpdateProject:
    """update_project API テスト。"""

    def test_success(self, mock_projects_dir: Path) -> None:
        """プロジェクト更新が成功。"""
        create_project(ProjectCreateRequest(name="update-test", description="old"))
        result = update_project("update-test", "new description")

        assert result.description == "new description"

    def test_not_found(self, mock_projects_dir: Path) -> None:
        """存在しないプロジェクト更新で例外。"""
        with pytest.raises(ProjectNotFoundError):
            update_project("nonexistent", "desc")


@pytest.mark.unit
class TestProjectCreateRequest:
    """ProjectCreateRequest バリデーションテスト。"""

    def test_valid_name(self) -> None:
        """有効な名前でバリデーション通過。"""
        req = ProjectCreateRequest(name="valid-name_123")
        assert req.name == "valid-name_123"

    def test_name_too_long(self) -> None:
        """65文字以上の名前で例外。"""
        with pytest.raises(ValueError):
            ProjectCreateRequest(name="a" * 65)

    def test_max_length_name(self) -> None:
        """64文字の名前は有効。"""
        req = ProjectCreateRequest(name="a" * 64)
        assert len(req.name) == 64

    def test_invalid_characters(self) -> None:
        """無効な文字を含む名前で例外。"""
        with pytest.raises(ValueError):
            ProjectCreateRequest(name="invalid name!")
