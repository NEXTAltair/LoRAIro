"""画像に埋め込まれた生成メタデータの読み取りと解析 (ADR 0105, Issue #1481 / #1503)。

Qt にも DB にも依存しない純粋な処理。画像ファイルから生成情報の原データ (PNG の
テキストチャンク、EXIF の UserComment) を整形前のまま取り出し、別の結果型として
共通項目 (生成ツール、正/負プロンプト、生成モデル、LoRA 参照、seed、steps、sampler、CFG)
へ解析する。

対応形式:
- SD WebUI (A1111 / Forge 等) 形式の生成情報テキスト。PNG の ``parameters`` チャンク、
  または JPEG / WebP の EXIF UserComment。最後の行に ``Steps:`` を含む 3 個以上の
  ``key: value`` があるときだけ SD WebUI 形式と認める。
- ComfyUI の ``prompt`` (API ノードグラフ) / ``workflow`` (UI ノード配置) チャンク。
  sampler ノード (``KSampler`` / ``KSamplerAdvanced``) が 1 つのときだけ、その入力と
  上流の標準ノード (``CLIPTextEncode``、``LoraLoader``、``CheckpointLoaderSimple`` 等)
  を辿って共通項目を抽出する。sampler が複数ある場合は単一設定へ統合せず ``partial`` とする。

取得できない項目は推測で補完しない。学習用の付属ファイル (``.txt`` / ``.caption``) は
生成情報として読まない。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TypeGuard

from PIL import Image

from ..domain.generation_metadata import (
    GenerationMetadataResult,
    GenerationMetadataSource,
    GenerationMetadataStatus,
    GenerationParameters,
    LoraReference,
)

# 原データの取得元
SOURCE_KIND_PNG_TEXT = "png_text"
SOURCE_KIND_EXIF = "exif"

# 取り出す PNG テキストチャンクのキー
PNG_KEY_PARAMETERS = "parameters"
PNG_KEY_COMFY_PROMPT = "prompt"
PNG_KEY_COMFY_WORKFLOW = "workflow"
_PNG_KEYS: tuple[str, ...] = (PNG_KEY_PARAMETERS, PNG_KEY_COMFY_PROMPT, PNG_KEY_COMFY_WORKFLOW)

# EXIF: ExifIFD (0x8769) の UserComment (0x9286)
EXIF_KEY_USER_COMMENT = "UserComment"
_EXIF_IFD_POINTER = 0x8769
_EXIF_USER_COMMENT_TAG = 0x9286

# 生成ツール
TOOL_SD_WEBUI = "sd_webui"
TOOL_COMFYUI = "comfyui"

# parser 名
PARSER_SD_WEBUI = "sd_webui"
PARSER_COMFYUI = "comfyui"
PARSER_NONE = "none"

# A1111 の parse_generation_parameters と同じ key: value の分解規則
_RE_PARAM = re.compile(r'\s*(\w[\w \-/]+):\s*("(?:\\.|[^\\"])+"|[^,]*)(?:,|$)')
# プロンプト内の LoRA / LyCORIS 参照 (<lora:name:weight> / <lyco:name:weight:...>)
_RE_LORA = re.compile(r"<(lora|lyco):([^:>]+)(?::([^:>]+))?[^>]*>")
_NEGATIVE_PREFIX = "Negative prompt:"

# ComfyUI の対象ノード種別
_COMFY_SAMPLER_CLASSES: frozenset[str] = frozenset({"KSampler", "KSamplerAdvanced"})
_COMFY_CHECKPOINT_CLASSES: frozenset[str] = frozenset(
    {"CheckpointLoaderSimple", "CheckpointLoader", "ImageOnlyCheckpointLoader"}
)
_COMFY_UNET_CLASSES: frozenset[str] = frozenset({"UNETLoader", "DiffusionModelLoader"})
_COMFY_LORA_CLASSES: frozenset[str] = frozenset({"LoraLoader", "LoraLoaderModelOnly"})
_COMFY_MODEL_PASSTHROUGH_CLASSES: frozenset[str] = frozenset(
    {
        "ModelSamplingDiscrete",
        "ModelSamplingContinuousEDM",
        "ModelSamplingFlux",
        "ModelSamplingSD3",
        "PatchModelAddDownscale",
        "FreeU",
        "FreeU_V2",
    }
)
_COMFY_CONDITIONING_PASSTHROUGH_CLASSES: frozenset[str] = frozenset(
    {
        "ConditioningSetTimestepRange",
        "ConditioningSetArea",
        "ConditioningSetMask",
        "FluxGuidance",
    }
)
_COMFY_STRING_PRIMITIVE_CLASSES: frozenset[str] = frozenset({"PrimitiveNode", "String", "StringLiteral"})
_COMFY_LATENT_CLASSES: frozenset[str] = frozenset({"EmptyLatentImage", "EmptySD3LatentImage"})


def read_generation_sources(image_path: Path) -> tuple[GenerationMetadataSource, ...]:
    """画像ファイルから生成情報の原データを取り出す (コピーを返し、画像を変更しない)。

    Args:
        image_path: 画像ファイルのパス。

    Returns:
        見つかった原データ。無ければ空のタプル。

    Raises:
        OSError: ファイルを開けない / 画像として読めない場合。
        ValueError: Pillow が画像のヘッダーを解釈できない場合。
    """
    sources: list[GenerationMetadataSource] = []
    with Image.open(image_path) as img:
        # img.info は IDAT より前のテキストチャンクを持つ (pop せずに参照だけする)
        info = dict(img.info)
        for key in _PNG_KEYS:
            value = info.get(key)
            if isinstance(value, str):
                sources.append(GenerationMetadataSource(SOURCE_KIND_PNG_TEXT, key, value))
        user_comment = img.getexif().get_ifd(_EXIF_IFD_POINTER).get(_EXIF_USER_COMMENT_TAG)
    if isinstance(user_comment, bytes) and user_comment:
        sources.append(
            GenerationMetadataSource(
                SOURCE_KIND_EXIF,
                EXIF_KEY_USER_COMMENT,
                _decode_user_comment(user_comment),
                raw_bytes=user_comment,
            )
        )
    elif isinstance(user_comment, str) and user_comment:
        sources.append(GenerationMetadataSource(SOURCE_KIND_EXIF, EXIF_KEY_USER_COMMENT, user_comment))
    return tuple(sources)


def _decode_user_comment(data: bytes) -> str | None:
    """EXIF UserComment を復号する。先頭 8 バイトの文字コード指定に従う。

    復号できなければ None (原データのバイト列は別に保持する)。
    """
    prefix, body = data[:8], data[8:]
    try:
        if prefix == b"UNICODE\x00":
            if body.startswith((b"\xff\xfe", b"\xfe\xff")):
                return body.decode("utf-16")
            # BOM が無い場合は、ASCII 範囲の文字 (生成情報の key: value 行は ASCII) の上位バイト 0 が
            # 偶数位置と奇数位置のどちらに多いかで決める。同数なら piexif の既定の big endian。
            zeros_even = body[0::2].count(0)
            zeros_odd = body[1::2].count(0)
            return body.decode("utf-16-le" if zeros_odd > zeros_even else "utf-16-be")
        if prefix == b"ASCII\x00\x00\x00":
            return body.decode("ascii")
        if prefix == b"\x00" * 8:
            return body.decode("utf-8")
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def parse_generation_sources(sources: tuple[GenerationMetadataSource, ...]) -> GenerationMetadataResult:
    """原データを解析して結果を返す (原データ自体は変更しない)。

    Args:
        sources: ``read_generation_sources`` で取り出した原データ。

    Returns:
        解析結果。原データは ``sources`` としてそのまま含める。
    """
    if not sources:
        return GenerationMetadataResult(GenerationMetadataStatus.NO_METADATA, PARSER_NONE)

    by_key = {(s.kind, s.key): s for s in sources}
    comfy_sources = [
        s
        for s in sources
        if s.kind == SOURCE_KIND_PNG_TEXT and s.key in (PNG_KEY_COMFY_PROMPT, PNG_KEY_COMFY_WORKFLOW)
    ]
    webui_source = by_key.get((SOURCE_KIND_PNG_TEXT, PNG_KEY_PARAMETERS)) or by_key.get(
        (SOURCE_KIND_EXIF, EXIF_KEY_USER_COMMENT)
    )

    webui_params = (
        parse_sd_webui_parameters(webui_source.raw_text)
        if webui_source is not None and webui_source.raw_text is not None
        else None
    )

    if comfy_sources:
        return _result_for_comfyui(sources, comfy_sources, webui_params)

    if webui_source is not None and webui_source.raw_text is None:
        return GenerationMetadataResult(
            GenerationMetadataStatus.FAILED,
            PARSER_NONE,
            sources=sources,
            error_message=f"{webui_source.kind}:{webui_source.key} を文字列として復号できません",
        )
    if webui_params is None:
        return GenerationMetadataResult(GenerationMetadataStatus.UNSUPPORTED, PARSER_NONE, sources=sources)
    return GenerationMetadataResult(
        _webui_status(webui_params),
        PARSER_SD_WEBUI,
        tool=TOOL_SD_WEBUI,
        sources=sources,
        parameters=webui_params,
    )


def _result_for_comfyui(
    sources: tuple[GenerationMetadataSource, ...],
    comfy_sources: list[GenerationMetadataSource],
    webui_params: GenerationParameters | None,
) -> GenerationMetadataResult:
    """ComfyUI のチャンクがある場合の解析結果を返す。"""
    parsed_chunks = {s.key: _parse_comfyui_chunk(s.key, s.raw_text) for s in comfy_sources}
    valid_graphs = {k: data for k, (state, data) in parsed_chunks.items() if state == "valid" and data}
    broken_keys = [k for k, (state, _) in parsed_chunks.items() if state == "broken_json"]

    if not valid_graphs:
        if webui_params is not None:
            # ComfyUI と断定できないため、SD WebUI 形式の結果として扱う
            return GenerationMetadataResult(
                _webui_status(webui_params),
                PARSER_SD_WEBUI,
                tool=TOOL_SD_WEBUI,
                sources=sources,
                parameters=webui_params,
            )
        if broken_keys:
            return GenerationMetadataResult(
                GenerationMetadataStatus.FAILED,
                PARSER_COMFYUI,
                sources=sources,
                error_message=f"ComfyUI の JSON が壊れています: {', '.join(broken_keys)}",
            )
        invalid = [s.key for s in comfy_sources]
        # 同じキー名を別の用途で使うツールもあるため、ComfyUI とは判定しない
        return GenerationMetadataResult(
            GenerationMetadataStatus.UNSUPPORTED,
            PARSER_NONE,
            sources=sources,
            error_message=f"ComfyUI のノードグラフとして解釈できません: {', '.join(invalid)}",
        )

    if PNG_KEY_COMFY_PROMPT in broken_keys and webui_params is None:
        return GenerationMetadataResult(
            GenerationMetadataStatus.FAILED,
            PARSER_COMFYUI,
            tool=TOOL_COMFYUI,
            sources=sources,
            error_message="ComfyUI の prompt JSON が壊れています",
        )

    prompt_graph = _resolve_comfy_prompt_graph(valid_graphs)
    if prompt_graph is not None:
        status, comfy_params, error_message = parse_comfyui_prompt(prompt_graph)
        if status is GenerationMetadataStatus.PARSED or webui_params is None:
            return GenerationMetadataResult(
                status,
                PARSER_COMFYUI,
                tool=TOOL_COMFYUI,
                sources=sources,
                parameters=comfy_params,
                error_message=error_message,
            )

    if webui_params is not None:
        # ComfyUI のノードが書いた SD WebUI 形式の要約。グラフ全体は未解析なので partial。
        return GenerationMetadataResult(
            GenerationMetadataStatus.PARTIAL,
            PARSER_SD_WEBUI,
            tool=TOOL_COMFYUI,
            sources=sources,
            parameters=webui_params,
        )
    return GenerationMetadataResult(
        GenerationMetadataStatus.UNSUPPORTED, PARSER_COMFYUI, tool=TOOL_COMFYUI, sources=sources
    )


def _parse_comfyui_chunk(key: str, raw_text: str | None) -> tuple[str, dict[str, Any] | None]:
    """チャンク文字列を判定し、``("valid" | "broken_json" | "not_comfyui", dict | None)`` を返す。"""
    if raw_text is None:
        return "not_comfyui", None
    stripped = raw_text.lstrip()
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        if stripped.startswith(("{", "[")):
            return "broken_json", None
        return "not_comfyui", None
    if not isinstance(data, dict) or not data:
        return "not_comfyui", None
    if key == PNG_KEY_COMFY_WORKFLOW:
        if isinstance(data.get("nodes"), list) or _is_prompt_graph(data.get("prompt")):
            return "valid", data
        return "not_comfyui", None
    if _is_prompt_graph(data):
        return "valid", data
    return "not_comfyui", None


def _is_prompt_graph(data: object) -> TypeGuard[dict[str, Any]]:
    """ComfyUI の API 形式の prompt ノード辞書かを判定する。"""
    if not isinstance(data, dict) or not data:
        return False
    return all(isinstance(node, dict) and isinstance(node.get("class_type"), str) for node in data.values())


def _resolve_comfy_prompt_graph(valid_graphs: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """利用可能なチャンクから API 形式の prompt ノード辞書を取り出す。"""
    prompt_graph = valid_graphs.get(PNG_KEY_COMFY_PROMPT)
    if prompt_graph is not None:
        return prompt_graph
    workflow = valid_graphs.get(PNG_KEY_COMFY_WORKFLOW)
    if workflow is None:
        return None
    embedded = workflow.get("prompt")
    if _is_prompt_graph(embedded):
        return embedded
    extra = workflow.get("extra")
    if isinstance(extra, dict):
        extra_prompt = extra.get("prompt")
        if _is_prompt_graph(extra_prompt):
            return extra_prompt
    return None


def _node_id_sort_key(node_id: str) -> tuple[int, int | str]:
    return (0, int(node_id)) if node_id.isdigit() else (1, node_id)


def parse_comfyui_prompt(
    prompt_graph: dict[str, Any],
) -> tuple[GenerationMetadataStatus, GenerationParameters | None, str | None]:
    """ComfyUI の prompt ノード辞書から生成メタデータの共通項目を抽出する (ADR 0105, #1503)。

    sampler ノードが 1 つのときだけ共通項目を抽出し、複数あるときは単一設定へ統合せず
    ``partial`` として sampler ノード情報だけを ``extra`` に記録する。
    """
    sampler_ids = sorted(
        (
            str(node_id)
            for node_id, node in prompt_graph.items()
            if isinstance(node, dict) and node.get("class_type") in _COMFY_SAMPLER_CLASSES
        ),
        key=_node_id_sort_key,
    )
    if not sampler_ids:
        return GenerationMetadataStatus.UNSUPPORTED, None, None
    if len(sampler_ids) >= 2:
        params = _params_for_multiple_samplers(prompt_graph, sampler_ids)
        return GenerationMetadataStatus.PARTIAL, params, "multiple_samplers"
    return _parse_single_comfy_sampler(prompt_graph, prompt_graph[sampler_ids[0]])


def _params_for_multiple_samplers(
    prompt_graph: dict[str, Any], sampler_ids: list[str]
) -> GenerationParameters:
    """複数 sampler があるとき、誤って単一の sampler 設定へ統合せず経路情報だけを記録する。"""
    model_results = [
        _trace_comfy_model_input(prompt_graph, prompt_graph[sid].get("inputs", {}).get("model"))
        for sid in sampler_ids
        if isinstance(prompt_graph[sid].get("inputs"), dict)
        and "model" in prompt_graph[sid].get("inputs", {})
    ]
    shared_model: str | None = None
    shared_loras: tuple[LoraReference, ...] = ()
    if model_results and all(ok and name is not None for name, _, ok in model_results):
        distinct = {(name, loras) for name, loras, _ in model_results}
        if len(distinct) == 1:
            shared_model, shared_loras = next(iter(distinct))
    return GenerationParameters(
        model_name=shared_model,
        loras=shared_loras,
        extra={
            "sampler_count": len(sampler_ids),
            "sampler_node_ids": sampler_ids,
        },
    )


def _parse_single_comfy_sampler(
    prompt_graph: dict[str, Any], sampler_node: dict[str, Any]
) -> tuple[GenerationMetadataStatus, GenerationParameters, str | None]:
    """単一の sampler ノードから入力と上流リンクを辿って共通項目を抽出する。"""
    raw_inputs = sampler_node.get("inputs")
    inputs: dict[str, Any] = raw_inputs if isinstance(raw_inputs, dict) else {}
    links_ok = True

    seed, seed_ok = _extract_comfy_seed(prompt_graph, inputs)
    links_ok = links_ok and seed_ok
    steps = _extract_comfy_int(inputs.get("steps"))
    cfg_scale = _extract_comfy_float(inputs.get("cfg"))
    sampler_raw = inputs.get("sampler_name")
    sampler = sampler_raw.strip() if isinstance(sampler_raw, str) and sampler_raw.strip() else None

    positive_prompt, pos_ok = _resolve_optional_prompt(prompt_graph, inputs, "positive")
    negative_prompt, neg_ok = _resolve_optional_prompt(prompt_graph, inputs, "negative")
    model_name, loras, model_ok = _resolve_optional_model(prompt_graph, inputs)
    links_ok = links_ok and pos_ok and neg_ok and model_ok

    extra = _extract_comfy_extra(prompt_graph, inputs)
    params = GenerationParameters(
        positive_prompt=positive_prompt,
        negative_prompt=negative_prompt,
        model_name=model_name,
        seed=seed,
        steps=steps,
        sampler=sampler,
        cfg_scale=cfg_scale,
        loras=loras,
        extra=extra,
    )
    core = (positive_prompt, model_name, seed, steps, sampler, cfg_scale)
    if links_ok and all(value is not None for value in core):
        return GenerationMetadataStatus.PARSED, params, None
    error_msg = None if links_ok else "unresolved_comfyui_node"
    return GenerationMetadataStatus.PARTIAL, params, error_msg


def _extract_comfy_seed(prompt_graph: dict[str, Any], inputs: dict[str, Any]) -> tuple[str | None, bool]:
    """sampler の ``seed`` または ``noise_seed`` を文字列として取り出す。"""
    raw = inputs.get("seed") if "seed" in inputs else inputs.get("noise_seed")
    if raw is None:
        return None, True
    if isinstance(raw, int) and not isinstance(raw, bool):
        return str(raw), True
    if isinstance(raw, str):
        parsed = _parse_seed(raw)
        return parsed, parsed is not None
    node_id = _linked_node_id(raw)
    if node_id is None:
        return None, False
    node = prompt_graph.get(node_id)
    node_inputs = node.get("inputs") if isinstance(node, dict) else None
    if isinstance(node, dict) and isinstance(node_inputs, dict):
        if node.get("class_type") in ("PrimitiveNode", "Seed", "Int", "IntLiteral"):
            for key in ("value", "seed", "noise_seed"):
                val = node_inputs.get(key)
                if isinstance(val, int) and not isinstance(val, bool):
                    return str(val), True
    return None, False


def _extract_comfy_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _extract_comfy_float(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _resolve_optional_prompt(
    prompt_graph: dict[str, Any], inputs: dict[str, Any], key: str
) -> tuple[str | None, bool]:
    if key not in inputs:
        return None, True
    return _trace_comfy_prompt_input(prompt_graph, inputs[key])


def _resolve_optional_model(
    prompt_graph: dict[str, Any], inputs: dict[str, Any]
) -> tuple[str | None, tuple[LoraReference, ...], bool]:
    if "model" not in inputs:
        return None, (), True
    return _trace_comfy_model_input(prompt_graph, inputs["model"])


def _extract_comfy_extra(prompt_graph: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    scheduler = inputs.get("scheduler")
    if isinstance(scheduler, str) and scheduler.strip():
        extra["scheduler"] = scheduler.strip()
    denoise = _extract_comfy_float(inputs.get("denoise"))
    if denoise is not None:
        extra["denoise"] = str(inputs["denoise"])
    if "latent_image" in inputs:
        size = _trace_comfy_latent_size(prompt_graph, inputs["latent_image"])
        if size is not None:
            extra["Size"] = size
    return extra


def _linked_node_id(value: object) -> str | None:
    """ComfyUI の入力リンク ``[node_id, slot_index]`` から参照先ノード ID を返す。"""
    if (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str | int)
        and not isinstance(value[0], bool)
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
    ):
        return str(value[0])
    return None


def _get_comfy_node(prompt_graph: dict[str, Any], node_id: str) -> tuple[str, dict[str, Any]] | None:
    """ノード辞書から ``(class_type, inputs)`` を取り出す。無ければ None。"""
    node = prompt_graph.get(node_id)
    if not isinstance(node, dict):
        return None
    class_type = node.get("class_type")
    node_inputs = node.get("inputs")
    if not isinstance(class_type, str) or not isinstance(node_inputs, dict):
        return None
    return class_type, node_inputs


def _trace_comfy_prompt_input(prompt_graph: dict[str, Any], raw_input: object) -> tuple[str | None, bool]:
    """conditioning / テキストリンクを辿ってプロンプト文字列を返す。"""
    if isinstance(raw_input, str):
        return raw_input.strip("\n") or None, True
    node_id = _linked_node_id(raw_input)
    if node_id is None:
        return None, False

    visited: set[str] = set()
    while node_id is not None and node_id not in visited:
        visited.add(node_id)
        node_info = _get_comfy_node(prompt_graph, node_id)
        if node_info is None:
            return None, False
        next_id, result = _step_comfy_prompt_node(*node_info)
        if result is not None:
            return result
        node_id = next_id
    return None, False


def _step_comfy_prompt_node(
    class_type: str, node_inputs: dict[str, Any]
) -> tuple[str | None, tuple[str | None, bool] | None]:
    """プロンプト経路の 1 ノードを処理し、(次のノード ID, 確定結果) を返す。"""
    if class_type == "CLIPTextEncode":
        text = node_inputs.get("text")
        if isinstance(text, str):
            return None, (text.strip("\n") or None, True)
        return _linked_node_id(text), None
    if class_type in ("CLIPTextEncodeSDXL", "CLIPTextEncodeSDXLRefiner"):
        return None, _extract_sdxl_clip_text(node_inputs)
    if class_type in _COMFY_CONDITIONING_PASSTHROUGH_CLASSES:
        return _linked_node_id(node_inputs.get("conditioning")), None
    if class_type in _COMFY_STRING_PRIMITIVE_CLASSES:
        return None, _extract_string_primitive(node_inputs)
    return None, (None, False)


def _extract_sdxl_clip_text(node_inputs: dict[str, Any]) -> tuple[str | None, bool]:
    text = node_inputs.get("text")
    if isinstance(text, str):
        return text.strip("\n") or None, True
    text_g = node_inputs.get("text_g")
    text_l = node_inputs.get("text_l")
    if isinstance(text_g, str) and isinstance(text_l, str):
        if text_g == text_l or not text_l:
            combined = text_g
        elif not text_g:
            combined = text_l
        else:
            combined = f"{text_g}\n{text_l}"
        return combined.strip("\n") or None, True
    return None, False


def _extract_string_primitive(node_inputs: dict[str, Any]) -> tuple[str | None, bool]:
    for key in ("value", "string", "text"):
        val = node_inputs.get(key)
        if isinstance(val, str):
            return val.strip("\n") or None, True
    return None, False


def _trace_comfy_model_input(
    prompt_graph: dict[str, Any], raw_input: object
) -> tuple[str | None, tuple[LoraReference, ...], bool]:
    """sampler の ``model`` リンクを上流へ辿り、(モデル名, LoRA 列, 解釈成否) を返す。"""
    node_id = _linked_node_id(raw_input)
    if node_id is None:
        return None, (), False

    loras_reversed: list[LoraReference] = []
    visited: set[str] = set()
    while node_id is not None and node_id not in visited:
        visited.add(node_id)
        node_info = _get_comfy_node(prompt_graph, node_id)
        if node_info is None:
            break
        next_id, model_name, ok = _step_comfy_model_node(*node_info, loras_reversed)
        if not ok:
            break
        if model_name is not None:
            return model_name, tuple(reversed(loras_reversed)), True
        node_id = next_id
    return None, tuple(reversed(loras_reversed)), False


def _step_comfy_model_node(
    class_type: str,
    node_inputs: dict[str, Any],
    loras_reversed: list[LoraReference],
) -> tuple[str | None, str | None, bool]:
    """モデル経路の 1 ノードを処理し、(次のノード ID, モデル名, 継続可否) を返す。"""
    if class_type in _COMFY_CHECKPOINT_CLASSES:
        ckpt = node_inputs.get("ckpt_name")
        if isinstance(ckpt, str) and ckpt.strip():
            return None, ckpt.strip(), True
        return None, None, False
    if class_type in _COMFY_UNET_CLASSES:
        unet = node_inputs.get("unet_name") or node_inputs.get("model_name")
        if isinstance(unet, str) and unet.strip():
            return None, unet.strip(), True
        return None, None, False
    if class_type in _COMFY_LORA_CLASSES:
        lora = _extract_comfy_lora_node(node_inputs)
        if lora is None:
            return None, None, False
        loras_reversed.append(lora)
        return _linked_node_id(node_inputs.get("model")), None, True
    if class_type in _COMFY_MODEL_PASSTHROUGH_CLASSES:
        return _linked_node_id(node_inputs.get("model")), None, True
    return None, None, False


def _extract_comfy_lora_node(node_inputs: dict[str, Any]) -> LoraReference | None:
    lora_name = node_inputs.get("lora_name")
    if not isinstance(lora_name, str) or not lora_name.strip():
        return None
    strength = node_inputs.get("strength_model")
    weight = str(strength) if isinstance(strength, int | float) and not isinstance(strength, bool) else None
    return LoraReference(name=lora_name.strip(), weight=weight)


def _trace_comfy_latent_size(prompt_graph: dict[str, Any], raw_input: object) -> str | None:
    node_id = _linked_node_id(raw_input)
    if node_id is None:
        return None
    node = prompt_graph.get(node_id)
    if not isinstance(node, dict) or node.get("class_type") not in _COMFY_LATENT_CLASSES:
        return None
    node_inputs = node.get("inputs")
    if not isinstance(node_inputs, dict):
        return None
    width = _extract_comfy_int(node_inputs.get("width"))
    height = _extract_comfy_int(node_inputs.get("height"))
    if width is not None and height is not None:
        return f"{width}x{height}"
    return None


def _webui_status(params: GenerationParameters) -> GenerationMetadataStatus:
    """主要項目 (prompt / steps / sampler / seed / cfg) が揃っていれば parsed。"""
    core = (params.positive_prompt, params.steps, params.sampler, params.seed, params.cfg_scale)
    if all(value is not None for value in core):
        return GenerationMetadataStatus.PARSED
    return GenerationMetadataStatus.PARTIAL


def parse_sd_webui_parameters(text: str) -> GenerationParameters | None:
    """SD WebUI 形式の生成情報テキストを解析する。

    最後の行が ``Steps:`` を含む 3 個以上の ``key: value`` でなければ SD WebUI 形式と
    認めず None を返す (汎用の文字列一致を生成情報とみなさない)。プロンプトの順序・重み表記・
    改行は変えない (前後の空行だけ除く)。

    Args:
        text: ``parameters`` チャンク等の原文。

    Returns:
        解析結果。SD WebUI 形式でなければ None。
    """
    lines = text.split("\n")
    # 末尾の空行は形式判定の対象外
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return None
    last_line = lines[-1]
    pairs = _RE_PARAM.findall(last_line)
    keys = [key.strip() for key, _ in pairs]
    if len(pairs) < 3 or "Steps" not in keys:
        return None

    prompt_lines: list[str] = []
    negative_lines: list[str] = []
    in_negative = False
    for line in lines[:-1]:
        if not in_negative and line.startswith(_NEGATIVE_PREFIX):
            in_negative = True
            negative_lines.append(line[len(_NEGATIVE_PREFIX) :].lstrip(" "))
            continue
        (negative_lines if in_negative else prompt_lines).append(line)

    values: dict[str, str] = {}
    for key, value in pairs:
        values[key.strip()] = _unquote(value.strip())

    positive = "\n".join(prompt_lines).strip("\n") or None
    negative = "\n".join(negative_lines).strip("\n") if in_negative else None

    known = {"Steps", "Sampler", "CFG scale", "Seed", "Model", "Model hash"}
    extra = {key: value for key, value in values.items() if key not in known}

    return GenerationParameters(
        positive_prompt=positive,
        negative_prompt=negative,
        model_name=values.get("Model") or None,
        model_hash=values.get("Model hash") or None,
        seed=_parse_seed(values.get("Seed")),
        steps=_parse_int(values.get("Steps")),
        sampler=values.get("Sampler") or None,
        cfg_scale=_parse_float(values.get("CFG scale")),
        loras=_extract_loras(positive),
        extra=extra,
    )


def _unquote(value: str) -> str:
    """A1111 がダブルクォートで囲んだ値 (JSON 文字列) を戻す。失敗したら原文のまま。"""
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return value
        if isinstance(decoded, str):
            return decoded
    return value


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_seed(value: str | None) -> str | None:
    """seed は 64 bit を超えることがあるため、整数として読める表記だけを文字列で持つ。"""
    if value is None:
        return None
    return value if re.fullmatch(r"-?\d+", value) else None


def _extract_loras(prompt: str | None) -> tuple[LoraReference, ...]:
    """プロンプト内の ``<lora:name:weight>`` を出現順に取り出す。"""
    if not prompt:
        return ()
    return tuple(
        LoraReference(name=name.strip(), weight=weight.strip() if weight else None, kind=kind)
        for kind, name, weight in _RE_LORA.findall(prompt)
    )


def extract_generation_metadata(image_path: Path) -> GenerationMetadataResult:
    """画像ファイルから生成メタデータを取り出して解析する。

    ファイルの読み取りに失敗しても例外を投げず、``failed`` の結果を返す (登録処理を止めない)。

    Args:
        image_path: 画像ファイルのパス。

    Returns:
        解析結果。
    """
    try:
        sources = read_generation_sources(image_path)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as e:
        return GenerationMetadataResult(
            GenerationMetadataStatus.FAILED,
            PARSER_NONE,
            error_message=f"生成メタデータの読み取りに失敗: {type(e).__name__}",
        )
    return parse_generation_sources(sources)
