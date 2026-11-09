"""ComfyUI 生成メタデータの DB 再解析テスト (ADR 0105 / 0106, Issue #1503)。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image as PILImage
from PIL import PngImagePlugin
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.schema import Base, GenerationMetadataSource, Image
from lorairo.domain.generation_metadata import (
    GenerationMetadataResult,
    GenerationMetadataStatus,
)
from lorairo.domain.generation_metadata import (
    GenerationMetadataSource as DomainSource,
)
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.generation_metadata_parser import PARSER_COMFYUI, SOURCE_KIND_PNG_TEXT, TOOL_COMFYUI

pytestmark = pytest.mark.unit

COMFY_SINGLE_PROMPT = json.dumps(
    {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "anime_v2.safetensors"}},
        "2": {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": "char_lora.safetensors",
                "strength_model": 0.8,
                "strength_clip": 0.8,
                "model": ["1", 0],
                "clip": ["1", 1],
            },
        },
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "1girl, smile", "clip": ["2", 1]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "bad quality", "clip": ["2", 1]}},
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 777,
                "steps": 24,
                "cfg": 6.5,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["2", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
            },
        },
    }
)


@pytest.fixture
def manager_and_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gen_meta.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    manager = ImageDatabaseManager(config_service=ConfigurationService(), session_factory=factory)
    manager.annotation_repo._merged_reader_initialized = True
    try:
        yield manager, factory
    finally:
        engine.dispose()


def _create_comfy_png(path: Path, prompt_json: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    info = PngImagePlugin.PngInfo()
    info.add_text("prompt", prompt_json)
    PILImage.new("RGB", (16, 16), "blue").save(path, "PNG", pnginfo=info)
    return path


def _insert_stored_image(factory, image_path: Path, uuid: str = "comfy-1") -> int:
    with factory() as session:
        img = Image(
            uuid=uuid,
            phash=f"phash-{uuid}",
            original_image_path=str(image_path),
            stored_image_path=str(image_path),
            width=16,
            height=16,
            format="PNG",
            extension=".png",
            filename=image_path.name,
        )
        session.add(img)
        session.commit()
        return int(img.id)


def test_analyze_generation_metadata_force_upgrades_v1_comfyui_unsupported_to_v2_parsed(
    tmp_path: Path, manager_and_factory
) -> None:
    manager, factory = manager_and_factory
    image_path = _create_comfy_png(tmp_path / "comfy.png", COMFY_SINGLE_PROMPT)
    image_id = _insert_stored_image(factory, image_path)

    # parser v1 時点で保存された ComfyUI の unsupported 行を再現
    v1_result = GenerationMetadataResult(
        status=GenerationMetadataStatus.UNSUPPORTED,
        parser_name=PARSER_COMFYUI,
        parser_version="1",
        tool=TOOL_COMFYUI,
        sources=(DomainSource(SOURCE_KIND_PNG_TEXT, "prompt", COMFY_SINGLE_PROMPT),),
    )
    manager.save_generation_metadata(image_id, v1_result)

    before_row = manager.get_generation_metadata(image_id)
    assert before_row is not None
    assert before_row.status == "unsupported"
    assert before_row.parser_version == "1"
    assert before_row.positive_prompt is None

    # force=False では解析済みのためスキップされる
    skipped = manager.analyze_generation_metadata([image_id], force=False)
    assert [(item.image_id, item.action) for item in skipped] == [(image_id, "skipped_analyzed")]

    # force=True で再解析すると v2 の parsed 結果に置き換わり、保存済みの原データは変わらない
    analyzed = manager.analyze_generation_metadata([image_id], force=True)
    assert [(item.image_id, item.action, item.status, item.tool) for item in analyzed] == [
        (image_id, "analyzed", GenerationMetadataStatus.PARSED, TOOL_COMFYUI)
    ]

    after_row = manager.get_generation_metadata(image_id)
    assert after_row is not None
    assert after_row.status == "parsed"
    assert after_row.parser_name == PARSER_COMFYUI
    assert after_row.parser_version == "2"
    assert after_row.tool == TOOL_COMFYUI
    assert after_row.positive_prompt == "1girl, smile"
    assert after_row.negative_prompt == "bad quality"
    assert after_row.model_name == "anime_v2.safetensors"
    assert after_row.seed == "777"
    assert after_row.steps == 24
    assert after_row.sampler == "dpmpp_2m"
    assert after_row.cfg_scale == 6.5
    assert json.loads(after_row.loras_json or "[]") == [
        {"name": "char_lora.safetensors", "weight": "0.8", "kind": "lora"}
    ]
    assert json.loads(after_row.extra_json or "{}") == {
        "scheduler": "karras",
        "denoise": "1.0",
    }

    with factory() as session:
        sources = list(session.scalars(select(GenerationMetadataSource)))
        assert len(sources) == 1
        assert sources[0].raw_text == COMFY_SINGLE_PROMPT
