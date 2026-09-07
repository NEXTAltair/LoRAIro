"""`ImageDatabaseManager` のクロップ親子関係 Facade / DI contract (ADR 0092, Issue #1343)。"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.repository.crop_relation import CropRelationRepository
from lorairo.database.schema import Base, Image
from lorairo.services.configuration_service import ConfigurationService

pytestmark = pytest.mark.unit


@pytest.fixture
def memory_session_factory():
    """in-memory SQLite セッションファクトリ (schema 全テーブル)。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine)


def _insert_image(session_factory, *, uuid: str) -> int:
    """テスト用画像を 1 件作成して id を返す。"""
    with session_factory() as session:
        image = Image(
            uuid=uuid,
            phash=f"phash-{uuid}",
            original_image_path=f"/tmp/{uuid}.png",
            stored_image_path=f"/tmp/{uuid}.png",
            width=1024,
            height=768,
            format="PNG",
            extension=".png",
            filename=f"{uuid}.png",
        )
        session.add(image)
        session.commit()
        image_id: int = image.id
    return image_id


class TestCropRelationDIContract:
    """`crop_relation_repo` の DI + 既定生成 (ADR 0035 パターン)。"""

    def test_creates_repo_with_session_factory_when_omitted(self, memory_session_factory) -> None:
        cfg = Mock(spec=ConfigurationService)
        manager = ImageDatabaseManager(config_service=cfg, session_factory=memory_session_factory)

        assert isinstance(manager.crop_relation_repo, CropRelationRepository)
        assert manager.crop_relation_repo.session_factory is memory_session_factory

    def test_uses_injected_repo(self, memory_session_factory) -> None:
        cfg = Mock(spec=ConfigurationService)
        injected = Mock(spec=CropRelationRepository)

        manager = ImageDatabaseManager(config_service=cfg, crop_relation_repo=injected)

        assert manager.crop_relation_repo is injected

    def test_injected_repo_supplies_session_factory_for_other_repos(self, memory_session_factory) -> None:
        """crop_relation_repo だけ渡した場合も session_factory が全 Repo へ伝播する。"""
        cfg = Mock(spec=ConfigurationService)
        repo = CropRelationRepository(session_factory=memory_session_factory)

        manager = ImageDatabaseManager(config_service=cfg, crop_relation_repo=repo)

        assert manager.image_repo.session_factory is memory_session_factory


class TestCropRelationFacade:
    """薄いラッパーが `crop_relation_repo` へ委譲する。"""

    def test_add_and_get_round_trip(self, memory_session_factory) -> None:
        cfg = Mock(spec=ConfigurationService)
        manager = ImageDatabaseManager(config_service=cfg, session_factory=memory_session_factory)
        parent_id = _insert_image(memory_session_factory, uuid="parent")
        child_id = _insert_image(memory_session_factory, uuid="child")

        relation_id = manager.add_crop_relation(
            parent_image_id=parent_id, child_image_id=child_id, x=1, y=2, width=3, height=4
        )

        assert relation_id > 0
        parent_relation = manager.get_crop_parent(child_id)
        assert parent_relation is not None
        assert parent_relation.parent_image_id == parent_id
        assert (parent_relation.x, parent_relation.y) == (1, 2)
        assert parent_relation.origin == "manual"
        assert [child.child_image_id for child in manager.get_crop_children(parent_id)] == [child_id]

    def test_add_crop_relation_delegates_with_origin(self, memory_session_factory) -> None:
        cfg = Mock(spec=ConfigurationService)
        injected = Mock(spec=CropRelationRepository)
        injected.add_relation.return_value = 42
        manager = ImageDatabaseManager(config_service=cfg, crop_relation_repo=injected)

        assert (
            manager.add_crop_relation(
                parent_image_id=1,
                child_image_id=2,
                x=3,
                y=4,
                width=5,
                height=6,
                origin="yolo-face",
            )
            == 42
        )
        injected.add_relation.assert_called_once_with(
            parent_image_id=1, child_image_id=2, x=3, y=4, width=5, height=6, origin="yolo-face"
        )

    def test_get_crop_children_delegates(self, memory_session_factory) -> None:
        cfg = Mock(spec=ConfigurationService)
        injected = Mock(spec=CropRelationRepository)
        injected.get_children.return_value = []
        manager = ImageDatabaseManager(config_service=cfg, crop_relation_repo=injected)

        assert manager.get_crop_children(7) == []
        injected.get_children.assert_called_once_with(7)

    def test_get_crop_parent_delegates(self, memory_session_factory) -> None:
        cfg = Mock(spec=ConfigurationService)
        injected = Mock(spec=CropRelationRepository)
        injected.get_parent.return_value = None
        manager = ImageDatabaseManager(config_service=cfg, crop_relation_repo=injected)

        assert manager.get_crop_parent(7) is None
        injected.get_parent.assert_called_once_with(7)
