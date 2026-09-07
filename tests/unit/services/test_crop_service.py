"""crop_service のユニットテスト (実 SQLite + 実ファイルシステム)。

ADR 0092 / Issue #1344。GUI を経由せずサービス関数を直接呼び、元画像が
一切変更されないこと・無効な矩形で副作用が残らないことを固定する。
"""

from pathlib import Path

import pytest
from PIL import Image

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.schema import TagAnnotationData
from lorairo.domain.crop_request import CropCreateRequest, CropRect
from lorairo.filesystem import FileSystemManager
from lorairo.services.crop_service import CropSourceInfo, create_crop_image, get_crop_source_info

pytestmark = pytest.mark.unit

PARENT_WIDTH = 1600
PARENT_HEIGHT = 1200


def _make_image(path: Path, width: int, height: int, color: tuple[int, int, int]) -> Path:
    """テスト用の実画像ファイルを作る。"""
    Image.new("RGB", (width, height), color).save(path)
    return path


def _register_parent(
    db_manager: ImageDatabaseManager,
    fsm: FileSystemManager,
    source_path: Path,
) -> int:
    """親画像を登録して image_id を返す。"""
    result = db_manager.register_original_image(source_path, fsm)
    assert result is not None, f"親画像の登録に失敗: {source_path}"
    return result[0]


def _tag_names(db_manager: ImageDatabaseManager, image_id: int) -> set[str]:
    return {tag["tag"] for tag in db_manager.get_image_annotations(image_id)["tags"]}


def _stored_path(db_manager: ImageDatabaseManager, image_id: int) -> Path:
    metadata = db_manager.get_image_metadata(image_id)
    assert metadata is not None
    return Path(str(metadata["stored_image_path"]))


def _manual_rating(db_manager: ImageDatabaseManager, image_id: int) -> str | None:
    ratings = db_manager.get_image_annotations(image_id)["ratings"]
    manual = [row for row in ratings if row["source"] == "Manual"]
    if not manual:
        return None
    return str(max(manual, key=lambda row: row["created_at"])["normalized_rating"])


@pytest.fixture
def parent_image(
    test_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    tmp_path: Path,
) -> int:
    """タグ 3 件と手動レーティングを持つ親画像を登録して ID を返す。"""
    source = _make_image(tmp_path / "parent.png", PARENT_WIDTH, PARENT_HEIGHT, (12, 128, 200))
    parent_id = _register_parent(test_db_manager, fs_manager, source)
    tags_data: list[TagAnnotationData] = [
        {
            "tag": "solo",
            "tag_id": None,
            "model_id": None,
            "existing": True,
            "is_edited_manually": False,
            "confidence_score": 0.75,
        },
        {
            "tag": "outdoors",
            "tag_id": None,
            "model_id": None,
            "existing": False,
            "is_edited_manually": False,
            "confidence_score": 0.5,
        },
        {
            "tag": "sky",
            "tag_id": None,
            "model_id": None,
            "existing": True,
            "is_edited_manually": False,
            "confidence_score": None,
        },
    ]
    test_db_manager.save_tags(parent_id, tags_data)
    test_db_manager.annotation_repo.update_manual_rating(parent_id, "PG-13")
    return parent_id


def _counts(
    db_manager: ImageDatabaseManager, parent_id: int, fsm: FileSystemManager
) -> tuple[int, int, int]:
    """(画像件数, 親の crop 子件数, original_images 配下のファイル数)。"""
    assert fsm.original_images_dir is not None
    original_root = fsm.original_images_dir.parent
    files = sum(1 for path in original_root.rglob("*") if path.is_file())
    return (
        db_manager.get_total_image_count(),
        len(db_manager.get_crop_children(parent_id)),
        files,
    )


