"""ProjectManagementService ユニットテスト — CRUD 一式。"""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lorairo.public_api.exceptions import (
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    ProjectOperationError,
)
from lorairo.public_api.types import ProjectInfo
from lorairo.services.project_management_service import ProjectManagementService

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

    # ---------- list_projects: non-directory entries are skipped ----------

    def test_list_projects_skips_non_directory_entries(self, service: ProjectManagementService) -> None:
        """list_projects: ディレクトリではないエントリをスキップする (line 293)。"""
        service.projects_base_dir.mkdir(parents=True, exist_ok=True)
        # プロジェクトを1件作成
        service.create_project("real_project")
        # ベースディレクトリ内にファイルも置く
        (service.projects_base_dir / "not_a_dir.txt").write_text("content")

        projects = service.list_projects()

        assert len(projects) == 1
        assert projects[0].name == "real_project"

    # ---------- _find_project_directory: exact match path ----------

    def test_find_project_directory_returns_path_for_matching_project(
        self, service: ProjectManagementService
    ) -> None:
        """_find_project_directory: 名前が一致するディレクトリを返す (line 300-301)。"""
        info = service.create_project("find_me")
        result = service._find_project_directory("find_me")
        assert result == info.path

    def test_find_project_directory_returns_none_when_base_dir_missing(
        self, service: ProjectManagementService
    ) -> None:
        """_find_project_directory: ベースディレクトリ未存在 → None (line 283-284)。"""
        assert not service.projects_base_dir.exists()
        result = service._find_project_directory("any")
        assert result is None

    # ---------- _read_project_info: missing metadata file ----------

    def test_read_project_info_returns_none_when_metadata_missing(
        self, service: ProjectManagementService
    ) -> None:
        """_read_project_info: .lorairo-project が存在しない → None (lines 322-323)。"""
        # メタデータなしのディレクトリを直接作成
        project_dir = service.projects_base_dir / "naked_dir"
        project_dir.mkdir(parents=True, exist_ok=True)

        result = service._read_project_info(project_dir)
        assert result is None

    def test_read_project_info_handles_suffix_date_format(self, service: ProjectManagementService) -> None:
        """_read_project_info: created に _NNN サフィックスが付いた日付を正常パースする (lines 331-336)。"""
        # 通常の create_project を使い、後でメタデータを上書き
        info = service.create_project("suffix_test")
        metadata_file = info.path / ".lorairo-project"
        metadata = json.loads(metadata_file.read_text())
        # _NNN サフィックス付きの日付文字列にする
        metadata["created"] = "20250522_153045_1"
        metadata_file.write_text(json.dumps(metadata, indent=2))

        result = service._read_project_info(info.path)
        assert result is not None
        assert result.name == "suffix_test"

    def test_read_project_info_falls_back_to_now_for_unparseable_date(
        self, service: ProjectManagementService
    ) -> None:
        """_read_project_info: created が解析不能な場合は datetime.now() にフォールバック (line 337)。"""
        info = service.create_project("bad_date_project")
        metadata_file = info.path / ".lorairo-project"
        metadata = json.loads(metadata_file.read_text())
        metadata["created"] = "not-a-date-at-all"
        metadata_file.write_text(json.dumps(metadata, indent=2))

        result = service._read_project_info(info.path)
        assert result is not None
        assert result.name == "bad_date_project"

    def test_read_project_info_returns_none_on_exception(self, service: ProjectManagementService) -> None:
        """_read_project_info: 読み込み例外 → None (lines 353-358)。"""
        info = service.create_project("exception_project")
        metadata_file = info.path / ".lorairo-project"
        # 不正な JSON を書き込む
        metadata_file.write_text("{ invalid json }")

        result = service._read_project_info(info.path)
        assert result is None

    # ---------- create_project: exception wrapping ----------

    def test_create_project_wraps_unexpected_exception_as_project_operation_error(
        self, service: ProjectManagementService
    ) -> None:
        """create_project: _project_exists が例外 → ProjectOperationError に変換 (lines 129-131)。

        Path.mkdir は Python 3.13 で read-only のためパッチ不可。
        代わりに _project_exists を OSError を投げるようにモックして
        except Exception -> raise ProjectOperationError パスを通す。
        """

        from lorairo.public_api.exceptions import ProjectOperationError

        with patch.object(service, "_project_exists", side_effect=OSError("permission denied")):
            with pytest.raises(ProjectOperationError) as exc_info:
                service.create_project("will_fail")

        assert exc_info.value.operation == "作成"

    # ---------- get_project: second ProjectNotFoundError path ----------

    def test_get_project_raises_not_found_when_metadata_unreadable(
        self, service: ProjectManagementService
    ) -> None:
        """get_project: ディレクトリは存在するがメタデータが壊れている → ProjectNotFoundError (line 180)。"""
        info = service.create_project("corrupted_project")
        # メタデータを壊す
        (info.path / ".lorairo-project").write_text("{ invalid json }")

        with pytest.raises(ProjectNotFoundError) as exc_info:
            service.get_project("corrupted_project")

        assert exc_info.value.project_name == "corrupted_project"

    # ---------- delete_project: exception wrapping ----------

    def test_delete_project_wraps_unexpected_exception_as_project_operation_error(
        self, service: ProjectManagementService
    ) -> None:
        """delete_project: rmtree が OSError → ProjectOperationError (lines 214-216)。"""

        from lorairo.public_api.exceptions import ProjectOperationError

        service.create_project("to_fail_delete")

        with patch(
            "lorairo.services.project_management_service.shutil.rmtree", side_effect=OSError("busy")
        ):
            with pytest.raises(ProjectOperationError) as exc_info:
                service.delete_project("to_fail_delete")

        assert exc_info.value.operation == "削除"

    # ---------- update_project: exception wrapping ----------

    def test_update_project_wraps_unexpected_exception_as_project_operation_error(
        self, service: ProjectManagementService
    ) -> None:
        """update_project: json.dumps が例外 → ProjectOperationError (lines 253-255)。

        Path.write_text は Python 3.13 でインスタンスレベルのパッチ不可。
        代わりに json.dumps をモックして例外を起こす。
        """

        from lorairo.public_api.exceptions import ProjectOperationError

        service.create_project("to_fail_update")

        with patch(
            "lorairo.services.project_management_service.json.dumps", side_effect=OSError("disk full")
        ):
            with pytest.raises(ProjectOperationError) as exc_info:
                service.update_project("to_fail_update", "new desc")

        assert exc_info.value.operation == "更新"

    # ---------- Issue #1175: NOT_FOUND 候補提示 / WARNING スパム集約 ----------

    def test_get_project_not_found_includes_available_candidates(
        self, service: ProjectManagementService
    ) -> None:
        """get_project: NOT_FOUND エラーに利用可能なプロジェクト名候補と探索先診断が入る (Issue #1175/#1508)。"""
        service.create_project("alpha")
        service.create_project("beta")

        with pytest.raises(ProjectNotFoundError) as exc_info:
            service.get_project("missing")

        assert exc_info.value.available == ["alpha", "beta"]
        assert "alpha" in str(exc_info.value)
        assert str(service.projects_base_dir) in str(exc_info.value)
        # CLI 境界が JSON details に載せる属性
        assert exc_info.value.details["available_projects"] == ["alpha", "beta"]
        assert exc_info.value.details["projects_base_dir"] == str(service.projects_base_dir)
        assert isinstance(exc_info.value.details["config_path"], str)
        assert isinstance(exc_info.value.details["config_found"], bool)
        assert exc_info.value.hint is not None

    def test_get_project_not_found_suggests_close_names_case_insensitively(
        self, service: ProjectManagementService
    ) -> None:
        """get_project: 近い名前 (大文字小文字違い・綴り違い) を suggestions に入れ、無関係な名前は入れない (#1662)。"""
        service.create_project("Alpha")
        service.create_project("zzz-unrelated")

        with pytest.raises(ProjectNotFoundError) as exc_info:
            service.get_project("alpah")

        assert exc_info.value.suggestions == ["Alpha"]
        assert exc_info.value.folder_matched_project is None

    def test_get_project_not_found_with_folder_name_reports_matching_project(
        self, service: ProjectManagementService
    ) -> None:
        """get_project: フォルダ名 (またはそのパス) を渡すと、そのフォルダの name を folder_matched_project に入れる (#1662)。"""
        info = service.create_project("alpha")

        for given in (info.path.name, str(info.path)):
            with pytest.raises(ProjectNotFoundError) as exc_info:
                service.get_project(given)
            assert exc_info.value.folder_matched_project == "alpha"
            assert exc_info.value.suggestions == []

    def test_get_project_not_found_without_projects_has_plain_message(
        self, service: ProjectManagementService
    ) -> None:
        """get_project: 候補ゼロでも探索先・設定検出状況を details と hint に含める (Issue #1175/#1508)。"""
        with pytest.raises(ProjectNotFoundError) as exc_info:
            service.get_project("missing")

        assert exc_info.value.available == []
        assert exc_info.value.details["available_projects"] == []
        assert exc_info.value.details["projects_base_dir"] == str(service.projects_base_dir)
        assert isinstance(exc_info.value.details["config_path"], str)
        assert isinstance(exc_info.value.details["config_found"], bool)
        assert exc_info.value.hint is not None

    def test_get_project_not_found_reports_actual_default_config_not_unloaded_cwd_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--workspace/--config 未指定時は CWD の未読込 config ではなく実際の DEFAULT_CONFIG_PATH を報告する。"""
        from lorairo.utils.config import DEFAULT_CONFIG_PATH

        other_cwd = tmp_path / "other_cwd"
        (other_cwd / "config").mkdir(parents=True)
        unloaded_cwd_config = other_cwd / "config" / "lorairo.toml"
        unloaded_cwd_config.write_text('[directories]\ndatabase_base_dir = "unused"\n', encoding="utf-8")
        monkeypatch.chdir(other_cwd)

        svc = ProjectManagementService(projects_base_dir=tmp_path / "projects")
        with pytest.raises(ProjectNotFoundError) as exc_info:
            svc.get_project("missing")

        assert exc_info.value.details["config_path"] == str(DEFAULT_CONFIG_PATH)
        assert exc_info.value.details["config_path"] != str(unloaded_cwd_config)
        assert exc_info.value.details["config_found"] is DEFAULT_CONFIG_PATH.is_file()

    def test_list_projects_skips_metadata_less_dirs_without_per_dir_warning(
        self, service: ProjectManagementService
    ) -> None:
        """list_projects: メタデータなしディレクトリはスキップされ一覧に出ない (Issue #1175)。"""
        service.create_project("alpha")
        (service.projects_base_dir / "no_metadata_dir").mkdir()
        (service.projects_base_dir / "no_metadata_dir2").mkdir()

        projects = service.list_projects()

        assert [p.name for p in projects] == ["alpha"]


@pytest.mark.unit
@pytest.mark.parametrize("failure_point", ["base", "project", "dataset", "original", "metadata", "db"])
def test_create_failure_rolls_back_and_allows_retry(
    service: ProjectManagementService, monkeypatch: pytest.MonkeyPatch, failure_point: str
) -> None:
    """Every creation stage cleans up its own partial output, including partial writes."""
    original_mkdir = Path.mkdir
    original_write = Path.write_text
    original_touch = Path.touch

    def mkdir(path: Path, *args, **kwargs):
        fails = {
            "base": path == service.projects_base_dir,
            "project": path.parent == service.projects_base_dir,
            "dataset": path.name == "image_dataset",
            "original": path.name == "original_images",
        }
        if fails.get(failure_point, False):
            raise OSError("creation failed")
        return original_mkdir(path, *args, **kwargs)

    def write(path: Path, *args, **kwargs):
        if failure_point == "metadata" and path.name == ".lorairo-project.pending":
            original_write(path, "partial metadata")
            raise OSError("creation failed")
        return original_write(path, *args, **kwargs)

    def touch(path: Path, *args, **kwargs):
        if failure_point == "db" and path.name == "image_database.db":
            original_touch(path, *args, **kwargs)
            raise OSError("creation failed")
        return original_touch(path, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "mkdir", mkdir)
        patcher.setattr(Path, "write_text", write)
        patcher.setattr(Path, "touch", touch)
        with pytest.raises(ProjectOperationError) as caught:
            service.create_project("retry")
    assert isinstance(caught.value.__cause__, OSError)
    assert caught.value.details["original_error"] == "creation failed"
    assert caught.value.details["residual_paths"] == []
    assert not service.projects_base_dir.exists()
    info = service.create_project("retry")
    assert (info.path / "image_database.db").is_file()
    with pytest.raises(ProjectAlreadyExistsError):
        service.create_project("retry")


@pytest.mark.unit
def test_create_failure_preserves_existing_files_and_projects(
    service: ProjectManagementService, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = service.create_project("existing")
    image = existing.path / "image_dataset" / "original_images" / "keep.png"
    image.write_bytes(b"existing image")
    unrelated = service.projects_base_dir / "keep.txt"
    unrelated.write_text("keep")
    incomplete = service.projects_base_dir / "incomplete"
    incomplete.mkdir()
    (incomplete / ".lorairo-project").write_text('{"name": "old-incomplete"}')
    before = {str(p): p.read_bytes() for p in service.projects_base_dir.rglob("*") if p.is_file()}
    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "touch", Mock(side_effect=OSError("db failed")))
        with pytest.raises(ProjectOperationError):
            service.create_project("new")
        with pytest.raises(ProjectAlreadyExistsError):
            service.create_project("existing")
        with pytest.raises(ProjectAlreadyExistsError):
            service.create_project("old-incomplete")
    after = {str(p): p.read_bytes() for p in service.projects_base_dir.rglob("*") if p.is_file()}
    assert after == before
    assert service.create_project("new").path.is_dir()


@pytest.mark.unit
def test_create_collision_never_claims_existing_directory(
    service: ProjectManagementService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory appearing during mkdir belongs to the competing creator."""
    service.projects_base_dir.mkdir()
    original_mkdir = Path.mkdir
    collision = []

    def mkdir(path: Path, *args, **kwargs):
        if path.parent == service.projects_base_dir and not collision:
            original_mkdir(path)
            (path / "keep.txt").write_text("other creator")
            collision.append(path)
        return original_mkdir(path, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "mkdir", mkdir)
        patcher.setattr(Path, "touch", Mock(side_effect=OSError("db failed")))
        with pytest.raises(ProjectOperationError):
            service.create_project("race")
    assert list(service.projects_base_dir.iterdir()) == collision
    assert (collision[0] / "keep.txt").read_text() == "other creator"


@pytest.mark.unit
def test_create_cleanup_failure_preserves_original_error_and_recovery(
    service: ProjectManagementService, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.projects_base_dir.mkdir()
    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "touch", Mock(side_effect=OSError("db failed")))
        patcher.setattr(
            "lorairo.services.project_management_service.shutil.rmtree",
            Mock(side_effect=PermissionError("cleanup denied")),
        )
        with pytest.raises(ProjectOperationError) as caught:
            service.create_project("cleanup")
    error = caught.value
    assert str(error.__cause__) == "db failed"
    residual = next(service.projects_base_dir.iterdir())
    assert error.details["original_error"] == "db failed"
    assert error.details["residual_paths"] == [str(residual)]
    assert error.details["cleanup_errors"] == [{"path": str(residual), "error": "cleanup denied"}]
    assert "retry project create" in error.details["recovery"]
    assert "cleanup denied" in str(error)
    assert repr(str(residual)) in str(error)


@pytest.mark.unit
def test_create_failure_keeps_foreign_files_in_new_parent(
    service: ProjectManagementService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty-only rollback preserves files added to a shared parent during creation."""

    def fail_touch(path: Path, *args, **kwargs):
        (service.projects_base_dir / "foreign.txt").write_text("keep")
        raise OSError("db failed")

    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "touch", fail_touch)
        with pytest.raises(ProjectOperationError) as caught:
            service.create_project("retry")
    assert (service.projects_base_dir / "foreign.txt").read_text() == "keep"
    assert caught.value.details["residual_paths"] == [str(service.projects_base_dir)]
    assert caught.value.details["cleanup_errors"]
    assert service.create_project("retry").path.is_dir()


@pytest.mark.unit
def test_create_failure_removes_new_base_ancestors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = ProjectManagementService(tmp_path / "new" / "nested" / "projects")
    original_mkdir = Path.mkdir

    def mkdir(path: Path, *args, **kwargs):
        if path == service.projects_base_dir:
            raise OSError("mkdir failed")
        return original_mkdir(path, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "mkdir", mkdir)
        with pytest.raises(ProjectOperationError):
            service.create_project("retry")
    assert list(tmp_path.iterdir()) == []
    assert service.create_project("retry").path.is_dir()


@pytest.mark.unit
@pytest.mark.parametrize("failure_point", ["metadata_close", "db", "project_info", "publish"])
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_creation_publishes_only_complete_projects(
    service: ProjectManagementService,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
    cleanup_fails: bool,
) -> None:
    """Complete temporary JSON must remain undiscoverable after any pre-publication failure."""
    service.projects_base_dir.mkdir()
    original_write = Path.write_text
    original_touch = Path.touch
    original_replace = Path.replace

    def write(path: Path, *args, **kwargs):
        result = original_write(path, *args, **kwargs)
        if failure_point == "metadata_close" and path.name == ".lorairo-project.pending":
            raise OSError("metadata close failed")
        return result

    def touch(path: Path, *args, **kwargs):
        result = original_touch(path, *args, **kwargs)
        if failure_point == "db" and path.name == "image_database.db":
            raise OSError("db failed")
        return result

    def replace(path: Path, target: Path):
        assert service.list_projects() == []
        assert service._find_project_directory("retry") is None
        assert (path.parent / "image_database.db").is_file()
        assert (path.parent / "image_dataset" / "original_images").is_dir()
        if failure_point == "publish":
            raise OSError("publish failed")
        return original_replace(path, target)

    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "write_text", write)
        patcher.setattr(Path, "touch", touch)
        patcher.setattr(Path, "replace", replace)
        if failure_point == "project_info":
            patcher.setattr(
                "lorairo.services.project_management_service.ProjectInfo",
                Mock(side_effect=ValueError("result construction failed")),
            )
        if cleanup_fails:
            patcher.setattr(
                "lorairo.services.project_management_service.shutil.rmtree",
                Mock(side_effect=PermissionError("cleanup denied")),
            )
        with pytest.raises(ProjectOperationError) as caught:
            service.create_project("retry")
    assert caught.value.__cause__ is not None
    assert service.list_projects() == []
    with pytest.raises(ProjectNotFoundError):
        service.get_project("retry")
    assert not list(service.projects_base_dir.rglob(".lorairo-project"))
    residuals = list(service.projects_base_dir.iterdir())
    assert bool(residuals) == cleanup_fails
    if cleanup_fails:
        assert caught.value.details["residual_paths"] == [str(residuals[0])]
        assert caught.value.details["cleanup_errors"][0]["error"] == "cleanup denied"
        assert json.loads((residuals[0] / ".lorairo-project.pending").read_text())["name"] == "retry"
    info = service.create_project("retry")
    assert service.get_project("retry").path == info.path
    assert [project.name for project in service.list_projects()] == ["retry"]
    assert not (info.path / ".lorairo-project.pending").exists()
    assert all(path.exists() for path in residuals)


