"""ProjectManagementService ユニットテスト — 旧ディレクトリ移行案内ログ (シナリオH) + CRUD 一式。"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lorairo.api.exceptions import (
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
)
from lorairo.api.types import ProjectInfo
from lorairo.services.project_management_service import ProjectManagementService


@pytest.mark.unit
def test_old_projects_dir_detected_logs_info(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """旧 ~/.lorairo/projects/ が存在する場合に INFO ログを出力する。"""
    # 旧ディレクトリを作成
    old_dir = tmp_path / ".lorairo" / "projects"
    old_dir.mkdir(parents=True)

    # Path.home() を差し替え
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    # get_config をモック
    def mock_get_config() -> MagicMock:
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = {"database_base_dir": str(tmp_path / "lorairo_data")}
        return mock_cfg

    monkeypatch.setattr("lorairo.services.project_management_service.get_config", mock_get_config)

    with patch("lorairo.services.project_management_service.logger") as mock_logger:
        ProjectManagementService()

    assert mock_logger.info.call_count == 1
    call_args = mock_logger.info.call_args[0][0]
    assert "旧プロジェクトディレクトリが検出されました" in call_args


@pytest.mark.unit
def test_no_old_projects_dir_no_info_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """旧 ~/.lorairo/projects/ が存在しない場合に INFO ログを出力しない。"""
    # .lorairo/projects は作らない

    # Path.home() を差し替え
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    # get_config をモック
    def mock_get_config() -> MagicMock:
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = {"database_base_dir": str(tmp_path / "lorairo_data")}
        return mock_cfg

    monkeypatch.setattr("lorairo.services.project_management_service.get_config", mock_get_config)

    with patch("lorairo.services.project_management_service.logger") as mock_logger:
        ProjectManagementService()

    mock_logger.info.assert_not_called()


# ==================== CRUD ユニットテスト (Issue #369) ====================


@pytest.fixture
def service(tmp_path: Path) -> ProjectManagementService:
    """projects_base_dir を tmp_path に DI した Service インスタンスを返す。

    `get_config()` フォールバック経路を回避するため、
    `projects_base_dir` を明示的に渡す。
    """
    return ProjectManagementService(projects_base_dir=tmp_path / "projects")


@pytest.mark.unit
class TestProjectCrud:
    """ProjectManagementService の CRUD 振る舞いを検証するテストクラス。"""

    # ---------- create_project ----------

    def test_create_project_with_new_name_creates_directory_structure(
        self, service: ProjectManagementService
    ) -> None:
        """create_project: 新規プロジェクト作成でディレクトリ構造とメタデータが揃う。"""
        info = service.create_project("alpha", description="first project")

        # 戻り値の検証
        assert isinstance(info, ProjectInfo)
        assert info.name == "alpha"
        assert info.description == "first project"
        assert info.image_count == 0
        assert info.path.exists()
        assert info.path.is_dir()
        assert info.path.parent == service.projects_base_dir

        # ディレクトリ構造の検証
        assert (info.path / "image_dataset").is_dir()
        assert (info.path / "image_dataset" / "original_images").is_dir()
        assert (info.path / "image_database.db").is_file()

        # メタデータファイルの検証
        metadata_file = info.path / ".lorairo-project"
        assert metadata_file.is_file()
        metadata = json.loads(metadata_file.read_text())
        assert metadata["name"] == "alpha"
        assert metadata["description"] == "first project"
        assert "created" in metadata

    def test_create_project_with_empty_description_returns_none_description(
        self, service: ProjectManagementService
    ) -> None:
        """create_project: description 省略時は ProjectInfo.description が None になる。"""
        info = service.create_project("beta")

        assert info.description is None

        # メタデータ JSON 側は空文字列で永続化される
        metadata = json.loads((info.path / ".lorairo-project").read_text())
        assert metadata["description"] == ""

    def test_create_project_with_duplicate_name_raises_project_already_exists_error(
        self, service: ProjectManagementService
    ) -> None:
        """create_project: 同名プロジェクト二度作成で ProjectAlreadyExistsError。"""
        service.create_project("gamma")

        with pytest.raises(ProjectAlreadyExistsError) as exc_info:
            service.create_project("gamma")

        assert exc_info.value.project_name == "gamma"

    # ---------- delete_project ----------

    def test_delete_project_with_existing_name_removes_directory_completely(
        self, service: ProjectManagementService
    ) -> None:
        """delete_project: ディレクトリと中身が完全削除される。"""
        info = service.create_project("delta")
        project_path = info.path
        assert project_path.exists()

        service.delete_project("delta")

        assert not project_path.exists()
        # ベースディレクトリ自体は残る
        assert service.projects_base_dir.exists()

    def test_delete_project_with_missing_name_raises_project_not_found_error(
        self, service: ProjectManagementService
    ) -> None:
        """delete_project: 存在しないプロジェクト名で ProjectNotFoundError。"""
        # ベースディレクトリは作成するが、プロジェクトは作らない
        service.projects_base_dir.mkdir(parents=True, exist_ok=True)

        with pytest.raises(ProjectNotFoundError) as exc_info:
            service.delete_project("nonexistent")

        assert exc_info.value.project_name == "nonexistent"

    # ---------- list_projects ----------

    def test_list_projects_with_multiple_projects_returns_all_project_infos(
        self, service: ProjectManagementService
    ) -> None:
        """list_projects: 複数プロジェクト作成で全件取得される。"""
        service.create_project("epsilon")
        service.create_project("zeta")
        service.create_project("eta")

        projects = service.list_projects()

        assert len(projects) == 3
        names = {p.name for p in projects}
        assert names == {"epsilon", "zeta", "eta"}
        for project in projects:
            assert isinstance(project, ProjectInfo)
            assert project.path.is_dir()

    def test_list_projects_with_empty_base_dir_returns_empty_list(
        self, service: ProjectManagementService
    ) -> None:
        """list_projects: ベースディレクトリが空（未作成）でも空リストを返す。"""
        # ベースディレクトリは作成しない
        assert not service.projects_base_dir.exists()

        projects = service.list_projects()

        assert projects == []

    def test_list_projects_with_existing_but_empty_base_dir_returns_empty_list(
        self, service: ProjectManagementService
    ) -> None:
        """list_projects: ベースディレクトリは存在するが中身が空でも空リストを返す。"""
        service.projects_base_dir.mkdir(parents=True, exist_ok=True)

        projects = service.list_projects()

        assert projects == []

    # ---------- get_project ----------

    def test_get_project_with_existing_name_returns_project_info(
        self, service: ProjectManagementService
    ) -> None:
        """get_project: 既存プロジェクト名から ProjectInfo を返す。"""
        created = service.create_project("theta", description="theta desc")

        info = service.get_project("theta")

        assert isinstance(info, ProjectInfo)
        assert info.name == "theta"
        assert info.description == "theta desc"
        assert info.path == created.path
        assert info.image_count == 0

    def test_get_project_with_missing_name_raises_project_not_found_error(
        self, service: ProjectManagementService
    ) -> None:
        """get_project: 存在しないプロジェクト名で ProjectNotFoundError。"""
        service.projects_base_dir.mkdir(parents=True, exist_ok=True)

        with pytest.raises(ProjectNotFoundError) as exc_info:
            service.get_project("nonexistent")

        assert exc_info.value.project_name == "nonexistent"

    # ---------- update_project ----------

    def test_update_project_with_new_description_persists_to_metadata(
        self, service: ProjectManagementService
    ) -> None:
        """update_project: description フィールドが .lorairo-project に永続化される。"""
        created = service.create_project("iota", description="original")

        updated = service.update_project("iota", "updated description")

        # 戻り値検証
        assert isinstance(updated, ProjectInfo)
        assert updated.name == "iota"
        assert updated.description == "updated description"

        # 永続化検証 (ファイル直読)
        metadata = json.loads((created.path / ".lorairo-project").read_text())
        assert metadata["description"] == "updated description"
        # name など他フィールドが破壊されていない
        assert metadata["name"] == "iota"
        assert "created" in metadata

    def test_update_project_with_missing_name_raises_project_not_found_error(
        self, service: ProjectManagementService
    ) -> None:
        """update_project: 存在しないプロジェクト名で ProjectNotFoundError。"""
        service.projects_base_dir.mkdir(parents=True, exist_ok=True)

        with pytest.raises(ProjectNotFoundError) as exc_info:
            service.update_project("nonexistent", "anything")

        assert exc_info.value.project_name == "nonexistent"
