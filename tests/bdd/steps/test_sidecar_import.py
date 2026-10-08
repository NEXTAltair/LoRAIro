"""画像登録時の sidecar スキップをユーザーフローとして固定 (#1374)。"""

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from PIL import Image as PILImage
from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy import select

from lorairo.annotation.sidecar_reader import SIDECAR_MAX_BYTES
from lorairo.database.db_manager import RegistrationOutcome
from lorairo.database.schema import Caption, Image, Tag
from lorairo.gui.workers.registration_worker import DatabaseRegistrationWorker

scenarios("../features/sidecar_import.feature")


@dataclass
class SidecarImportContext:
    images: list[Path] = field(default_factory=list)
    bad_suffix: str = ""


@pytest.fixture
def sidecar_context():
    return SidecarImportContext()


@given(parsers.parse('異常な "{suffix}" と正常なもう片方の付属ファイルを持つ画像がある'))
def first_image(sidecar_context, tmp_path, suffix):
    image = tmp_path / "first.png"
    PILImage.new("RGB", (64, 64), "red").save(image)
    image.with_suffix(suffix).write_bytes(b"partial tag," + b"x" * SIDECAR_MAX_BYTES)
    other_suffix = ".caption" if suffix == ".txt" else ".txt"
    image.with_suffix(other_suffix).write_text("normal sibling")
    sidecar_context.images.append(image)
    sidecar_context.bad_suffix = suffix


@given("正常な付属テキストを持つ後続画像がある")
def followup_image(sidecar_context, tmp_path):
    image = tmp_path / "followup.png"
    PILImage.new("RGB", (80, 64), "blue").save(image)
    image.with_suffix(".txt").write_text("followup tag")
    image.with_suffix(".caption").write_text("followup caption")
    sidecar_context.images.append(image)


@when(parsers.parse('"{entry}" 経路で画像を登録する'))
def register_images(sidecar_context, test_db_manager, fs_manager, monkeypatch, entry):
    test_db_manager.annotation_repo._merged_reader_initialized = True
    if entry == "worker":
        monkeypatch.setattr(fs_manager, "get_image_files", lambda _: iter(sidecar_context.images))
        result = DatabaseRegistrationWorker(
            sidecar_context.images[0].parent, test_db_manager, fs_manager
        ).execute()
        assert result.error_count == 0
        assert result.registered_count + result.variant_count == 2
        assert result.processed_paths == sidecar_context.images
    else:
        for image in sidecar_context.images:
            result = test_db_manager.register_image_with_side_effects(image, fs_manager)
            assert result.outcome in (RegistrationOutcome.REGISTERED, RegistrationOutcome.VARIANT)


@then("画像2枚と正常な付属テキストのみがDBに保存される")
def persisted_images_and_annotations(sidecar_context, db_session_factory):
    with db_session_factory() as session:
        images = {image.filename: image.id for image in session.scalars(select(Image))}
        assert set(images) == {image.name for image in sidecar_context.images}
        first_id = images[sidecar_context.images[0].name]
        first_tags = list(session.scalars(select(Tag.tag).where(Tag.image_id == first_id)))
        first_captions = list(session.scalars(select(Caption.caption).where(Caption.image_id == first_id)))
        assert first_tags == (["normal sibling"] if sidecar_context.bad_suffix == ".caption" else [])
        assert first_captions == (["normal sibling"] if sidecar_context.bad_suffix == ".txt" else [])
        followup_id = images[sidecar_context.images[1].name]
        assert list(session.scalars(select(Tag.tag).where(Tag.image_id == followup_id))) == ["followup tag"]
        assert list(session.scalars(select(Caption.caption).where(Caption.image_id == followup_id))) == [
            "followup caption"
        ]