@pytest.mark.unit
@pytest.mark.parametrize("existing_file", [False, True])
def test_create_preserves_preexisting_timestamp_destination(
    service: ProjectManagementService, existing_file: bool
) -> None:
    """The exact generated destination may already be a file or an unrelated directory."""
    from datetime import datetime

    now = datetime(2026, 9, 6, 10, 0, 0)
    service.projects_base_dir.mkdir()
    existing = service.projects_base_dir / "same_20260906_100000"
    if existing_file:
        existing.write_bytes(b"keep")
        protected = existing
    else:
        existing.mkdir()
        protected = existing / "keep.txt"
        protected.write_bytes(b"keep")
    with patch("lorairo.services.project_management_service.datetime") as clock:
        clock.now.return_value = now
        info = service.create_project("same")
    assert info.path.name == "same_20260906_100000_1"
    assert protected.read_bytes() == b"keep"


@pytest.mark.unit
class TestEnsureProjectMetadata:
    """ensure_project_metadata: GUI が作成・オープンしたフォルダのメタデータ補完 (#1659)。"""

    def test_writes_metadata_with_folder_name_for_folder_without_metadata(
        self, service: ProjectManagementService
    ) -> None:
        """メタデータの無いフォルダにフォルダ名を name とする .lorairo-project を書き、一覧に出る。"""
        project_dir = service.projects_base_dir / "otogi-lora_20261126_001"
        project_dir.mkdir(parents=True)

        written = service.ensure_project_metadata(project_dir)

        assert written is True
        metadata = json.loads((project_dir / ".lorairo-project").read_text(encoding="utf-8"))
        assert metadata["name"] == "otogi-lora_20261126_001"
        assert metadata["description"] == ""
        assert metadata["created"]
        assert not (project_dir / ".lorairo-project.pending").exists()
        listed = service.list_projects()
        assert [p.name for p in listed] == ["otogi-lora_20261126_001"]
        assert service.get_project("otogi-lora_20261126_001").path == project_dir

    def test_does_not_overwrite_existing_metadata(self, service: ProjectManagementService) -> None:
        """CLI が作った既存メタデータの name は変えない。"""
        info = service.create_project("cli_project", description="from cli")
        before = (info.path / ".lorairo-project").read_text(encoding="utf-8")

        written = service.ensure_project_metadata(info.path)

        assert written is False
        assert (info.path / ".lorairo-project").read_text(encoding="utf-8") == before
        assert [p.name for p in service.list_projects()] == ["cli_project"]

    def test_does_not_overwrite_unreadable_metadata(self, service: ProjectManagementService) -> None:
        """壊れたメタデータも上書きしない (ユーザーのファイルを勝手に消さない)。"""
        project_dir = service.projects_base_dir / "broken_20261126_001"
        project_dir.mkdir(parents=True)
        (project_dir / ".lorairo-project").write_text("not json", encoding="utf-8")

        assert service.ensure_project_metadata(project_dir) is False
        assert (project_dir / ".lorairo-project").read_text(encoding="utf-8") == "not json"


