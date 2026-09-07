"""クロップ画像作成の BDD ステップ定義 (Issue #1344 / ADR 0092)。

実 SQLite + 実ファイルシステムでサービス層の振る舞い仕様を固定する。
"""

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import Mock

from PIL import Image
from pytest_bdd import given, parsers, scenarios, then, when

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.schema import TagAnnotationData
from lorairo.domain.crop_request import CropCreateRequest, CropRect
from lorairo.filesystem import FileSystemManager
from lorairo.services.crop_service import create_crop_image
from lorairo.services.dataset_export_service import DatasetExportService

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "crop_service.feature"
scenarios(str(_FEATURE_FILE))

PARENT_WIDTH = 1600
PARENT_HEIGHT = 1200
PARENT_RATING = "PG-13"
PARENT_TAGS = ("solo", "outdoors")
EXPORT_RESOLUTION = 768


@dataclass
class CropContext:
    """ステップ間で受け渡すクロップ作成の状態。"""

    db_manager: ImageDatabaseManager
    fsm: FileSystemManager
    workspace: Path
    parent_id: int
    parent_bytes: bytes
    parent_tags: set[str]
    child_id: int | None = None
    error: Exception | None = None
    baseline: tuple[int, int, int] = (0, 0, 0)
    export_dir: Path | None = None
    exported_stem: str = ""
    processed_name: str = field(default="")


def _counts(ctx: CropContext) -> tuple[int, int, int]:
    """(画像件数, 親のクロップ子件数, original_images 配下のファイル数)。"""
    assert ctx.fsm.original_images_dir is not None
    original_root = ctx.fsm.original_images_dir.parent
    files = sum(1 for path in original_root.rglob("*") if path.is_file())
    return (
        ctx.db_manager.get_total_image_count(),
        len(ctx.db_manager.get_crop_children(ctx.parent_id)),
        files,
    )


def _stored_path(db_manager: ImageDatabaseManager, image_id: int) -> Path:
    metadata = db_manager.get_image_metadata(image_id)
    assert metadata is not None
    return Path(str(metadata["stored_image_path"]))


def _tag_names(db_manager: ImageDatabaseManager, image_id: int) -> set[str]:
    return {tag["tag"] for tag in db_manager.get_image_annotations(image_id)["tags"]}


def _manual_rating(db_manager: ImageDatabaseManager, image_id: int) -> str | None:
    manual = [
        row for row in db_manager.get_image_annotations(image_id)["ratings"] if row["source"] == "Manual"
    ]
    if not manual:
        return None
    return str(max(manual, key=lambda row: row["created_at"])["normalized_rating"])


def _crop(ctx: CropContext, rect: CropRect, rating: str | None) -> None:
    """クロップを実行し、成功なら child_id、失敗なら error を ctx に残す。"""
    ctx.baseline = _counts(ctx)
    request = CropCreateRequest(
        parent_image_id=ctx.parent_id,
        rect=rect,
        tags=tuple(sorted(ctx.parent_tags)),
        rating=rating,
    )
    try:
        ctx.child_id = create_crop_image(request, db_manager=ctx.db_manager, fsm=ctx.fsm)
    except ValueError as exc:
        ctx.error = exc


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given("タグとレーティングを持つ元画像が登録されている", target_fixture="ctx")
def given_parent_image_registered(
    test_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    tmp_path: Path,
) -> CropContext:
    source = tmp_path / "bdd_parent.png"
    Image.new("RGB", (PARENT_WIDTH, PARENT_HEIGHT), (24, 100, 160)).save(source)
    registered = test_db_manager.register_original_image(source, fs_manager)
    assert registered is not None
    parent_id = registered[0]

    tags_data: list[TagAnnotationData] = [
        {
            "tag": tag,
            "tag_id": None,
            "model_id": None,
            "existing": True,
            "is_edited_manually": False,
            "confidence_score": None,
        }
        for tag in PARENT_TAGS
    ]
    test_db_manager.save_tags(parent_id, tags_data)
    test_db_manager.annotation_repo.update_manual_rating(parent_id, PARENT_RATING)

    return CropContext(
        db_manager=test_db_manager,
        fsm=fs_manager,
        workspace=tmp_path,
        parent_id=parent_id,
        parent_bytes=_stored_path(test_db_manager, parent_id).read_bytes(),
        parent_tags=_tag_names(test_db_manager, parent_id),
    )


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when(parsers.parse("元画像から矩形 {x:d},{y:d},{width:d},{height:d} を切り出して保存する"))
def when_crop_saved(ctx: CropContext, x: int, y: int, width: int, height: int) -> None:
    _crop(ctx, CropRect(x=x, y=y, width=width, height=height), None)


