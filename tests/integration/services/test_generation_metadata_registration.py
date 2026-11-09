"""登録経路での生成メタデータの読み取りと再解析 (ADR 0106, Issue #1482)。

GUI worker / 共通入口 (API・CLI が使う ``register_image_with_side_effects``) の両方で、
実 DB に生成メタデータが保存され、失敗しても登録が続くことを確認する。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image as PILImage
from PIL import PngImagePlugin
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager, RegistrationOutcome
from lorairo.database.schema import Base, Caption, GenerationMetadata, GenerationMetadataSource, Image, Tag
from lorairo.domain.generation_metadata import GenerationMetadataStatus
from lorairo.gui.workers.registration_worker import DatabaseRegistrationWorker
from lorairo.public_api.images import _register_into_db
from lorairo.services.configuration_service import ConfigurationService

pytestmark = pytest.mark.integration

A1111_TEXT = (
    "1girl, (smile:1.2)\nNegative prompt: lowres\n"
    "Steps: 20, Sampler: Euler a, CFG scale: 7, Seed: 42, Model: animeModel"
)


@pytest.fixture
def gen_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'registration.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    manager = ImageDatabaseManager(config_service=ConfigurationService(), session_factory=factory)
    manager.annotation_repo._merged_reader_initialized = True
    try:
        yield manager, factory
    finally:
        engine.dispose()


def _png(path: Path, parameters: str | None, color: str = "red", size: tuple[int, int] = (64, 64)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    info = PngImagePlugin.PngInfo()
    if parameters is not None:
        info.add_text("parameters", parameters)
    PILImage.new("RGB", size, color).save(path, "PNG", pnginfo=info)
    return path


def _register(entry: str, manager, fs_manager, monkeypatch, images: list[Path], source: Path) -> None:
    if entry == "worker":
        monkeypatch.setattr(fs_manager, "get_image_files", lambda _: iter(images))
        result = DatabaseRegistrationWorker(source, manager, fs_manager).execute()
        assert result.error_count == 0
    else:
        api_result = _register_into_db(manager, fs_manager, images)
        assert api_result.failed == 0


def _rows(factory) -> dict[str, GenerationMetadata]:
    with factory() as session:
        names = {row.id: row.filename for row in session.scalars(select(Image))}
        return {names[row.image_id]: row for row in session.scalars(select(GenerationMetadata))}


@pytest.mark.parametrize("entry", ["worker", "common"])
def test_registration_saves_generation_metadata_on_every_entry(
    tmp_path, gen_db, fs_manager, monkeypatch, entry
) -> None:
    manager, factory = gen_db
    source = tmp_path / "source"
    generated = _png(source / "gen.png", A1111_TEXT, "red")
    # 単色画像は pHash が同じになるため、寸法を変えて重複にならないようにする
    plain = _png(source / "plain.png", None, "blue", size=(80, 64))

    _register(entry, manager, fs_manager, monkeypatch, [generated, plain], source)

    rows = _rows(factory)
    assert rows["gen.png"].status == "parsed"
    assert rows["gen.png"].tool == "sd_webui"
    assert rows["gen.png"].positive_prompt == "1girl, (smile:1.2)"
    assert rows["plain.png"].status == "no_metadata"
    with factory() as session:
        raw = list(session.scalars(select(GenerationMetadataSource.raw_text)))
        assert raw == [A1111_TEXT]
        # 生成プロンプトは学習用のタグ / キャプションへ自動で反映しない (付くのは ai generated だけ, ADR 0107)
        assert list(session.scalars(select(Tag.tag))) == ["ai generated"]
        assert list(session.scalars(select(Caption.caption))) == []


def test_reimport_keeps_existing_raw_and_analysis(tmp_path, gen_db, fs_manager) -> None:
    manager, factory = gen_db
    first = _png(tmp_path / "a" / "img.png", A1111_TEXT)
    # 画素が同じで生成情報だけ違う画像 = 重複 (再取り込み)
    second = _png(tmp_path / "b" / "img.png", "changed\nSteps: 1, Sampler: x, CFG scale: 1, Seed: 1")

    assert (
        manager.register_image_with_side_effects(first, fs_manager).outcome
        is RegistrationOutcome.REGISTERED
    )
    assert (
        manager.register_image_with_side_effects(second, fs_manager).outcome
        is RegistrationOutcome.DUPLICATE
    )

    rows = _rows(factory)
    assert rows["img.png"].positive_prompt == "1girl, (smile:1.2)"
    with factory() as session:
        assert list(session.scalars(select(GenerationMetadataSource.raw_text))) == [A1111_TEXT]


def test_reimport_analyzes_image_registered_before_feature(tmp_path, gen_db, fs_manager) -> None:
    manager, factory = gen_db
    image = _png(tmp_path / "img.png", A1111_TEXT)
    result = manager.register_image_with_side_effects(image, fs_manager)
    # 機能追加前に登録された画像を模して、解析結果と原データを消す
    with factory() as session:
        session.query(GenerationMetadataSource).delete()
        session.query(GenerationMetadata).delete()
        session.commit()

    manager.register_image_with_side_effects(image, fs_manager)

    evidence = manager.get_generation_evidence(result.image_id or 0)
    assert evidence is not None
    assert evidence.status is GenerationMetadataStatus.PARSED
    assert evidence.is_ai_generated is True


def test_save_failure_does_not_stop_registration(tmp_path, gen_db, fs_manager, monkeypatch) -> None:
    manager, factory = gen_db
    image = _png(tmp_path / "img.png", A1111_TEXT)

    def broken_save(image_id, result):
        raise OperationalError("INSERT", {}, Exception("database is locked"))

    monkeypatch.setattr(manager.generation_metadata_repo, "save_result", broken_save)

    result = manager.register_image_with_side_effects(image, fs_manager)

    assert result.outcome is RegistrationOutcome.REGISTERED
    assert _rows(factory) == {}
    assert manager.get_generation_evidence(result.image_id or 0) is None


def test_unreadable_metadata_is_failed_but_image_is_registered(
    tmp_path, gen_db, fs_manager, monkeypatch
) -> None:
    manager, factory = gen_db
    image = _png(tmp_path / "img.png", A1111_TEXT)

    def broken_read(path):
        raise OSError("boom")

    monkeypatch.setattr("lorairo.services.generation_metadata_parser.read_generation_sources", broken_read)

    result = manager.register_image_with_side_effects(image, fs_manager)

    assert result.outcome is RegistrationOutcome.REGISTERED
    assert _rows(factory)["img.png"].status == "failed"


def test_analyze_generation_metadata_reanalysis_policy(tmp_path, gen_db, fs_manager) -> None:
    manager, factory = gen_db
    image = _png(tmp_path / "img.png", A1111_TEXT)
    image_id = manager.register_image_with_side_effects(image, fs_manager).image_id
    assert image_id is not None
    with factory() as session:
        session.query(GenerationMetadata).delete()
        session.commit()

    assert manager.count_unanalyzed_generation_images() == 1
    assert manager.get_unanalyzed_generation_image_ids(limit=10) == [image_id]

    items = manager.analyze_generation_metadata([image_id, 9999])
    assert [(i.image_id, i.action, i.status) for i in items] == [
        (image_id, "analyzed", GenerationMetadataStatus.PARSED),
        (9999, "not_found", None),
    ]
    assert manager.count_unanalyzed_generation_images() == 0

    # 解析済みは既定で飛ばし、force で置き換える (原データは 1 件のまま)
    assert manager.analyze_generation_metadata([image_id])[0].action == "skipped_analyzed"
    assert manager.analyze_generation_metadata([image_id], force=True)[0].action == "analyzed"
    with factory() as session:
        assert len(list(session.scalars(select(GenerationMetadataSource)))) == 1


def test_analyze_generation_metadata_reports_missing_file(tmp_path, gen_db, fs_manager) -> None:
    manager, factory = gen_db
    image = _png(tmp_path / "img.png", A1111_TEXT)
    image_id = manager.register_image_with_side_effects(image, fs_manager).image_id
    assert image_id is not None
    with factory() as session:
        stored = session.get(Image, image_id)
        assert stored is not None
        Path(stored.stored_image_path).unlink()

    assert manager.analyze_generation_metadata([image_id], force=True)[0].action == "file_missing"


def test_unanalyzed_cursor_advances_past_missing_file(tmp_path, gen_db, fs_manager) -> None:
    manager, factory = gen_db
    first = manager.register_image_with_side_effects(_png(tmp_path / "a.png", A1111_TEXT), fs_manager)
    second = manager.register_image_with_side_effects(
        _png(tmp_path / "b.png", A1111_TEXT, size=(80, 64)), fs_manager
    )
    assert first.image_id is not None and second.image_id is not None
    with factory() as session:
        session.query(GenerationMetadata).delete()
        stored = session.get(Image, first.image_id)
        assert stored is not None
        Path(stored.stored_image_path).unlink()
        session.commit()

    batch = manager.get_unanalyzed_generation_image_ids(limit=1)
    assert batch == [first.image_id]
    assert manager.analyze_generation_metadata(batch)[0].action == "file_missing"
    # 欠落した画像は未解析のまま残るが、カーソルで先へ進める
    assert manager.get_unanalyzed_generation_image_ids(limit=1) == [first.image_id]
    assert manager.get_unanalyzed_generation_image_ids(limit=1, after_id=first.image_id) == [
        second.image_id
    ]


# --- #1396: ai generated の自動付与 (ADR 0107) ---

COMFY_PROMPT = '{"3": {"class_type": "KSampler", "inputs": {"seed": 1}}}'


def _tags(factory, filename: str) -> list[tuple[str, str | None]]:
    """画像のタグを (tag, モデルの litellm_model_id) で返す。"""
    from lorairo.database.schema import Model

    with factory() as session:
        image_id = session.scalars(select(Image.id).where(Image.filename == filename)).one()
        rows = session.execute(
            select(Tag.tag, Model.litellm_model_id)
            .outerjoin(Model, Model.id == Tag.model_id)
            .where(Tag.image_id == image_id)
            .order_by(Tag.id)
        ).all()
        return [(row[0], row[1]) for row in rows]


def _comfy_png(path: Path, size: tuple[int, int] = (64, 64)) -> Path:
    info = PngImagePlugin.PngInfo()
    info.add_text("prompt", COMFY_PROMPT)
    PILImage.new("RGB", size, "green").save(path, "PNG", pnginfo=info)
    return path


@pytest.mark.parametrize("entry", ["worker", "common"])
def test_ai_generated_tag_is_added_only_with_generation_evidence(
    tmp_path, gen_db, fs_manager, monkeypatch, entry
) -> None:
    manager, factory = gen_db
    source = tmp_path / "source"
    webui = _png(source / "webui.png", A1111_TEXT, size=(64, 64))
    comfy = _comfy_png(source / "comfy.png", size=(72, 64))
    plain = _png(source / "plain.png", None, size=(80, 64))
    # parameters チャンクはあるが SD WebUI 形式ではない (汎用 fallback 一致を根拠にしない)
    loose = _png(source / "loose.png", "1girl, solo", size=(88, 64))

    _register(entry, manager, fs_manager, monkeypatch, [webui, comfy, plain, loose], source)

    assert _tags(factory, "webui.png") == [("ai generated", "__generation_metadata__")]
    assert _tags(factory, "comfy.png") == [("ai generated", "__generation_metadata__")]
    assert _tags(factory, "plain.png") == []
    assert _tags(factory, "loose.png") == []


def test_ai_generated_tag_is_searchable_as_normal_tag(tmp_path, gen_db, fs_manager) -> None:
    from lorairo.database.filter_criteria import ImageFilterCriteria

    manager, _ = gen_db
    tagged = manager.register_image_with_side_effects(_png(tmp_path / "a.png", A1111_TEXT), fs_manager)
    manager.register_image_with_side_effects(_png(tmp_path / "b.png", None, size=(80, 64)), fs_manager)

    records, total = manager.image_repo.get_images_by_filter(ImageFilterCriteria(tags=["ai generated"]))

    assert total == 1
    assert [r["id"] for r in records] == [tagged.image_id]


def test_ai_generated_tag_is_not_duplicated(tmp_path, gen_db, fs_manager) -> None:
    manager, factory = gen_db
    image = _png(tmp_path / "a" / "img.png", A1111_TEXT)
    image.with_suffix(".txt").write_text("1girl, ai_generated", encoding="utf-8")

    manager.register_image_with_side_effects(image, fs_manager)
    # 同じ画像の再取り込み
    again = _png(tmp_path / "b" / "img.png", A1111_TEXT)
    manager.register_image_with_side_effects(again, fs_manager)

    # 関連 .txt (取り込み時に ai generated へ整形される) に既にあるため、自動付与の行は足さない
    assert _tags(factory, "img.png") == [("1girl", None), ("ai generated", None)]


def test_ai_generated_tag_is_added_once_on_reimport(tmp_path, gen_db, fs_manager) -> None:
    manager, factory = gen_db
    manager.register_image_with_side_effects(_png(tmp_path / "a" / "img.png", A1111_TEXT), fs_manager)
    manager.register_image_with_side_effects(_png(tmp_path / "b" / "img.png", A1111_TEXT), fs_manager)

    assert _tags(factory, "img.png") == [("ai generated", "__generation_metadata__")]


def test_soft_rejected_ai_generated_tag_is_not_readded(tmp_path, gen_db, fs_manager) -> None:
    import datetime

    manager, factory = gen_db
    manager.register_image_with_side_effects(_png(tmp_path / "a" / "img.png", A1111_TEXT), fs_manager)
    with factory() as session:
        tag = session.scalars(select(Tag)).one()
        tag.rejected_at = datetime.datetime(2026, 1, 1)
        session.commit()

    manager.register_image_with_side_effects(_png(tmp_path / "b" / "img.png", A1111_TEXT), fs_manager)

    assert _tags(factory, "img.png") == [("ai generated", "__generation_metadata__")]


def test_direct_registration_entry_also_tags(tmp_path, gen_db, fs_manager) -> None:
    """データセット取り込み・クロップ等が使う register_original_image でも同じ動作になる。"""
    manager, factory = gen_db

    registered = manager.register_original_image(_png(tmp_path / "img.png", A1111_TEXT), fs_manager)

    assert registered is not None
    assert _tags(factory, "img.png") == [("ai generated", "__generation_metadata__")]


def test_tag_failure_does_not_stop_registration(tmp_path, gen_db, fs_manager, monkeypatch) -> None:
    manager, factory = gen_db

    def broken_add(image_id):
        raise OperationalError("INSERT", {}, Exception("database is locked"))

    monkeypatch.setattr(manager.generation_metadata_repo, "add_ai_generated_tag", broken_add)

    result = manager.register_image_with_side_effects(_png(tmp_path / "img.png", A1111_TEXT), fs_manager)

    assert result.outcome is RegistrationOutcome.REGISTERED
    assert _tags(factory, "img.png") == []


def test_backfill_and_revoke_after_analyze_metadata(tmp_path, gen_db, fs_manager) -> None:
    """機能追加前の画像に analyze_generation_metadata → apply_ai_generated_tags_batch で付与・取り消しできる (#1502)。"""
    manager, factory = gen_db
    webui = manager.register_image_with_side_effects(
        _png(tmp_path / "webui.png", A1111_TEXT, size=(64, 64)), fs_manager
    )
    plain = manager.register_image_with_side_effects(
        _png(tmp_path / "plain.png", None, size=(80, 64)), fs_manager
    )
    assert webui.image_id is not None and plain.image_id is not None

    # 機能追加前に登録された状態を模して、生成メタデータと自動付与タグを消す
    with factory() as session:
        session.query(Tag).delete()
        session.query(GenerationMetadataSource).delete()
        session.query(GenerationMetadata).delete()
        session.commit()

    # 再解析はタグに触れない (ADR 0106)
    manager.analyze_generation_metadata([webui.image_id, plain.image_id])
    assert _tags(factory, "webui.png") == []

    # dry-run で件数だけ確認し、本番で付与する
    assert manager.apply_ai_generated_tags_batch(dry_run=True).tags_added == 1
    assert _tags(factory, "webui.png") == []

    applied = manager.apply_ai_generated_tags_batch()
    assert (applied.target_images, applied.evidence_images, applied.tags_added) == (2, 1, 1)
    assert _tags(factory, "webui.png") == [("ai generated", "__generation_metadata__")]
    assert _tags(factory, "plain.png") == []

    # 手動タグを足した後、GENERATION_METADATA だけを一括で取り消せる
    manager.add_manual_tag(webui.image_id, "1girl")
    revoked = manager.revoke_ai_generated_tags_batch()
    assert revoked.tags_revoked == 1
    assert _tags(factory, "webui.png") == [("1girl", "__manual_edit__")]