class TestCreateCropImage:
    def test_registers_child_with_independent_id_and_cropped_file(
        self,
        test_db_manager: ImageDatabaseManager,
        fs_manager: FileSystemManager,
        parent_image: int,
    ) -> None:
        """子は独立した image_id で登録され、保存ファイルの実寸が矩形と一致する。"""
        request = CropCreateRequest(
            parent_image_id=parent_image,
            rect=CropRect(x=100, y=50, width=640, height=480),
        )

        child_id = create_crop_image(request, db_manager=test_db_manager, fsm=fs_manager)

        assert child_id != parent_image
        child_path = _stored_path(test_db_manager, child_id)
        assert child_path.is_file()
        with Image.open(child_path) as child_image:
            assert child_image.size == (640, 480)
        child_metadata = test_db_manager.get_image_metadata(child_id)
        assert child_metadata is not None
        assert (child_metadata["width"], child_metadata["height"]) == (640, 480)

    def test_parent_file_tags_and_rating_are_unchanged(
        self,
        test_db_manager: ImageDatabaseManager,
        fs_manager: FileSystemManager,
        parent_image: int,
    ) -> None:
        """クロップ作成で元画像のファイル・タグ・レーティングは変わらない。"""
        parent_path = _stored_path(test_db_manager, parent_image)
        before_bytes = parent_path.read_bytes()
        before_tags = _tag_names(test_db_manager, parent_image)
        before_rating = _manual_rating(test_db_manager, parent_image)

        request = CropCreateRequest(
            parent_image_id=parent_image,
            rect=CropRect(x=0, y=0, width=800, height=600),
            tags=tuple(sorted(before_tags)),
            rating="X",
        )
        create_crop_image(request, db_manager=test_db_manager, fsm=fs_manager)

        assert parent_path.read_bytes() == before_bytes
        assert _tag_names(test_db_manager, parent_image) == before_tags
        assert _manual_rating(test_db_manager, parent_image) == before_rating == "PG-13"

    def test_child_tags_are_request_only_and_inherit_parent_attributes(
        self,
        test_db_manager: ImageDatabaseManager,
        fs_manager: FileSystemManager,
        parent_image: int,
    ) -> None:
        """採用タグだけがコピーされ、親のタグ属性を引き継ぐ。"""
        parent_tags = {
            tag["tag"]: tag for tag in test_db_manager.get_image_annotations(parent_image)["tags"]
        }
        adopted = sorted(parent_tags)[:2]
        request = CropCreateRequest(
            parent_image_id=parent_image,
            rect=CropRect(x=10, y=10, width=320, height=240),
            tags=tuple(adopted),
        )

        child_id = create_crop_image(request, db_manager=test_db_manager, fsm=fs_manager)

        child_tags = {tag["tag"]: tag for tag in test_db_manager.get_image_annotations(child_id)["tags"]}
        assert set(child_tags) == set(adopted)
        for name in adopted:
            assert child_tags[name]["model_id"] == parent_tags[name]["model_id"]
            assert child_tags[name]["confidence_score"] == parent_tags[name]["confidence_score"]
            assert child_tags[name]["existing"] == parent_tags[name]["existing"]

    def test_tags_not_present_on_parent_are_registered_as_manual_existing(
        self,
        test_db_manager: ImageDatabaseManager,
        fs_manager: FileSystemManager,
        parent_image: int,
    ) -> None:
        """親に無いタグも採用タグとして子に登録される。"""
        request = CropCreateRequest(
            parent_image_id=parent_image,
            rect=CropRect(x=0, y=0, width=256, height=256),
            tags=("closeup",),
        )

        child_id = create_crop_image(request, db_manager=test_db_manager, fsm=fs_manager)

        child_tags = test_db_manager.get_image_annotations(child_id)["tags"]
        assert [tag["tag"] for tag in child_tags] == ["closeup"]
        assert child_tags[0]["existing"] is True
        assert child_tags[0]["model_id"] is None

    def test_rating_is_copied_and_can_differ_from_parent(
        self,
        test_db_manager: ImageDatabaseManager,
        fs_manager: FileSystemManager,
        parent_image: int,
    ) -> None:
        """子のレーティングは request の値で保存され、親とは独立に管理される。"""
        request = CropCreateRequest(
            parent_image_id=parent_image,
            rect=CropRect(x=0, y=0, width=512, height=512),
            rating="R",
        )

        child_id = create_crop_image(request, db_manager=test_db_manager, fsm=fs_manager)
        assert _manual_rating(test_db_manager, child_id) == "R"

        test_db_manager.annotation_repo.update_manual_rating(child_id, "XXX")
        assert _manual_rating(test_db_manager, child_id) == "XXX"
        assert _manual_rating(test_db_manager, parent_image) == "PG-13"

    def test_rating_is_left_unset_when_request_has_none(
        self,
        test_db_manager: ImageDatabaseManager,
        fs_manager: FileSystemManager,
        parent_image: int,
    ) -> None:
        """request.rating が None なら子のレーティングは未設定のまま。"""
        request = CropCreateRequest(
            parent_image_id=parent_image,
            rect=CropRect(x=0, y=0, width=512, height=512),
        )

        child_id = create_crop_image(request, db_manager=test_db_manager, fsm=fs_manager)

        assert _manual_rating(test_db_manager, child_id) is None

    def test_crop_relation_stores_rect_and_origin(
        self,
        test_db_manager: ImageDatabaseManager,
        fs_manager: FileSystemManager,
        parent_image: int,
    ) -> None:
        """crop_relations に親子・座標・由来が保存される。"""
        request = CropCreateRequest(
            parent_image_id=parent_image,
            rect=CropRect(x=33, y=44, width=555, height=666),
            origin="yolo-v8",
        )

        child_id = create_crop_image(request, db_manager=test_db_manager, fsm=fs_manager)

        children = test_db_manager.get_crop_children(parent_image)
        assert len(children) == 1
        relation = children[0]
        assert relation.child_image_id == child_id
        assert (relation.x, relation.y, relation.width, relation.height) == (33, 44, 555, 666)
        assert relation.origin == "yolo-v8"

        parent_relation = test_db_manager.get_crop_parent(child_id)
        assert parent_relation is not None
        assert parent_relation.parent_image_id == parent_image

    def test_child_can_be_cropped_again_into_a_grandchild(
        self,
        test_db_manager: ImageDatabaseManager,
        fs_manager: FileSystemManager,
        parent_image: int,
    ) -> None:
        """子を親としてさらに切り出せる (親 → 子 → 孫)。"""
        child_id = create_crop_image(
            CropCreateRequest(
                parent_image_id=parent_image,
                rect=CropRect(x=0, y=0, width=800, height=600),
            ),
            db_manager=test_db_manager,
            fsm=fs_manager,
        )
        grandchild_id = create_crop_image(
            CropCreateRequest(
                parent_image_id=child_id,
                rect=CropRect(x=10, y=10, width=200, height=150),
            ),
            db_manager=test_db_manager,
            fsm=fs_manager,
        )

        assert len({parent_image, child_id, grandchild_id}) == 3
        grandchild_relation = test_db_manager.get_crop_parent(grandchild_id)
        assert grandchild_relation is not None
        assert grandchild_relation.parent_image_id == child_id
        assert [rel.child_image_id for rel in test_db_manager.get_crop_children(child_id)] == [
            grandchild_id
        ]

    @pytest.mark.parametrize(
        ("rect", "label"),
        [
            (CropRect(x=0, y=0, width=0, height=100), "zero_width"),
            (CropRect(x=0, y=0, width=100, height=0), "zero_height"),
            (CropRect(x=PARENT_WIDTH - 10, y=0, width=100, height=100), "out_of_bounds"),
            (CropRect(x=-5, y=0, width=100, height=100), "negative_origin"),
        ],
    )
    def test_invalid_rect_raises_value_error_without_side_effects(
        self,
        test_db_manager: ImageDatabaseManager,
        fs_manager: FileSystemManager,
        parent_image: int,
        rect: CropRect,
        label: str,
    ) -> None:
        """無効な矩形は ValueError で、DB とファイルに副作用が残らない。"""
        before = _counts(test_db_manager, parent_image, fs_manager)

        with pytest.raises(ValueError):
            create_crop_image(
                CropCreateRequest(parent_image_id=parent_image, rect=rect),
                db_manager=test_db_manager,
                fsm=fs_manager,
            )

        assert _counts(test_db_manager, parent_image, fs_manager) == before, label

    def test_missing_parent_raises_value_error_without_side_effects(
        self,
        test_db_manager: ImageDatabaseManager,
        fs_manager: FileSystemManager,
        parent_image: int,
    ) -> None:
        """親画像が存在しなければ ValueError で副作用が残らない。"""
        before = _counts(test_db_manager, parent_image, fs_manager)

        with pytest.raises(ValueError):
            create_crop_image(
                CropCreateRequest(
                    parent_image_id=parent_image + 9999,
                    rect=CropRect(x=0, y=0, width=100, height=100),
                ),
                db_manager=test_db_manager,
                fsm=fs_manager,
            )

        assert _counts(test_db_manager, parent_image, fs_manager) == before

    def test_invalid_rating_raises_value_error_without_side_effects(
        self,
        test_db_manager: ImageDatabaseManager,
        fs_manager: FileSystemManager,
        parent_image: int,
    ) -> None:
        """正準値外のレーティングは ValueError で副作用が残らない。"""
        before = _counts(test_db_manager, parent_image, fs_manager)

        with pytest.raises(ValueError):
            create_crop_image(
                CropCreateRequest(
                    parent_image_id=parent_image,
                    rect=CropRect(x=0, y=0, width=100, height=100),
                    rating="NC-17",
                ),
                db_manager=test_db_manager,
                fsm=fs_manager,
            )

        assert _counts(test_db_manager, parent_image, fs_manager) == before


