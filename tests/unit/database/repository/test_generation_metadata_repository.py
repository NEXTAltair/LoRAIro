"""`GenerationMetadataRepository` の単体テスト (ADR 0105, Issue #1481)。"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.exc import IntegrityError

from lorairo.database.repository.generation_metadata import GenerationMetadataRepository
from lorairo.database.schema import Image
from lorairo.domain.generation_metadata import (
    GenerationMetadataResult,
    GenerationMetadataSource,
    GenerationMetadataStatus,
    GenerationParameters,
    LoraReference,
)

pytestmark = pytest.mark.unit

RAW = "cat,\n(dog:1.2)\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 1"


@pytest.fixture
def repo(db_session_factory) -> GenerationMetadataRepository:
    return GenerationMetadataRepository(session_factory=db_session_factory)


def _insert_image(db_session_factory, uuid: str = "img") -> int:
    with db_session_factory() as session:
        image = Image(
            uuid=uuid,
            phash=f"phash-{uuid}",
            original_image_path=f"/tmp/{uuid}.png",
            stored_image_path=f"/tmp/{uuid}.png",
            width=8,
            height=8,
            format="PNG",
            extension=".png",
            filename=f"{uuid}.png",
        )
        session.add(image)
        session.commit()
        image_id: int = image.id
    return image_id


def _parsed_result(raw: str = RAW) -> GenerationMetadataResult:
    return GenerationMetadataResult(
        status=GenerationMetadataStatus.PARSED,
        parser_name="sd_webui",
        tool="sd_webui",
        sources=(GenerationMetadataSource("png_text", "parameters", raw),),
        parameters=GenerationParameters(
            positive_prompt="cat,\n(dog:1.2)",
            seed="18446744073709551615",
            steps=20,
            sampler="Euler a",
            cfg_scale=7.0,
            loras=(LoraReference("styleA", "0.8"),),
            extra={"Size": "512x512"},
        ),
    )


def test_save_and_read_back_parsed_result(repo, db_session_factory) -> None:
    image_id = _insert_image(db_session_factory)

    repo.save_result(image_id, _parsed_result())

    row = repo.get_by_image_id(image_id)
    assert row is not None
    assert row.status == "parsed"
    assert row.tool == "sd_webui"
    assert row.parser_name == "sd_webui"
    assert row.parser_version == "1"
    assert row.positive_prompt == "cat,\n(dog:1.2)"
    assert row.seed == "18446744073709551615"
    assert row.steps == 20
    assert row.cfg_scale == 7.0
    assert json.loads(row.loras_json or "[]") == [{"name": "styleA", "weight": "0.8", "kind": "lora"}]
    assert json.loads(row.extra_json or "{}") == {"Size": "512x512"}
    assert row.input_sha256 == _parsed_result().input_sha256
    assert row.analyzed_at is not None

    sources = repo.get_sources(image_id)
    assert [(s.source_kind, s.source_key, s.raw_text) for s in sources] == [("png_text", "parameters", RAW)]
    assert sources[0].raw_bytes is None


def test_unanalyzed_image_returns_none(repo, db_session_factory) -> None:
    image_id = _insert_image(db_session_factory)
    assert repo.get_by_image_id(image_id) is None
    assert repo.get_sources(image_id) == []


def test_no_metadata_is_stored_as_distinct_state(repo, db_session_factory) -> None:
    image_id = _insert_image(db_session_factory)

    repo.save_result(
        image_id, GenerationMetadataResult(GenerationMetadataStatus.NO_METADATA, parser_name="none")
    )

    row = repo.get_by_image_id(image_id)
    assert row is not None
    assert row.status == "no_metadata"
    assert row.tool is None
    assert row.input_sha256 is None
    assert repo.get_sources(image_id) == []


def test_resave_replaces_result_but_keeps_existing_raw(repo, db_session_factory) -> None:
    image_id = _insert_image(db_session_factory)
    repo.save_result(image_id, _parsed_result())

    # 再解析: 同じ取得元の原データは書き換えず、解析結果だけ置き換える
    failed = GenerationMetadataResult(
        GenerationMetadataStatus.FAILED,
        parser_name="none",
        sources=(
            GenerationMetadataSource("png_text", "parameters", "changed"),
            GenerationMetadataSource("exif", "UserComment", None, raw_bytes=b"\xff"),
        ),
        error_message="boom",
    )
    repo.save_result(image_id, failed)

    row = repo.get_by_image_id(image_id)
    assert row is not None
    assert row.status == "failed"
    assert row.positive_prompt is None
    assert row.steps is None
    assert row.loras_json is None
    assert row.error_message == "boom"
    sources = repo.get_sources(image_id)
    assert [(s.source_key, s.raw_text, s.raw_bytes) for s in sources] == [
        ("parameters", RAW, None),
        ("UserComment", None, b"\xff"),
    ]


def test_status_check_constraint_rejects_unknown_status(db_session_factory) -> None:
    from lorairo.database.schema import GenerationMetadata

    image_id = _insert_image(db_session_factory)
    with db_session_factory() as session:
        session.add(
            GenerationMetadata(image_id=image_id, status="bogus", parser_name="x", parser_version="1")
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_one_result_row_per_image(db_session_factory) -> None:
    from lorairo.database.schema import GenerationMetadata

    image_id = _insert_image(db_session_factory)
    with db_session_factory() as session:
        for _ in range(2):
            session.add(
                GenerationMetadata(image_id=image_id, status="parsed", parser_name="x", parser_version="1")
            )
        with pytest.raises(IntegrityError):
            session.commit()