@when(
    parsers.parse(
        '元画像から矩形 {x:d},{y:d},{width:d},{height:d} をレーティング "{rating}" で切り出して保存する'
    )
)
def when_crop_saved_with_rating(
    ctx: CropContext, x: int, y: int, width: int, height: int, rating: str
) -> None:
    _crop(ctx, CropRect(x=x, y=y, width=width, height=height), rating)


@when(parsers.parse('クロップ画像のレーティングを "{rating}" に変更する'))
def when_child_rating_changed(ctx: CropContext, rating: str) -> None:
    assert ctx.child_id is not None
    ctx.db_manager.annotation_repo.update_manual_rating(ctx.child_id, rating)


@when(parsers.parse("クロップ画像の処理済み画像を解像度 {resolution:d} で登録する"))
def when_processed_image_registered(ctx: CropContext, resolution: int) -> None:
    assert ctx.child_id is not None
    child_path = _stored_path(ctx.db_manager, ctx.child_id)
    destination_dir = ctx.workspace / "processed"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{child_path.stem}_{resolution}.webp"
    with Image.open(child_path) as image:
        resized = image.copy()
        resized.thumbnail((resolution, resolution))
        resized.save(destination)
        width, height = resized.size
    processed_id = ctx.db_manager.register_processed_image(
        ctx.child_id,
        destination,
        {
            "width": width,
            "height": height,
            "has_alpha": False,
            "mode": "RGB",
            "filename": destination.name,
        },
    )
    assert processed_id is not None
    ctx.processed_name = destination.name
    ctx.exported_stem = destination.stem


@when("クロップ画像を学習用データセットとしてエクスポートする")
def when_child_exported(ctx: CropContext) -> None:
    assert ctx.child_id is not None
    service = DatasetExportService(
        config_service=Mock(),
        file_system_manager=ctx.fsm,
        db_manager=ctx.db_manager,
        search_processor=Mock(),
    )
    ctx.export_dir = ctx.workspace / "export"
    report = service.export_dataset_all_formats(
        [ctx.child_id], ctx.export_dir, resolution=EXPORT_RESOLUTION
    )
    assert report.failures == {}, report.failures


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


@then("クロップ画像は元画像とは別の画像 ID で登録される")
def then_child_has_independent_id(ctx: CropContext) -> None:
    assert ctx.error is None
    assert ctx.child_id is not None
    assert ctx.child_id != ctx.parent_id
    assert ctx.db_manager.get_image_metadata(ctx.child_id) is not None


@then(parsers.parse("切り出したファイルの実寸は {width:d}x{height:d} である"))
def then_child_file_size(ctx: CropContext, width: int, height: int) -> None:
    assert ctx.child_id is not None
    with Image.open(_stored_path(ctx.db_manager, ctx.child_id)) as child_image:
        assert child_image.size == (width, height)


@then("元画像のファイルとタグとレーティングは変わらない")
def then_parent_unchanged(ctx: CropContext) -> None:
    assert _stored_path(ctx.db_manager, ctx.parent_id).read_bytes() == ctx.parent_bytes
    assert _tag_names(ctx.db_manager, ctx.parent_id) == ctx.parent_tags
    assert _manual_rating(ctx.db_manager, ctx.parent_id) == PARENT_RATING


@then("親子関係に切り出し座標と由来が保存される")
def then_relation_saved(ctx: CropContext) -> None:
    children = ctx.db_manager.get_crop_children(ctx.parent_id)
    assert len(children) == 1
    relation = children[0]
    assert relation.child_image_id == ctx.child_id
    assert (relation.x, relation.y, relation.width, relation.height) == (100, 100, 640, 480)
    assert relation.origin == "manual"


@then(parsers.parse('クロップ画像のレーティングは "{rating}" である'))
def then_child_rating(ctx: CropContext, rating: str) -> None:
    assert ctx.child_id is not None
    assert _manual_rating(ctx.db_manager, ctx.child_id) == rating


@then(parsers.parse('元画像のレーティングは "{rating}" のままである'))
def then_parent_rating_unchanged(ctx: CropContext, rating: str) -> None:
    assert _manual_rating(ctx.db_manager, ctx.parent_id) == rating


@then("ValueError が発生する")
def then_value_error(ctx: CropContext) -> None:
    assert isinstance(ctx.error, ValueError)
    assert ctx.child_id is None


@then("画像件数とクロップ関係件数と保存ファイル数は変わらない")
def then_no_side_effects(ctx: CropContext) -> None:
    assert _counts(ctx) == ctx.baseline


@then("エクスポート先にクロップ画像とタグファイルが出力される")
def then_export_written(ctx: CropContext) -> None:
    assert ctx.export_dir is not None
    assert (ctx.export_dir / ctx.processed_name).is_file()
    tag_file = ctx.export_dir / f"{ctx.exported_stem}.txt"
    assert tag_file.is_file()
    assert set(tag_file.read_text(encoding="utf-8").split(", ")) == set(PARENT_TAGS)