class TestProjectMetadataEncoding:
    """メタデータの読み書きをロケールに依存させない (#1659 PR #1664 Codex P2)。"""

    def test_metadata_round_trips_non_locale_characters_under_cp932_locale(
        self, service: ProjectManagementService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """既定のエンコーディングが cp932 の環境でも、絵文字を含むフォルダ名を書いて一覧に出せる。"""
        original_write = Path.write_text
        original_read = Path.read_text

        def write_with_locale_default(
            self: Path,
            data: str,
            encoding: str | None = None,
            errors: str | None = None,
            newline: str | None = None,
        ) -> int:
            # encoding 未指定時は Windows (UTF-8 モード無効) のロケール既定 cp932 を模擬する
            return original_write(self, data, encoding or "cp932", errors, newline)

        def read_with_locale_default(
            self: Path, encoding: str | None = None, errors: str | None = None, newline: str | None = None
        ) -> str:
            return original_read(self, encoding or "cp932", errors, newline)

        monkeypatch.setattr(Path, "write_text", write_with_locale_default)
        monkeypatch.setattr(Path, "read_text", read_with_locale_default)
        project_dir = service.projects_base_dir / "素材🎨_20261128_001"
        project_dir.mkdir(parents=True)

        assert service.ensure_project_metadata(project_dir) is True

        raw = (project_dir / ".lorairo-project").read_bytes()
        assert json.loads(raw.decode("utf-8"))["name"] == "素材🎨_20261128_001"
        assert [p.name for p in service.list_projects()] == ["素材🎨_20261128_001"]

    def test_reads_legacy_metadata_written_in_locale_encoding(
        self, service: ProjectManagementService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """以前 Windows のロケール既定 (cp932) で書かれたメタデータも一覧と名前検索で読める。"""
        monkeypatch.setattr(
            "lorairo.services.project_management_service.locale.getpreferredencoding",
            lambda do_setlocale=True: "cp932",
        )
        project_dir = service.projects_base_dir / "素材_20260101_120000"
        project_dir.mkdir(parents=True)
        legacy = {"name": "素材", "created": "20260101_120000", "description": "日本語の説明"}
        (project_dir / ".lorairo-project").write_bytes(
            json.dumps(legacy, ensure_ascii=False).encode("cp932")
        )

        listed = service.list_projects()

        assert [(p.name, p.description) for p in listed] == [("素材", "日本語の説明")]
        assert service.get_project("素材").path == project_dir
