"""ProjectRepository 直接の単体テスト (ADR 0035 段階 2, Issue #423)。

`db_repository.py` から抽出した `ProjectRepository` の責務境界を独立して検証する。
既存の `tests/unit/database/test_db_repository_project_filter.py` は
`ImageRepository` の delegating facade 経由で同じ実装をカバーしているため、本ファイルでは
ProjectRepository を直接 instantiate して以下を最小限カバーする:

- BaseRepository 継承 / session_factory 共有
- `ensure_project` の upsert / path 更新 / SQLAlchemyError 伝播
- `get_image_ids_by_project` / `get_image_ids_by_project_id` の動作
- `assign_images_to_project` の正常系 + 空入力ガード
- ImageRepository facade 経由でも同じ ProjectRepository クラスが見えること
- DI contract: ImageDatabaseManager は injected project_repo 経由で呼ぶ
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.repository.base import BaseRepository
from lorairo.database.repository.project import ProjectRepository
from lorairo.database.schema import Image, Project
from lorairo.services.configuration_service import ConfigurationService


@pytest.fixture
def memory_session_factory():
    """in-memory SQLite セッションファクトリ（schema 全テーブル）。"""
    from lorairo.database.schema import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine)


@pytest.fixture
def project_repository(memory_session_factory) -> ProjectRepository:
    """In-memory SQLite に対する ProjectRepository インスタンス。"""
    return ProjectRepository(session_factory=memory_session_factory)


def _make_image(session_factory, project_id: int | None = None) -> int:
    """テスト用 Image を 1 件作成して id を返す。"""
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


@pytest.mark.unit
class TestProjectRepositoryStructure:
    """ADR 0035 段階 2 で確立した抽出構造の sanity check。"""

    def test_inherits_base_repository(self) -> None:
        """ProjectRepository は BaseRepository を継承する。"""
        assert issubclass(ProjectRepository, BaseRepository)

    def test_holds_session_factory(self, memory_session_factory) -> None:
        """`session_factory` を BaseRepository 経由で保持する。"""
        repo = ProjectRepository(session_factory=memory_session_factory)
        assert repo.session_factory is memory_session_factory


@pytest.mark.unit
class TestEnsureProject:
    """`ensure_project` の upsert 動作。"""

    def test_creates_new_project(self, project_repository: ProjectRepository) -> None:
        """新規プロジェクトを作成し正の ID を返す。"""
        project_id = project_repository.ensure_project("alpha", Path("/tmp/alpha"))
        assert isinstance(project_id, int)
        assert project_id > 0

    def test_returns_same_id_on_duplicate(self, project_repository: ProjectRepository) -> None:
        """同名で 2 回呼んでも同じ ID が返る (upsert)。"""
        id1 = project_repository.ensure_project("beta", Path("/tmp/beta"))
        id2 = project_repository.ensure_project("beta", Path("/tmp/beta"))
        assert id1 == id2

    def test_updates_path_when_different(
        self, project_repository: ProjectRepository, memory_session_factory
    ) -> None:
        """同名でパスが変わった場合、path カラムが更新される。"""
        project_id = project_repository.ensure_project("gamma", Path("/tmp/old"))
        project_repository.ensure_project("gamma", Path("/tmp/new"))

        with memory_session_factory() as session:
            project = session.execute(select(Project).where(Project.id == project_id)).scalar_one()
            assert project.path == str(Path("/tmp/new"))

    def test_persists_description(
        self, project_repository: ProjectRepository, memory_session_factory
    ) -> None:
        """description 引数が DB に保存される。"""
        project_id = project_repository.ensure_project(
            "delta", Path("/tmp/delta"), description="some description"
        )
        with memory_session_factory() as session:
            project = session.execute(select(Project).where(Project.id == project_id)).scalar_one()
            assert project.description == "some description"

    def test_empty_description_stored_as_none(
        self, project_repository: ProjectRepository, memory_session_factory
    ) -> None:
        """空文字 description は None として保存される (`description or None`)。"""
        project_id = project_repository.ensure_project("epsilon", Path("/tmp/epsilon"))
        with memory_session_factory() as session:
            project = session.execute(select(Project).where(Project.id == project_id)).scalar_one()
            assert project.description is None

    def test_raises_sqlalchemy_error(self, project_repository: ProjectRepository) -> None:
        """予期しない SQLAlchemyError は呼び出し元に伝播する (silent return しない)。"""
        # session.execute で SQLAlchemyError を発生させる
        mock_session = Mock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_session.execute.side_effect = SQLAlchemyError("simulated DB failure")
        mock_session.rollback = Mock()

        with patch.object(project_repository, "session_factory", return_value=mock_session):
            with pytest.raises(SQLAlchemyError, match="simulated DB failure"):
                project_repository.ensure_project("zeta", Path("/tmp/zeta"))
        mock_session.rollback.assert_called()


@pytest.mark.unit
class TestGetImageIdsByProject:
    """`get_image_ids_by_project` / `get_image_ids_by_project_id` の動作。"""

    @pytest.fixture
    def populated_repo(self, project_repository: ProjectRepository, memory_session_factory):
        """proj_a に 3 枚 / proj_b に 2 枚を保持する fixture。"""
        pid_a = project_repository.ensure_project("proj_a", Path("/tmp/a"))
        pid_b = project_repository.ensure_project("proj_b", Path("/tmp/b"))
        ids_a = [_make_image(memory_session_factory, project_id=pid_a) for _ in range(3)]
        ids_b = [_make_image(memory_session_factory, project_id=pid_b) for _ in range(2)]
        return project_repository, pid_a, pid_b, ids_a, ids_b

    def test_get_by_name_returns_correct_ids(self, populated_repo) -> None:
        """get_image_ids_by_project は名前から正しい id セットを返す。"""
        repo, _, _, ids_a, _ = populated_repo
        result = repo.get_image_ids_by_project("proj_a")
        assert set(result) == set(ids_a)

    def test_get_by_id_returns_correct_ids(self, populated_repo) -> None:
        """get_image_ids_by_project_id は id から正しい id セットを返す。"""
        repo, pid_a, _, ids_a, _ = populated_repo
        result = repo.get_image_ids_by_project_id(pid_a)
        assert set(result) == set(ids_a)

    def test_get_by_unknown_name_returns_empty(self, populated_repo) -> None:
        """存在しないプロジェクト名では空リストを返す (silent return ではなく正常系)。"""
        repo, _, _, _, _ = populated_repo
        assert repo.get_image_ids_by_project("nonexistent") == []

    def test_get_by_unknown_id_returns_empty(self, populated_repo) -> None:
        """存在しないプロジェクト ID では空リストを返す。"""
        repo, _, _, _, _ = populated_repo
        assert repo.get_image_ids_by_project_id(99999) == []

    def test_does_not_mix_projects(self, populated_repo) -> None:
        """proj_a の取得結果に proj_b の画像が含まれない。"""
        repo, _, _, _, _ = populated_repo
        result_a = set(repo.get_image_ids_by_project("proj_a"))
        result_b = set(repo.get_image_ids_by_project("proj_b"))
        assert result_a.isdisjoint(result_b)


@pytest.mark.unit
class TestAssignImagesToProject:
    """`assign_images_to_project` の動作。"""

    def test_returns_zero_for_empty_input(self, project_repository: ProjectRepository) -> None:
        """空リスト入力では DB アクセスせず 0 を返す。"""
        pid = project_repository.ensure_project("only", Path("/tmp/only"))
        assert project_repository.assign_images_to_project([], pid) == 0

    def test_assigns_images_and_returns_count(
        self, project_repository: ProjectRepository, memory_session_factory
    ) -> None:
        """画像を割り当てた件数を返し、DB に反映される。"""
        pid = project_repository.ensure_project("target", Path("/tmp/target"))
        unassigned_ids = [_make_image(memory_session_factory, project_id=None) for _ in range(3)]

        updated = project_repository.assign_images_to_project(unassigned_ids, pid)

        assert updated == 3
        result = project_repository.get_image_ids_by_project_id(pid)
        assert set(result) == set(unassigned_ids)

    def test_reassigns_to_different_project(
        self, project_repository: ProjectRepository, memory_session_factory
    ) -> None:
        """既に割り当てられた画像を別プロジェクトに再割り当てできる。"""
        pid_a = project_repository.ensure_project("from", Path("/tmp/from"))
        pid_b = project_repository.ensure_project("to", Path("/tmp/to"))
        image_ids = [_make_image(memory_session_factory, project_id=pid_a) for _ in range(2)]

        updated = project_repository.assign_images_to_project(image_ids, pid_b)

        assert updated == 2
        assert project_repository.get_image_ids_by_project_id(pid_a) == []
        assert set(project_repository.get_image_ids_by_project_id(pid_b)) == set(image_ids)


@pytest.mark.unit
class TestImageDatabaseManagerDIContract:
    """ImageDatabaseManager が injected `project_repo` 経由で ensure_project を呼ぶ (DI contract)。

    PR #477 review 教訓: クラス経由 static 呼び出しではなく、インスタンス経由で呼ぶことで
    テストが mock 注入で動作を制御できる。
    """

    def test_get_current_project_id_uses_injected_project_repo(self) -> None:
        """`_get_current_project_id` は self.project_repo.ensure_project を呼ぶ。"""
        mock_config_service = Mock(spec=ConfigurationService)
        mock_project_repo = Mock(spec=ProjectRepository)
        mock_project_repo.ensure_project.return_value = 123

        manager = ImageDatabaseManager(
            config_service=mock_config_service,
            project_repo=mock_project_repo,
        )

        fake_root = Path("/tmp/some_project")
        with patch("lorairo.database.db_core.get_current_project_root", return_value=fake_root):
            result = manager._get_current_project_id()

        assert result == 123
        # injected mock 経由で呼ばれることを assert (DI contract)
        mock_project_repo.ensure_project.assert_called_once_with("some_project", fake_root)

    def test_auto_constructs_project_repo_with_session_factory(self, db_session_factory) -> None:
        """`session_factory` 引数で project_repo が自動生成される。

        ADR 0035 段階 6 (#423): facade 撤廃後、session_factory を Manager に渡すと
        全 Repo がそれを共有して構築される。
        """
        mock_config_service = Mock(spec=ConfigurationService)
        manager = ImageDatabaseManager(
            config_service=mock_config_service,
            session_factory=db_session_factory,
        )
        assert isinstance(manager.project_repo, ProjectRepository)
        assert manager.project_repo.session_factory is db_session_factory
