"""`CropRelationRepository` の単体テスト (ADR 0092, Issue #1343)。

クロップ画像の直接の親子関係と切り出し矩形を `crop_relations` に永続化する
Repository の責務境界を検証する:

- 同じ親に複数の子を登録できる / `get_children` は登録順
- 親 → 子 → 孫の連鎖 (子を親として孫を登録できる)
- 未登録画像に対する `get_parent` / `get_children` の空返し
- 同じ子の二重登録は `IntegrityError` (1 子 = 1 親)
- `origin` の既定値は `manual`
- session を作り直しても保持される (再接続相当)
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from lorairo.database.repository.base import BaseRepository
from lorairo.database.repository.crop_relation import CropRelationRepository
from lorairo.database.schema import Image

pytestmark = pytest.mark.unit


@pytest.fixture
def crop_relation_repository(db_session_factory) -> CropRelationRepository:
    """共通 conftest の schema 済み in-memory DB に対する Repository。"""
    return CropRelationRepository(session_factory=db_session_factory)


def _insert_image(db_session_factory, *, uuid: str, width: int = 1024, height: int = 768) -> int:
    """テスト用画像を 1 件作成して id を返す。"""
    with db_session_factory() as session:
        image = Image(
            uuid=uuid,
            phash=f"phash-{uuid}",
            original_image_path=f"/tmp/{uuid}.png",
            stored_image_path=f"/tmp/{uuid}.png",
            width=width,
            height=height,
            format="PNG",
            extension=".png",
            filename=f"{uuid}.png",
        )
        session.add(image)
        session.commit()
        image_id: int = image.id
    return image_id


class TestSchemaCreation:
    """`Base.metadata.create_all` 経由で crop_relations が作成される。"""

    def test_crop_relations_table_exists(self, test_engine_with_schema) -> None:
        from sqlalchemy import inspect

        assert "crop_relations" in inspect(test_engine_with_schema).get_table_names()


class TestAddRelation:
    """`add_relation` の登録と既定値。"""

    def test_returns_positive_relation_id(
        self, crop_relation_repository: CropRelationRepository, db_session_factory
    ) -> None:
        parent_id = _insert_image(db_session_factory, uuid="parent")
        child_id = _insert_image(db_session_factory, uuid="child")

        relation_id = crop_relation_repository.add_relation(
            parent_image_id=parent_id,
            child_image_id=child_id,
            x=10,
            y=20,
            width=100,
            height=50,
        )

        assert relation_id > 0

    def test_origin_defaults_to_manual(
        self, crop_relation_repository: CropRelationRepository, db_session_factory
    ) -> None:
        parent_id = _insert_image(db_session_factory, uuid="parent")
        child_id = _insert_image(db_session_factory, uuid="child")
        crop_relation_repository.add_relation(
            parent_image_id=parent_id, child_image_id=child_id, x=0, y=0, width=10, height=10
        )

        relation = crop_relation_repository.get_parent(child_id)

        assert relation is not None
        assert relation.origin == "manual"

    def test_origin_can_record_detector_name(
        self, crop_relation_repository: CropRelationRepository, db_session_factory
    ) -> None:
        """#1340 の検出器由来は追加マイグレーションなしに origin へ入る。"""
        parent_id = _insert_image(db_session_factory, uuid="parent")
        child_id = _insert_image(db_session_factory, uuid="child")
        crop_relation_repository.add_relation(
            parent_image_id=parent_id,
            child_image_id=child_id,
            x=0,
            y=0,
            width=10,
            height=10,
            origin="yolo-face",
        )

        relation = crop_relation_repository.get_parent(child_id)

        assert relation is not None
        assert relation.origin == "yolo-face"

    def test_stores_rect_in_parent_pixel_coordinates(
        self, crop_relation_repository: CropRelationRepository, db_session_factory
    ) -> None:
        parent_id = _insert_image(db_session_factory, uuid="parent")
        child_id = _insert_image(db_session_factory, uuid="child")
        crop_relation_repository.add_relation(
            parent_image_id=parent_id, child_image_id=child_id, x=11, y=22, width=333, height=444
        )

        relation = crop_relation_repository.get_parent(child_id)

        assert relation is not None
        assert (relation.x, relation.y, relation.width, relation.height) == (11, 22, 333, 444)

    def test_duplicate_child_raises_integrity_error(
        self, crop_relation_repository: CropRelationRepository, db_session_factory
    ) -> None:
        """1 子 = 1 親。同じ子を二重登録すると IntegrityError が伝播する。"""
        parent_a = _insert_image(db_session_factory, uuid="parent-a")
        parent_b = _insert_image(db_session_factory, uuid="parent-b")
        child_id = _insert_image(db_session_factory, uuid="child")
        crop_relation_repository.add_relation(
            parent_image_id=parent_a, child_image_id=child_id, x=0, y=0, width=10, height=10
        )

        with pytest.raises(IntegrityError):
            crop_relation_repository.add_relation(
                parent_image_id=parent_b, child_image_id=child_id, x=0, y=0, width=10, height=10
            )


