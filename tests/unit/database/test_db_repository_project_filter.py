"""ISSUE #175: Project DB 正規化 Phase C — _apply_project_filter() 本実装テスト。"""

import uuid
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from lorairo.database.filter_criteria import ImageFilterCriteria

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_image(session_factory, project_id: int | None = None):
    """テスト用 Image を1件作成して session に追加。"""
    from lorairo.database.schema import Image

    with session_factory() as session:
        img = Image(
            uuid=str(uuid.uuid4()),
            phash=f"aa{uuid.uuid4().hex[:10]}",
            original_image_path=f"/tmp/{uuid.uuid4().hex}.png",
            stored_image_path=f"/tmp/{uuid.uuid4().hex}.png",
            width=100,
            height=100,
            format="PNG",
            extension="png",
            project_id=project_id,
        )
        session.add(img)
        session.commit()
        return img.id


@pytest.fixture
def memory_session_factory():
    """in-memory SQLite セッションファクトリ（schema 全テーブル）。"""
    from lorairo.database.schema import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine)


# ---------------------------------------------------------------------------
# ImageFilterCriteria — project フィールドテスト（ISSUE #174 分、引き続き有効）
# ---------------------------------------------------------------------------


class TestImageFilterCriteriaProjectFields:
    """ImageFilterCriteria のプロジェクトフィールドを検証。"""

    def test_construct_with_project_name(self):
        criteria = ImageFilterCriteria(project_name="my_project")
        assert criteria.project_name == "my_project"

    def test_construct_with_project_id(self):
        criteria = ImageFilterCriteria(project_id=42)
        assert criteria.project_id == 42

    def test_default_values_are_none(self):
        criteria = ImageFilterCriteria()
        assert criteria.project_name is None
        assert criteria.project_id is None

    def test_from_kwargs_with_project_name(self):
        criteria = ImageFilterCriteria.from_kwargs(project_name="foo")
        assert criteria.project_name == "foo"

    def test_from_kwargs_with_project_id(self):
        criteria = ImageFilterCriteria.from_kwargs(project_id=7)
        assert criteria.project_id == 7

    def test_from_kwargs_combined_with_tags(self):
        criteria = ImageFilterCriteria.from_kwargs(project_name="foo", tags=["landscape", "anime"])
        assert criteria.project_name == "foo"
        assert criteria.tags == ["landscape", "anime"]

    def test_to_dict_includes_project_fields(self):
        criteria = ImageFilterCriteria(project_name="bar", project_id=99)
        result = criteria.to_dict()
        assert "project_name" in result
        assert result["project_name"] == "bar"
        assert "project_id" in result
        assert result["project_id"] == 99

    def test_to_dict_none_by_default(self):
        criteria = ImageFilterCriteria()
        result = criteria.to_dict()
        assert result["project_name"] is None
        assert result["project_id"] is None


# ---------------------------------------------------------------------------
# _apply_project_filter() — Phase C 本実装テスト
# ---------------------------------------------------------------------------


