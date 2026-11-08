"""生成メタデータの parser (ADR 0105, Issue #1481)。

テスト用の画像は Pillow でその場で作る (外部から取得しない)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from lorairo.domain.generation_metadata import (
    GenerationMetadataSource,
    GenerationMetadataStatus,
    LoraReference,
)
from lorairo.services.generation_metadata_parser import (
    EXIF_KEY_USER_COMMENT,
    PARSER_COMFYUI,
    PARSER_NONE,
    PARSER_SD_WEBUI,
    SOURCE_KIND_EXIF,
    SOURCE_KIND_PNG_TEXT,
    TOOL_COMFYUI,
    TOOL_SD_WEBUI,
    extract_generation_metadata,
    parse_generation_sources,
    parse_sd_webui_parameters,
)

pytestmark = pytest.mark.unit

A1111_TEXT = (
    "masterpiece, (best quality:1.2), 1girl,\n"
    "solo, <lora:styleA:0.8> <lora:charB:1>\n"
    "Negative prompt: lowres, bad hands\n"
    "worst quality\n"
    "Steps: 28, Sampler: DPM++ 2M Karras, CFG scale: 7.5, Seed: 18446744073709551615, "
    'Size: 512x768, Model hash: abc123, Model: animeModel_v1, Lora hashes: "styleA: 1111, charB: 2222", '
    "Version: v1.10.1"
)

COMFY_PROMPT = json.dumps(
    {
        "3": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 20}},
        "9": {"class_type": "KSampler", "inputs": {"seed": 2, "steps": 30}},
    }
)
COMFY_WORKFLOW = json.dumps({"nodes": [{"id": 3, "type": "KSampler"}], "links": []})


def _png(path: Path, texts: dict[str, str]) -> Path:
    info = PngImagePlugin.PngInfo()
    for key, value in texts.items():
        info.add_text(key, value)
    Image.new("RGB", (8, 8), "white").save(path, "PNG", pnginfo=info)
    return path


def _jpeg_with_user_comment(path: Path, comment: bytes) -> Path:
    exif = Image.Exif()
    exif.get_ifd(0x8769)[0x9286] = comment
    Image.new("RGB", (8, 8), "white").save(path, "JPEG", exif=exif)
    return path


class TestSdWebuiParameters:
    def test_extracts_common_fields_without_rewriting_prompt(self) -> None:
        params = parse_sd_webui_parameters(A1111_TEXT)

        assert params is not None
        assert params.positive_prompt == (
            "masterpiece, (best quality:1.2), 1girl,\nsolo, <lora:styleA:0.8> <lora:charB:1>"
        )
        assert params.negative_prompt == "lowres, bad hands\nworst quality"
        assert params.steps == 28
        assert params.sampler == "DPM++ 2M Karras"
        assert params.cfg_scale == 7.5
        assert params.seed == "18446744073709551615"
        assert params.model_name == "animeModel_v1"
        assert params.model_hash == "abc123"
        assert params.loras == (
            LoraReference(name="styleA", weight="0.8"),
            LoraReference(name="charB", weight="1"),
        )
        assert params.extra["Size"] == "512x768"
        assert params.extra["Lora hashes"] == "styleA: 1111, charB: 2222"
        assert params.extra["Version"] == "v1.10.1"

    def test_text_without_parameter_line_is_not_sd_webui(self) -> None:
        assert parse_sd_webui_parameters("1girl, solo, smile") is None

    def test_parameter_line_without_steps_is_not_sd_webui(self) -> None:
        assert parse_sd_webui_parameters("1girl\nFoo: 1, Bar: 2, Baz: 3") is None

    def test_missing_negative_prompt_is_none(self) -> None:
        params = parse_sd_webui_parameters("cat\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 1")
        assert params is not None
        assert params.negative_prompt is None
        assert params.positive_prompt == "cat"

    def test_unparsable_values_are_not_guessed(self) -> None:
        params = parse_sd_webui_parameters("cat\nSteps: many, Sampler: Euler, CFG scale: x, Seed: abc")
        assert params is not None
        assert params.steps is None
        assert params.cfg_scale is None
        assert params.seed is None
        assert params.model_name is None


class TestExtractFromImage:
    def test_a1111_png_is_parsed_and_raw_is_kept_verbatim(self, tmp_path: Path) -> None:
        path = _png(tmp_path / "a.png", {"parameters": A1111_TEXT})

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.PARSED
        assert result.tool == TOOL_SD_WEBUI
        assert result.parser_name == PARSER_SD_WEBUI
        assert result.is_ai_generation_evidence is True
        assert result.sources == (GenerationMetadataSource(SOURCE_KIND_PNG_TEXT, "parameters", A1111_TEXT),)
        assert result.input_sha256 is not None
        # 画像ファイルは変更していない (再読み取りで同じ原データ)
        assert extract_generation_metadata(path).sources == result.sources

    def test_plain_png_has_no_metadata(self, tmp_path: Path) -> None:
        path = tmp_path / "plain.png"
        Image.new("RGB", (512, 768), "white").save(path, "PNG")

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.NO_METADATA
        assert result.tool is None
        assert result.parser_name == PARSER_NONE
        assert result.sources == ()
        assert result.input_sha256 is None
        assert result.is_ai_generation_evidence is False

    def test_partial_when_core_field_missing(self, tmp_path: Path) -> None:
        path = _png(tmp_path / "p.png", {"parameters": "cat\nSteps: 20, Sampler: Euler a, Size: 512x512"})

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.PARTIAL
        assert result.tool == TOOL_SD_WEBUI
        assert result.parameters is not None
        assert result.parameters.seed is None

    def test_parameters_without_webui_shape_is_unsupported(self, tmp_path: Path) -> None:
        path = _png(tmp_path / "u.png", {"parameters": "1girl, solo"})

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.UNSUPPORTED
        assert result.tool is None
        assert result.is_ai_generation_evidence is False
        assert result.sources[0].raw_text == "1girl, solo"

    def test_comfyui_is_detected_but_not_merged_into_single_setting(self, tmp_path: Path) -> None:
        path = _png(tmp_path / "c.png", {"prompt": COMFY_PROMPT, "workflow": COMFY_WORKFLOW})

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.UNSUPPORTED
        assert result.tool == TOOL_COMFYUI
        assert result.parser_name == PARSER_COMFYUI
        assert result.parameters is None
        assert result.is_ai_generation_evidence is True
        assert {s.key for s in result.sources} == {"prompt", "workflow"}

    def test_comfyui_with_webui_summary_is_partial(self, tmp_path: Path) -> None:
        path = _png(tmp_path / "cw.png", {"parameters": A1111_TEXT, "prompt": COMFY_PROMPT})

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.PARTIAL
        assert result.tool == TOOL_COMFYUI
        assert result.parameters is not None
        assert result.parameters.steps == 28

    def test_prompt_chunk_that_is_not_comfy_graph_is_unsupported(self, tmp_path: Path) -> None:
        path = _png(tmp_path / "np.png", {"prompt": "1girl, solo"})

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.UNSUPPORTED
        assert result.tool is None
        assert result.is_ai_generation_evidence is False

    def test_jpeg_exif_user_comment_is_parsed(self, tmp_path: Path) -> None:
        comment = b"UNICODE\x00" + A1111_TEXT.encode("utf-16-be")
        path = _jpeg_with_user_comment(tmp_path / "e.jpg", comment)

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.PARSED
        assert result.tool == TOOL_SD_WEBUI
        source = result.sources[0]
        assert (source.kind, source.key) == (SOURCE_KIND_EXIF, EXIF_KEY_USER_COMMENT)
        assert source.raw_bytes == comment
        assert source.raw_text == A1111_TEXT

    @pytest.mark.parametrize("encoding", ["utf-16-be", "utf-16-le"])
    def test_bomless_user_comment_starting_with_non_ascii(self, tmp_path: Path, encoding: str) -> None:
        text = "猫\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 1"
        path = _jpeg_with_user_comment(tmp_path / "jp.jpg", b"UNICODE\x00" + text.encode(encoding))

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.PARSED
        assert result.sources[0].raw_text == text

    def test_camera_user_comment_is_unsupported(self, tmp_path: Path) -> None:
        path = _jpeg_with_user_comment(tmp_path / "cam.jpg", b"ASCII\x00\x00\x00holiday")

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.UNSUPPORTED
        assert result.is_ai_generation_evidence is False

    def test_undecodable_user_comment_fails_but_keeps_bytes(self, tmp_path: Path) -> None:
        comment = b"ASCII\x00\x00\x00\xff\xfe\xfd"
        path = _jpeg_with_user_comment(tmp_path / "bad.jpg", comment)

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.FAILED
        assert result.sources[0].raw_bytes == comment
        assert result.sources[0].raw_text is None
        assert result.error_message

    def test_unreadable_file_fails_without_raising(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.png"
        path.write_bytes(b"not an image")

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.FAILED
        assert result.sources == ()
        assert result.error_message

    def test_training_caption_sidecar_is_not_read(self, tmp_path: Path) -> None:
        path = tmp_path / "s.png"
        Image.new("RGB", (8, 8)).save(path, "PNG")
        (tmp_path / "s.txt").write_text("1girl, solo, Steps: 20, Sampler: Euler, Seed: 1", encoding="utf-8")

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.NO_METADATA


def test_input_hash_changes_with_raw_data() -> None:
    a = parse_generation_sources((GenerationMetadataSource(SOURCE_KIND_PNG_TEXT, "parameters", "x"),))
    b = parse_generation_sources((GenerationMetadataSource(SOURCE_KIND_PNG_TEXT, "parameters", "y"),))
    assert a.input_sha256 != b.input_sha256