class TestGetChildren:
    """`get_children` は同じ親の子を登録順に返す。"""

    def test_returns_multiple_children_in_creation_order(
        self, crop_relation_repository: CropRelationRepository, db_session_factory
    ) -> None:
        parent_id = _insert_image(db_session_factory, uuid="parent")
        first_child = _insert_image(db_session_factory, uuid="child-1")
        second_child = _insert_image(db_session_factory, uuid="child-2")
        third_child = _insert_image(db_session_factory, uuid="child-3")
        for index, child_id in enumerate((third_child, first_child, second_child)):
            crop_relation_repository.add_relation(
                parent_image_id=parent_id,
                child_image_id=child_id,
                x=index,
                y=index,
                width=10,
                height=10,
            )

        children = crop_relation_repository.get_children(parent_id)

        # 登録順 (relation.id 昇順) であり、子 ID 昇順ではない
        assert [relation.child_image_id for relation in children] == [
            third_child,
            first_child,
            second_child,
        ]

    def test_returns_empty_list_for_image_without_children(
        self, crop_relation_repository: CropRelationRepository, db_session_factory
    ) -> None:
        image_id = _insert_image(db_session_factory, uuid="lonely")

        assert crop_relation_repository.get_children(image_id) == []

    def test_returns_empty_list_for_unknown_image(
        self, crop_relation_repository: CropRelationRepository
    ) -> None:
        assert crop_relation_repository.get_children(9999) == []


class TestGetParent:
    """`get_parent` は直接の親の関係行を返す。"""

    def test_returns_none_for_non_crop_image(
        self, crop_relation_repository: CropRelationRepository, db_session_factory
    ) -> None:
        image_id = _insert_image(db_session_factory, uuid="original")

        assert crop_relation_repository.get_parent(image_id) is None

    def test_returns_none_for_unknown_image(self, crop_relation_repository: CropRelationRepository) -> None:
        assert crop_relation_repository.get_parent(9999) is None


class TestGrandchildChain:
    """親 → 子 → 孫は直接の親子行の連鎖で表現される。"""

    def test_child_can_become_parent_of_grandchild(
        self, crop_relation_repository: CropRelationRepository, db_session_factory
    ) -> None:
        parent_id = _insert_image(db_session_factory, uuid="parent")
        child_id = _insert_image(db_session_factory, uuid="child")
        grandchild_id = _insert_image(db_session_factory, uuid="grandchild")
        crop_relation_repository.add_relation(
            parent_image_id=parent_id, child_image_id=child_id, x=10, y=10, width=200, height=200
        )
        crop_relation_repository.add_relation(
            parent_image_id=child_id, child_image_id=grandchild_id, x=5, y=5, width=50, height=50
        )

        child_relation = crop_relation_repository.get_parent(child_id)
        grandchild_relation = crop_relation_repository.get_parent(grandchild_id)

        assert child_relation is not None
        assert child_relation.parent_image_id == parent_id
        assert grandchild_relation is not None
        assert grandchild_relation.parent_image_id == child_id
        # 座標は直接の親基準 (孫の矩形は子画像基準)
        assert (grandchild_relation.x, grandchild_relation.y) == (5, 5)

    def test_parent_children_do_not_include_grandchild(
        self, crop_relation_repository: CropRelationRepository, db_session_factory
    ) -> None:
        parent_id = _insert_image(db_session_factory, uuid="parent")
        child_id = _insert_image(db_session_factory, uuid="child")
        grandchild_id = _insert_image(db_session_factory, uuid="grandchild")
        crop_relation_repository.add_relation(
            parent_image_id=parent_id, child_image_id=child_id, x=0, y=0, width=10, height=10
        )
        crop_relation_repository.add_relation(
            parent_image_id=child_id, child_image_id=grandchild_id, x=0, y=0, width=5, height=5
        )

        assert [
            relation.child_image_id for relation in crop_relation_repository.get_children(parent_id)
        ] == [child_id]
        assert [
            relation.child_image_id for relation in crop_relation_repository.get_children(child_id)
        ] == [grandchild_id]


class TestPersistenceAcrossSessions:
    """session / repository を作り直しても関係は保持される (再接続相当)。"""

    def test_relation_survives_new_session_factory(
        self, crop_relation_repository: CropRelationRepository, db_session_factory, test_engine_with_schema
    ) -> None:
        parent_id = _insert_image(db_session_factory, uuid="parent")
        child_id = _insert_image(db_session_factory, uuid="child")
        crop_relation_repository.add_relation(
            parent_image_id=parent_id, child_image_id=child_id, x=7, y=8, width=9, height=10
        )

        reconnected_factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine_with_schema)
        reconnected_repository = CropRelationRepository(session_factory=reconnected_factory)

        relation = reconnected_repository.get_parent(child_id)
        children = reconnected_repository.get_children(parent_id)

        assert relation is not None
        assert relation.parent_image_id == parent_id
        assert (relation.x, relation.y, relation.width, relation.height) == (7, 8, 9, 10)
        assert [child.child_image_id for child in children] == [child_id]


class TestRepositoryContract:
    """BaseRepository 継承 / session_factory 共有。"""

    def test_inherits_base_repository(self, crop_relation_repository: CropRelationRepository) -> None:
        assert isinstance(crop_relation_repository, BaseRepository)

    def test_shares_injected_session_factory(self, db_session_factory) -> None:
        repository = CropRelationRepository(session_factory=db_session_factory)
        assert repository.session_factory is db_session_factory
