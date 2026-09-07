"""クロップ子画像が既存の学習用エクスポートに乗ることを検証する統合テスト。

Issue #1344 の受け入れ条件「子画像のタグ・レーティングが親から独立して管理され、
既存の学習用エクスポート (dataset_export_service) で子画像が出力される」を、
実 SQLite + 実ファイルで固定する。
"""

from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.schema import TagAnnotationData
from lorairo.domain.crop_request import CropCreateRequest, CropRect
from lorairo.filesystem import FileSystemManager
from lorairo.services.crop_service import create_crop_image
from lorairo.services.dataset_export_service import DatasetExportService

pytestmark = pytest.mark.integration

EXPORT_RESOLUTION = 768


@pytest.fixture
def export_service(
    test_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
) -> DatasetExportService:
    """実 DB / 実ファイルシステムを使う DatasetExportService。"""
    return DatasetExportService(
        config_service=Mock(),
        file_system_manager=fs_manager,
        db_manager=test_db_manager,
        search_processor=Mock(),
    )


def _register_processed_copy(
    db_manager: ImageDatabaseManager,
    image_id: int,
    source_path: Path,
    destination_dir: Path,
    resolution: int,
) -> Path:
    """子画像を指定解像度にリサイズして実配置し、processed_images へ登録する。"""
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{source_path.stem}_{resolution}.webp"
    with Image.open(source_path) as image:
        resized = image.copy()
        resized.thumbnail((resolution, resolution))
        resized.save(destination)
        width, height = resized.size
    processed_id = db_manager.register_processed_image(
        image_id,
        destination,
        {"width": width, "height": height, "has_alpha": False, "mode": "RGB", "filename": destination.name},
    )
    assert processed_id is not None
    return destination


def test_crop_child_is_exported_with_its_own_tags(
    test_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    export_service: DatasetExportService,
    tmp_path: Path,
) -> None:
    """クロップ子画像が画像 + タグ txt としてエクスポートされる。"""
    source = tmp_path / "parent.png"
    Image.new("RGB", (1600, 1200), (30, 90, 180)).save(source)
    registered = test_db_manager.register_original_image(source, fs_manager)
    assert registered is not None
    parent_id = registered[0]

    parent_tags: list[TagAnnotationData] = [
        {
            "tag": "solo",
            "tag_id": None,
            "model_id": None,
            "existing": True,
            "is_edited_manually": False,
            "confidence_score": None,
        },
        {
            "tag": "outdoors",
            "tag_id": None,
            "model_id": None,
            "existing": True,
            "is_edited_manually": False,
            "confidence_score": None,
        },
    ]
    test_db_manager.save_tags(parent_id, parent_tags)
    test_db_manager.annotation_repo.update_manual_rating(parent_id, "PG")

    child_id = create_crop_image(
        CropCreateRequest(
            parent_image_id=parent_id,
            rect=CropRect(x=100, y=100, width=1024, height=1024),
            tags=("solo",),
            rating="R",
        ),
        db_manager=test_db_manager,
        fsm=fs_manager,
    )

    child_metadata = test_db_manager.get_image_metadata(child_id)
    assert child_metadata is not None
    child_path = Path(str(child_metadata["stored_image_path"]))
    processed_path = _register_processed_copy(
        test_db_manager,
        child_id,
        child_path,
        tmp_path / "processed",
        EXPORT_RESOLUTION,
    )

    output_dir = tmp_path / "export"
    report = export_service.export_dataset_all_formats([child_id], output_dir, resolution=EXPORT_RESOLUTION)

    assert report.failures == {}
    exported_image = output_dir / processed_path.name
    exported_tags = output_dir / f"{processed_path.stem}.txt"
    assert exported_image.is_file()
    assert exported_tags.is_file()
    assert exported_tags.read_text(encoding="utf-8").strip() == "solo"

    # 子のタグ・レーティングは親から独立している。
    parent_tag_names = {tag["tag"] for tag in test_db_manager.get_image_annotations(parent_id)["tags"]}
    child_tag_names = {tag["tag"] for tag in test_db_manager.get_image_annotations(child_id)["tags"]}
    assert parent_tag_names == {"solo", "outdoors"}
    assert child_tag_names == {"solo"}
