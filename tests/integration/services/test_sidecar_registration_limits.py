"""GUI / 共通登録入口の sidecar 制限と永続化を実 DB で検証 (#1374)。"""

import os
from pathlib import Path

import pytest
from PIL import Image as PILImage
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from lorairo.annotation.sidecar_reader import SIDECAR_MAX_BYTES
from lorairo.database.db_manager import ImageDatabaseManager, RegistrationOutcome
from lorairo.database.schema import Base, Caption, Image, Tag
from lorairo.gui.workers.registration_worker import DatabaseRegistrationWorker
from lorairo.services.configuration_service import ConfigurationService
from lorairo.utils.log import logger

pytestmark = pytest.mark.integration


@pytest.fixture
def sidecar_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'registration.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    manager = ImageDatabaseManager(config_service=ConfigurationService(), session_factory=factory)
    manager.annotation_repo._merged_reader_initialized = True
    try:
        yield manager, factory
    finally:
        engine.dispose()


@pytest.mark.parametrize("entry", ["worker", "common"])
@pytest.mark.parametrize("bad_suffix", [".txt", ".caption"])
@pytest.mark.parametrize("fault", ["link", "fifo", "oversized", "directory", "unreadable"])
@pytest.mark.timeout(15)
def test_invalid_sidecar_preserves_sibling_image_and_batch_followup(
    tmp_path, sidecar_db, fs_manager, monkeypatch, entry, bad_suffix, fault
):
    manager, factory = sidecar_db
    source = tmp_path / "source"
    source.mkdir()
    first = source / "first.png"
    followup = source / "followup.png"
    PILImage.new("RGB", (64, 64), "red").save(first)
    PILImage.new("RGB", (80, 64), "blue").save(followup)
    invalid = first.with_suffix(bad_suffix)
    private = tmp_path / "private.txt"
    private.write_text("PRIVATECONTENTSHOULDNOTIMPORT")
    if fault == "link":
        invalid.symlink_to(private)
    elif fault == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("POSIX FIFO")
        os.mkfifo(invalid)
    elif fault == "oversized":
        invalid.write_bytes(b"partial tag," + b"x" * SIDECAR_MAX_BYTES)
    elif fault == "directory":
        invalid.mkdir()
    else:
        invalid.write_text("PRIVATECONTENTSHOULDNOTIMPORT")
        real_open = os.open

        def unreadable(path, flags, *args, **kwargs):
            if Path(path) == invalid:
                raise PermissionError("PRIVATECONTENTSHOULDNOTIMPORT")
            return real_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(os, "open", unreadable)
    sibling_suffix = ".caption" if bad_suffix == ".txt" else ".txt"
    first.with_suffix(sibling_suffix).write_text("normal sibling")
    followup.with_suffix(".txt").write_text("followup tag")
    followup.with_suffix(".caption").write_text("followup caption")
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)), level="DEBUG", format="{message}")
    try:
        if entry == "worker":
            monkeypatch.setattr(fs_manager, "get_image_files", lambda _: iter([first, followup]))
            result = DatabaseRegistrationWorker(source, manager, fs_manager).execute()
            assert result.error_count == 0
            assert result.registered_count + result.variant_count == 2
            assert result.processed_paths == [first, followup]
        else:
            for image in (first, followup):
                result = manager.register_image_with_side_effects(image, fs_manager)
                assert result.outcome in (RegistrationOutcome.REGISTERED, RegistrationOutcome.VARIANT)
    finally:
        logger.remove(sink)

    # 新しい session から再取得し、モック結果ではなく永続化された実体を確認する。
    with factory() as session:
        images = {row.filename: row.id for row in session.scalars(select(Image))}
        assert set(images) == {first.name, followup.name}
        tags = list(session.scalars(select(Tag.tag).where(Tag.image_id == images[first.name])))
        captions = list(
            session.scalars(select(Caption.caption).where(Caption.image_id == images[first.name]))
        )
        assert tags == (["normal sibling"] if bad_suffix == ".caption" else [])
        assert captions == (["normal sibling"] if bad_suffix == ".txt" else [])
        assert list(session.scalars(select(Tag.tag).where(Tag.image_id == images[followup.name]))) == [
            "followup tag"
        ]
        assert list(
            session.scalars(select(Caption.caption).where(Caption.image_id == images[followup.name]))
        ) == ["followup caption"]
        assert private.read_text() not in " ".join(session.scalars(select(Tag.tag)))
        assert private.read_text() not in " ".join(session.scalars(select(Caption.caption)))
    assert any(invalid.name in line and "スキップ" in line for line in messages)
    assert all(
        "PRIVATECONTENTSHOULDNOTIMPORT" not in line and "partial tag" not in line for line in messages
    )


@pytest.mark.parametrize("entry", ["worker", "common"])
@pytest.mark.parametrize("size", [SIDECAR_MAX_BYTES - 1, SIDECAR_MAX_BYTES, SIDECAR_MAX_BYTES + 1])
def test_byte_limit_never_saves_partial_tags_or_captions(
    tmp_path, sidecar_db, fs_manager, monkeypatch, entry, size
):
    manager, factory = sidecar_db
    image = tmp_path / "boundary.png"
    PILImage.new("RGB", (64, 64), "red").save(image)
    image.with_suffix(".txt").write_bytes(b"boundary tag".ljust(size, b" "))
    image.with_suffix(".caption").write_bytes(b"boundary caption".ljust(size, b" "))
    if entry == "worker":
        monkeypatch.setattr(fs_manager, "get_image_files", lambda _: iter([image]))
        result = DatabaseRegistrationWorker(tmp_path, manager, fs_manager).execute()
        assert result.error_count == 0
        assert result.registered_count == 1
    else:
        result = manager.register_image_with_side_effects(image, fs_manager)
        assert result.outcome is RegistrationOutcome.REGISTERED
    with factory() as session:
        assert len(list(session.scalars(select(Image)))) == 1
        assert list(session.scalars(select(Tag.tag))) == (
            ["boundary tag"] if size <= SIDECAR_MAX_BYTES else []
        )
        assert list(session.scalars(select(Caption.caption))) == (
            ["boundary caption"] if size <= SIDECAR_MAX_BYTES else []
        )
