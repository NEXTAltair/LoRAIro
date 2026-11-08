"""画像に埋め込まれた生成メタデータの読み取りと解析 (ADR 0105, Issue #1481)。

Qt にも DB にも依存しない純粋な処理。画像ファイルから生成情報の原データ (PNG の
テキストチャンク、EXIF の UserComment) を整形前のまま取り出し、別の結果型として
共通項目 (生成ツール、正/負プロンプト、生成モデル、LoRA 参照、seed、steps、sampler、CFG)
へ解析する。

初期対応:
- SD WebUI (A1111 / Forge 等) 形式の生成情報テキスト。PNG の ``parameters`` チャンク、
  または JPEG / WebP の EXIF UserComment。最後の行に ``Steps:`` を含む 3 個以上の
  ``key: value`` があるときだけ SD WebUI 形式と認める。
- ComfyUI の ``prompt`` / ``workflow`` チャンクは、原データを保存して ComfyUI と判定するが、
  ノードグラフからは項目を抽出しない (複数 sampler 等を単一設定へ統合しないため)。

取得できない項目は推測で補完しない。学習用の付属ファイル (``.txt`` / ``.caption``) は
生成情報として読まない。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

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
            # BOM が無い場合、ASCII 範囲の文字の上位バイトが先頭にあれば big endian
            big_endian = len(body) >= 2 and body[0] == 0 and body[1] != 0
            return body.decode("utf-16-be" if big_endian else "utf-16-le")
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
    """ComfyUI のチャンクがある場合の結果。ノードグラフからは項目を抽出しない。"""
    invalid = [s.key for s in comfy_sources if not _is_comfyui_graph(s.key, s.raw_text)]
    if invalid and len(invalid) == len(comfy_sources):
        if webui_params is not None:
            # ComfyUI と断定できないため、SD WebUI 形式の結果として扱う
            return GenerationMetadataResult(
                _webui_status(webui_params),
                PARSER_SD_WEBUI,
                tool=TOOL_SD_WEBUI,
                sources=sources,
                parameters=webui_params,
            )
        # 同じキー名を別の用途で使うツールもあるため、ComfyUI とは判定しない
        return GenerationMetadataResult(
            GenerationMetadataStatus.UNSUPPORTED,
            PARSER_NONE,
            sources=sources,
            error_message=f"ComfyUI のノードグラフとして解釈できません: {', '.join(invalid)}",
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


def _is_comfyui_graph(key: str, raw_text: str | None) -> bool:
    """ComfyUI の prompt (API 形式) / workflow (UI 形式) の JSON かを判定する。"""
    if raw_text is None:
        return False
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict) or not data:
        return False
    if key == PNG_KEY_COMFY_WORKFLOW:
        return isinstance(data.get("nodes"), list)
    return all(isinstance(node, dict) and "class_type" in node for node in data.values())


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
