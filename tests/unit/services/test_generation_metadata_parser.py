"""生成メタデータの parser (ADR 0105, Issue #1481 / #1503)。

テスト用の画像は Pillow でその場で作る (外部から取得しない)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from lorairo.domain.generation_metadata import (
    GENERATION_METADATA_PARSER_VERSION,
    PARSER_VERSION,
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
    parse_comfyui_prompt,
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

COMFY_SINGLE_SAMPLER_PROMPT = json.dumps(
    {
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"},
        },
        "10": {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": "style_v1.safetensors",
                "strength_model": 0.75,
                "strength_clip": 0.75,
                "model": ["4", 0],
                "clip": ["4", 1],
            },
        },
        "11": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "lora_name": "detail.safetensors",
                "strength_model": 0.5,
                "model": ["10", 0],
            },
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 512, "height": 768, "batch_size": 1},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "masterpiece, 1girl, solo", "clip": ["10", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "lowres, bad hands", "clip": ["10", 1]},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 156680208700286,
                "steps": 20,
                "cfg": 8.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["11", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
    }
)

COMFY_MULTI_SAMPLER_PROMPT = json.dumps(
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


def test_parser_version_is_bumped_to_v2() -> None:
    assert PARSER_VERSION == "2"
    assert GENERATION_METADATA_PARSER_VERSION == "2"


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


class TestComfyUiNodeGraph:
    def test_single_ksampler_extracts_model_loras_prompts_and_sampler_fields(self, tmp_path: Path) -> None:
        path = _png(
            tmp_path / "comfy_single.png",
            {"prompt": COMFY_SINGLE_SAMPLER_PROMPT, "workflow": COMFY_WORKFLOW},
        )

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.PARSED
        assert result.tool == TOOL_COMFYUI
        assert result.parser_name == PARSER_COMFYUI
        assert result.parser_version == "2"
        assert result.error_message is None
        assert result.is_ai_generation_evidence is True
        assert {s.key for s in result.sources} == {"prompt", "workflow"}
        # 原データは書き換えない
        prompt_source = next(s for s in result.sources if s.key == "prompt")
        assert prompt_source.raw_text == COMFY_SINGLE_SAMPLER_PROMPT

        params = result.parameters
        assert params is not None
        assert params.positive_prompt == "masterpiece, 1girl, solo"
        assert params.negative_prompt == "lowres, bad hands"
        assert params.model_name == "v1-5-pruned-emaonly.safetensors"
        assert params.model_hash is None
        assert params.seed == "156680208700286"
        assert params.steps == 20
        assert params.sampler == "euler"
        assert params.cfg_scale == 8.0
        # ベースモデルから sampler へ向かう適用順
        assert params.loras == (
            LoraReference(name="style_v1.safetensors", weight="0.75"),
            LoraReference(name="detail.safetensors", weight="0.5"),
        )
        assert params.extra == {
            "scheduler": "normal",
            "denoise": "1.0",
            "Size": "512x768",
        }

    def test_ksampler_advanced_with_noise_seed_and_unet_loader_is_parsed(self) -> None:
        graph = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux1-dev.safetensors"}},
            "2": {"class_type": "ModelSamplingFlux", "inputs": {"model": ["1", 0]}},
            "3": {
                "class_type": "PrimitiveNode",
                "inputs": {"value": "cinematic lighting, portrait"},
            },
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": ["3", 0]}},
            "5": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["4", 0], "guidance": 3.5}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
            "7": {
                "class_type": "KSamplerAdvanced",
                "inputs": {
                    "add_noise": "enable",
                    "noise_seed": 999888777,
                    "steps": 25,
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "model": ["2", 0],
                    "positive": ["5", 0],
                    "negative": ["6", 0],
                },
            },
        }

        status, params, error = parse_comfyui_prompt(graph)

        assert status is GenerationMetadataStatus.PARSED
        assert error is None
        assert params is not None
        assert params.model_name == "flux1-dev.safetensors"
        assert params.positive_prompt == "cinematic lighting, portrait"
        assert params.negative_prompt is None
        assert params.seed == "999888777"
        assert params.steps == 25
        assert params.sampler == "euler"
        assert params.cfg_scale == 1.0
        assert params.extra == {"scheduler": "simple"}

    def test_multiple_samplers_are_partial_and_not_merged_into_single_setting(self, tmp_path: Path) -> None:
        path = _png(tmp_path / "c.png", {"prompt": COMFY_MULTI_SAMPLER_PROMPT, "workflow": COMFY_WORKFLOW})

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.PARTIAL
        assert result.tool == TOOL_COMFYUI
        assert result.parser_name == PARSER_COMFYUI
        assert result.error_message == "multiple_samplers"
        assert result.error_reason == "multiple_samplers"
        assert result.is_ai_generation_evidence is True
        assert {s.key for s in result.sources} == {"prompt", "workflow"}
        assert result.parameters is not None
        # 複数の sampler を単一設定へ統合しない
        assert result.parameters.seed is None
        assert result.parameters.steps is None
        assert result.parameters.sampler is None
        assert result.parameters.cfg_scale is None
        assert result.parameters.positive_prompt is None
        assert result.parameters.negative_prompt is None
        assert result.parameters.extra == {
            "sampler_count": 2,
            "sampler_node_ids": ["3", "9"],
        }

    def test_multiple_samplers_sharing_same_checkpoint_preserve_only_shared_model(self) -> None:
        graph = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sdxl.safetensors"}},
            "2": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 20, "model": ["1", 0]}},
            "3": {"class_type": "KSampler", "inputs": {"seed": 2, "steps": 10, "model": ["1", 0]}},
        }

        status, params, error = parse_comfyui_prompt(graph)

        assert status is GenerationMetadataStatus.PARTIAL
        assert error == "multiple_samplers"
        assert params is not None
        assert params.model_name == "sdxl.safetensors"
        assert params.seed is None
        assert params.steps is None
        assert params.extra == {"sampler_count": 2, "sampler_node_ids": ["2", "3"]}

    def test_unknown_prompt_or_model_node_results_in_partial(self, tmp_path: Path) -> None:
        graph = {
            "1": {"class_type": "CustomModelMerger", "inputs": {"model_a": "a.safetensors"}},
            "2": {"class_type": "WildcardPromptNode", "inputs": {"wildcard": "__pose__"}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "lowres"}},
            "4": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 42,
                    "steps": 20,
                    "cfg": 7.0,
                    "sampler_name": "euler_ancestral",
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                },
            },
        }
        path = _png(tmp_path / "unknown_node.png", {"prompt": json.dumps(graph)})

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.PARTIAL
        assert result.tool == TOOL_COMFYUI
        assert result.parser_name == PARSER_COMFYUI
        assert result.error_message == "unresolved_comfyui_node"
        assert result.parameters is not None
        assert result.parameters.seed == "42"
        assert result.parameters.steps == 20
        assert result.parameters.sampler == "euler_ancestral"
        assert result.parameters.cfg_scale == 7.0
        # 未知ノードの先は推測しない
        assert result.parameters.model_name is None
        assert result.parameters.positive_prompt is None
        assert result.parameters.negative_prompt == "lowres"

    def test_workflow_only_without_prompt_graph_is_unsupported(self, tmp_path: Path) -> None:
        path = _png(tmp_path / "wf_only.png", {"workflow": COMFY_WORKFLOW})

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.UNSUPPORTED
        assert result.tool == TOOL_COMFYUI
        assert result.parser_name == PARSER_COMFYUI
        assert result.parameters is None
        assert result.is_ai_generation_evidence is True

    def test_broken_json_in_prompt_chunk_fails_and_keeps_raw_source(self, tmp_path: Path) -> None:
        broken = '{"3": {"class_type": "KSampler", "inputs": {"seed": 1'
        path = _png(tmp_path / "broken_comfy.png", {"prompt": broken})

        result = extract_generation_metadata(path)

        assert result.status is GenerationMetadataStatus.FAILED
        assert result.error_message is not None
        assert result.is_ai_generation_evidence is False
        assert result.sources == (GenerationMetadataSource(SOURCE_KIND_PNG_TEXT, "prompt", broken),)


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

    def test_comfyui_with_webui_summary_is_partial(self, tmp_path: Path) -> None:
        path = _png(tmp_path / "cw.png", {"parameters": A1111_TEXT, "prompt": COMFY_MULTI_SAMPLER_PROMPT})

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