class TestGetCropSourceInfo:
    def test_returns_parent_size_candidate_tags_and_manual_rating(
        self,
        test_db_manager: ImageDatabaseManager,
        parent_image: int,
    ) -> None:
        """親の寸法・候補タグ・手動レーティングを返す。"""
        info = get_crop_source_info(parent_image, db_manager=test_db_manager)

        assert isinstance(info, CropSourceInfo)
        assert (info.width, info.height) == (PARENT_WIDTH, PARENT_HEIGHT)
        assert info.image_path.is_file()
        assert set(info.candidate_tags) == _tag_names(test_db_manager, parent_image)
        assert len(info.candidate_tags) == len(set(info.candidate_tags))
        assert info.rating == "PG-13"

    def test_excludes_soft_rejected_tags(
        self,
        test_db_manager: ImageDatabaseManager,
        parent_image: int,
    ) -> None:
        """soft-reject 済みタグは候補タグに含まれない。"""
        rejected = sorted(_tag_names(test_db_manager, parent_image))[0]
        assert test_db_manager.soft_reject_tag(parent_image, rejected) is True

        info = get_crop_source_info(parent_image, db_manager=test_db_manager)

        assert rejected not in info.candidate_tags
        assert set(info.candidate_tags) == _tag_names(test_db_manager, parent_image)

    def test_returns_none_rating_when_parent_has_no_manual_rating(
        self,
        test_db_manager: ImageDatabaseManager,
        fs_manager: FileSystemManager,
        tmp_path: Path,
    ) -> None:
        """手動レーティング未設定の親では rating が None になる。"""
        source = _make_image(tmp_path / "plain.png", 400, 300, (240, 20, 20))
        parent_id = _register_parent(test_db_manager, fs_manager, source)

        info = get_crop_source_info(parent_id, db_manager=test_db_manager)

        assert info.rating is None
        assert info.candidate_tags == ()

    def test_missing_parent_raises_value_error(
        self,
        test_db_manager: ImageDatabaseManager,
        parent_image: int,
    ) -> None:
        """存在しない親画像 ID では ValueError。"""
        with pytest.raises(ValueError):
            get_crop_source_info(parent_image + 9999, db_manager=test_db_manager)