class TestApplyProjectFilter:
    """_apply_project_filter() の基本動作テスト。"""

    @pytest.fixture
    def repository(self):
        from lorairo.database.db_repository import ImageRepository

        return ImageRepository(session_factory=Mock())

    def test_apply_project_filter_returns_same_query_when_none(self, repository):
        """project_name/project_id ともに None の場合、クエリを変更しない。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        result = repository._apply_project_filter(base_query, None, None)
        assert result == base_query


class TestApplyProjectFilterPhaseC:
    """Phase C: _apply_project_filter() が実際にクエリを変更することを検証。"""

    @pytest.fixture
    def repository(self):
        from lorairo.database.db_repository import ImageRepository

        return ImageRepository(session_factory=Mock())

    def test_apply_project_filter_by_id_modifies_query(self, repository):
        """project_id 指定時にクエリが変更される。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        result = repository._apply_project_filter(base_query, None, 42)
        assert result != base_query

    def test_apply_project_filter_by_name_modifies_query(self, repository):
        """project_name 指定時にクエリが変更される。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        result = repository._apply_project_filter(base_query, "my_project", None)
        assert result != base_query

    def test_apply_project_filter_project_id_takes_priority(self, repository):
        """project_id と project_name 両方指定時は project_id フィルタのみ適用。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        result_id_only = repository._apply_project_filter(base_query, None, 42)
        result_both = repository._apply_project_filter(base_query, "foo", 42)
        assert str(result_id_only) == str(result_both)

    def test_no_warning_logged_for_project_id(self, repository):
        """Phase C 完了後は project_id 指定で警告を出さない。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        with patch("lorairo.database.db_repository.logger") as mock_logger:
            repository._apply_project_filter(base_query, None, 42)
        mock_logger.warning.assert_not_called()

    def test_no_warning_logged_for_project_name(self, repository):
        """Phase C 完了後は project_name 指定で警告を出さない。"""
        from lorairo.database.schema import Image

        base_query = select(Image.id)
        with patch("lorairo.database.db_repository.logger") as mock_logger:
            repository._apply_project_filter(base_query, "foo", None)
        mock_logger.warning.assert_not_called()


# ---------------------------------------------------------------------------
# ensure_project()
# ---------------------------------------------------------------------------


class TestEnsureProject:
    """ensure_project() メソッドのテスト（in-memory SQLite）。"""

    def test_ensure_project_creates_new(self, memory_session_factory):
        """新規プロジェクトが作成され正の ID が返る。"""
        from lorairo.database.db_repository import ImageRepository

        repo = ImageRepository(session_factory=memory_session_factory)
        project_id = repo.ensure_project("test_project", Path("/tmp/test"))
        assert isinstance(project_id, int)
        assert project_id > 0

    def test_ensure_project_returns_same_id_on_duplicate(self, memory_session_factory):
        """同名で2回呼んでも同じ ID が返る（upsert 動作）。"""
        from lorairo.database.db_repository import ImageRepository

        repo = ImageRepository(session_factory=memory_session_factory)
        id1 = repo.ensure_project("test_project", Path("/tmp/test"))
        id2 = repo.ensure_project("test_project", Path("/tmp/test"))
        assert id1 == id2

    def test_ensure_project_different_names_get_different_ids(self, memory_session_factory):
        """異なる名前では異なる ID が割り当てられる。"""
        from lorairo.database.db_repository import ImageRepository

        repo = ImageRepository(session_factory=memory_session_factory)
        id_a = repo.ensure_project("project_a", Path("/tmp/a"))
        id_b = repo.ensure_project("project_b", Path("/tmp/b"))
        assert id_a != id_b

    def test_ensure_project_updates_path_on_change(self, memory_session_factory):
        """同名でパスが変わった場合、パスが更新される。"""
        from lorairo.database.db_repository import ImageRepository
        from lorairo.database.schema import Project

        repo = ImageRepository(session_factory=memory_session_factory)
        project_id = repo.ensure_project("proj", Path("/tmp/old"))
        repo.ensure_project("proj", Path("/tmp/new"))

        with memory_session_factory() as session:
            project = session.execute(select(Project).where(Project.id == project_id)).scalar_one()
            assert project.path == str(Path("/tmp/new"))


# ---------------------------------------------------------------------------
# get_image_ids_by_project() / get_image_ids_by_project_id()
# ---------------------------------------------------------------------------


class TestGetImageIdsByProject:
    """get_image_ids_by_project() / get_image_ids_by_project_id() のテスト。"""

    @pytest.fixture
    def repo_with_images(self, memory_session_factory):
        """proj_a に3枚、proj_b に2枚の画像を持つリポジトリ。"""
        from lorairo.database.db_repository import ImageRepository

        repo = ImageRepository(session_factory=memory_session_factory)
        pid_a = repo.ensure_project("proj_a", Path("/tmp/a"))
        pid_b = repo.ensure_project("proj_b", Path("/tmp/b"))
        ids_a = [_make_image(memory_session_factory, project_id=pid_a) for _ in range(3)]
        ids_b = [_make_image(memory_session_factory, project_id=pid_b) for _ in range(2)]
        return repo, pid_a, pid_b, ids_a, ids_b

    def test_get_by_name_returns_correct_count(self, repo_with_images):
        """get_image_ids_by_project() が正しい件数を返す。"""
        repo, _, _, _, _ = repo_with_images
        result = repo.get_image_ids_by_project("proj_a")
        assert len(result) == 3

    def test_get_by_id_returns_correct_count(self, repo_with_images):
        """get_image_ids_by_project_id() が正しい件数を返す。"""
        repo, pid_a, _, _, _ = repo_with_images
        result = repo.get_image_ids_by_project_id(pid_a)
        assert len(result) == 3

    def test_get_by_name_returns_correct_ids(self, repo_with_images):
        """get_image_ids_by_project() が実際の画像 ID セットを返す。"""
        repo, _, _, ids_a, _ = repo_with_images
        result = repo.get_image_ids_by_project("proj_a")
        assert set(result) == set(ids_a)

    def test_get_by_id_returns_correct_ids(self, repo_with_images):
        """get_image_ids_by_project_id() が実際の画像 ID セットを返す。"""
        repo, pid_a, _, ids_a, _ = repo_with_images
        result = repo.get_image_ids_by_project_id(pid_a)
        assert set(result) == set(ids_a)

    def test_get_by_unknown_name_returns_empty(self, repo_with_images):
        """存在しないプロジェクト名では空リストを返す。"""
        repo, _, _, _, _ = repo_with_images
        result = repo.get_image_ids_by_project("nonexistent")
        assert result == []

    def test_get_does_not_mix_projects(self, repo_with_images):
        """proj_a の取得結果に proj_b の画像が含まれない。"""
        repo, _, _, _, _ = repo_with_images
        result_a = set(repo.get_image_ids_by_project("proj_a"))
        result_b = set(repo.get_image_ids_by_project("proj_b"))
        assert result_a.isdisjoint(result_b)


# ---------------------------------------------------------------------------
# assign_images_to_project()
# ---------------------------------------------------------------------------


class TestAssignImagesToProject:
    """assign_images_to_project() のテスト。"""

    @pytest.fixture
    def repo_with_unassigned_images(self, memory_session_factory):
        """proj_a を持ち、未割り当て画像3枚を含むリポジトリ。"""
        from lorairo.database.db_repository import ImageRepository

        repo = ImageRepository(session_factory=memory_session_factory)
        pid = repo.ensure_project("proj_a", Path("/tmp/a"))
        image_ids = [_make_image(memory_session_factory, project_id=None) for _ in range(3)]
        return repo, pid, image_ids

    def test_assign_returns_updated_count(self, repo_with_unassigned_images):
        """assign_images_to_project() が更新件数を返す。"""
        repo, pid, image_ids = repo_with_unassigned_images
        updated = repo.assign_images_to_project(image_ids, pid)
        assert updated == 3

    def test_assign_empty_list_returns_zero(self, repo_with_unassigned_images):
        """空リストを渡すと 0 を返す。"""
        repo, pid, _ = repo_with_unassigned_images
        updated = repo.assign_images_to_project([], pid)
        assert updated == 0

    def test_assign_images_are_retrievable(self, repo_with_unassigned_images):
        """割り当て後に get_image_ids_by_project_id() で取得できる。"""
        repo, pid, image_ids = repo_with_unassigned_images
        repo.assign_images_to_project(image_ids, pid)
        result = repo.get_image_ids_by_project_id(pid)
        assert set(result) == set(image_ids)

    def test_assign_partial_update(self, repo_with_unassigned_images):
        """一部の画像 ID のみ割り当てる場合、指定した件数だけ更新される。"""
        repo, pid, image_ids = repo_with_unassigned_images
        updated = repo.assign_images_to_project(image_ids[:2], pid)
        assert updated == 2
        result = repo.get_image_ids_by_project_id(pid)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# add_original_image — project_id セット検証（ISSUE #165 Codex P1 指摘対応）
# ---------------------------------------------------------------------------


class TestAddOriginalImageProjectId:
    """add_original_image() が info["project_id"] を Image に設定することを検証。

    マイグレーション後に登録される新規画像も project_id が付くことで、
    _apply_project_filter() の WHERE Image.project_id == subq が機能する。
    """

    @pytest.fixture
    def repository(self, memory_session_factory):
        from lorairo.database.db_repository import ImageRepository

        return ImageRepository(session_factory=memory_session_factory)

    @pytest.fixture
    def project_id(self, memory_session_factory):
        """projects テーブルにダミー行を挿入してIDを返す。"""
        from lorairo.database.schema import Project

        with memory_session_factory() as session:
            project = Project(name="test_project", path="/tmp/test_project")
            session.add(project)
            session.commit()
            return project.id

    def _base_info(self) -> dict:
        import uuid as _uuid

        uid = _uuid.uuid4().hex
        return {
            "uuid": uid,
            "phash": uid[:16],
            "original_image_path": f"/tmp/{uid}.png",
            "stored_image_path": f"/tmp/{uid}_s.png",
            "width": 100,
            "height": 100,
            "format": "PNG",
            "extension": "png",
        }

    def test_add_original_image_sets_project_id_when_provided(
        self, repository, memory_session_factory, project_id
    ):
        """info に project_id を含めると Image.project_id が設定される。"""
        from sqlalchemy import select

        from lorairo.database.schema import Image

        info = {**self._base_info(), "project_id": project_id}
        image_id = repository.add_original_image(info)

        with memory_session_factory() as session:
            img = session.execute(select(Image).where(Image.id == image_id)).scalar_one()
        assert img.project_id == project_id

    def test_add_original_image_project_id_none_by_default(self, repository, memory_session_factory):
        """info に project_id がない場合、Image.project_id は None。"""
        from sqlalchemy import select

        from lorairo.database.schema import Image

        info = self._base_info()
        image_id = repository.add_original_image(info)

        with memory_session_factory() as session:
            img = session.execute(select(Image).where(Image.id == image_id)).scalar_one()
        assert img.project_id is None
