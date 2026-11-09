"""2 枚の画像の現在の注釈と生成メタデータを比べる (Issue #1399 / #1484 / #1485, Qt-free)。

比較画面 (``gui/widgets/image_comparison_dialog.py``) の差分計算と左右の選択状態を持つ。
DB は読むだけで、タグや採用状態は変更しない。

- タグは左右の集合差分 (共通 / 左だけ / 右だけ) を、それぞれの元の並びで返す。
- キャプションとプロンプトは原文を整形せずにトークン単位の差分を返す。各差分区間の左側を連結すると
  左の原文、右側を連結すると右の原文に戻る。
- 生成メタデータは共通項目 (生成ツール / 解析状態 / モデル / LoRA / 正・負プロンプト / seed / steps /
  sampler / scheduler / CFG / denoise 等) を原文の値で比べ、表示用の整形文字列は別に持つ。
- 片側に情報が無いとき (タグ 0 件・キャプション未登録・生成メタデータなし・画像が見つからない) は比較せず、
  ``Availability`` で欠けている側を返す。空と空を「同じ」とは言わない。
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from enum import StrEnum
from pathlib import PurePath
from typing import Any, Protocol

from ..domain.generation_metadata import (
    GenerationMetadataResult,
    GenerationMetadataSource,
    GenerationMetadataStatus,
    LoraReference,
)


class Side(StrEnum):
    """比較の左右。"""

    LEFT = "left"
    RIGHT = "right"

    @property
    def other(self) -> Side:
        """反対側。"""
        return Side.RIGHT if self is Side.LEFT else Side.LEFT


class Availability(StrEnum):
    """比較項目が左右のどちらにあるか。"""

    BOTH = "both"
    LEFT_MISSING = "left_missing"
    RIGHT_MISSING = "right_missing"
    BOTH_MISSING = "both_missing"


def _availability(has_left: bool, has_right: bool) -> Availability:
    if has_left and has_right:
        return Availability.BOTH
    if has_right:
        return Availability.LEFT_MISSING
    if has_left:
        return Availability.RIGHT_MISSING
    return Availability.BOTH_MISSING


class DiffKind(StrEnum):
    """キャプション差分の区間の種類。"""

    EQUAL = "equal"
    DELETE = "delete"
    INSERT = "insert"
    REPLACE = "replace"


@dataclass(frozen=True)
class TagDiff:
    """タグの集合差分。``availability`` が BOTH 以外のときは各タプルが空になる。"""

    availability: Availability
    common: tuple[str, ...] = ()
    left_only: tuple[str, ...] = ()
    right_only: tuple[str, ...] = ()

    @property
    def identical(self) -> bool:
        """両側にタグがあり、集合が一致するか。"""
        return self.availability is Availability.BOTH and not self.left_only and not self.right_only


@dataclass(frozen=True)
class DiffSegment:
    """キャプション差分の 1 区間。``left`` / ``right`` は原文の部分文字列。"""

    kind: DiffKind
    left: str
    right: str


@dataclass(frozen=True)
class CaptionDiff:
    """キャプションのテキスト差分。``availability`` が BOTH のときだけ ``segments`` を持つ。"""

    availability: Availability
    segments: tuple[DiffSegment, ...] = ()

    @property
    def identical(self) -> bool:
        """両側にキャプションがあり、原文が一致するか。"""
        return self.availability is Availability.BOTH and all(
            seg.kind is DiffKind.EQUAL for seg in self.segments
        )


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def diff_tags(left: list[str] | tuple[str, ...], right: list[str] | tuple[str, ...]) -> TagDiff:
    """左右のタグを共通 / 左だけ / 右だけに分ける。

    タグは原文のまま (大文字小文字も区別して) 比べる。重複は 1 つにまとめる。

    Args:
        left: 左の画像のタグ。
        right: 右の画像のタグ。

    Returns:
        片側のタグが 0 件なら比較せず、欠けている側を示す ``TagDiff``。
    """
    left_tags = _unique(list(left))
    right_tags = _unique(list(right))
    availability = _availability(bool(left_tags), bool(right_tags))
    if availability is not Availability.BOTH:
        return TagDiff(availability=availability)
    right_set = set(right_tags)
    left_set = set(left_tags)
    return TagDiff(
        availability=availability,
        common=tuple(t for t in left_tags if t in right_set),
        left_only=tuple(t for t in left_tags if t not in right_set),
        right_only=tuple(t for t in right_tags if t not in left_set),
    )


# ASCII の語・空白の連続はまとめ、それ以外 (日本語・記号) は 1 文字ずつに分ける。
# どの文字もちょうど 1 つのトークンに入るため、連結すると原文に戻る。
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|\s+|.", re.DOTALL)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text)


def _normalize_caption(text: str | None) -> str | None:
    return text if text else None


def diff_caption(left: str | None, right: str | None) -> CaptionDiff:
    """キャプションの原文どうしのテキスト差分を返す。

    改行や空白も整形せずに比べる。``None`` と空文字は「キャプション未登録」として扱う。

    Args:
        left: 左の画像のキャプション。
        right: 右の画像のキャプション。

    Returns:
        片側が未登録なら比較せず、欠けている側を示す ``CaptionDiff``。
    """
    left_text = _normalize_caption(left)
    right_text = _normalize_caption(right)
    availability = _availability(left_text is not None, right_text is not None)
    if left_text is None or right_text is None:
        return CaptionDiff(availability=availability)

    left_tokens = _tokenize(left_text)
    right_tokens = _tokenize(right_text)
    matcher = SequenceMatcher(a=left_tokens, b=right_tokens, autojunk=False)
    segments: list[DiffSegment] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        segments.append(
            DiffSegment(
                kind=DiffKind(tag),
                left="".join(left_tokens[i1:i2]),
                right="".join(right_tokens[j1:j2]),
            )
        )
    return CaptionDiff(availability=availability, segments=tuple(segments))


_TOOL_LABELS: dict[str, str] = {
    "sd_webui": "SD WebUI",
    "comfyui": "ComfyUI",
}
_STATUS_LABELS: dict[GenerationMetadataStatus, str] = {
    GenerationMetadataStatus.PARSED: "解析済み (parsed)",
    GenerationMetadataStatus.PARTIAL: "一部解析 (partial)",
    GenerationMetadataStatus.UNSUPPORTED: "未対応形式 (unsupported)",
    GenerationMetadataStatus.NO_METADATA: "なし",
    GenerationMetadataStatus.FAILED: "解析失敗 (failed)",
}
_SCHEDULER_KEYS: tuple[str, ...] = ("Schedule type", "Scheduler", "scheduler")
_DENOISE_KEYS: tuple[str, ...] = ("Denoising strength", "Denoise", "denoise")
_RESERVED_EXTRA_KEYS: frozenset[str] = frozenset(_SCHEDULER_KEYS + _DENOISE_KEYS)
_FIELD_ALIASES: dict[str, str] = {
    "cfg": "cfg_scale",
    "model": "model_name",
    "positive": "positive_prompt",
    "negative": "negative_prompt",
}


def _non_empty_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def _format_lora(lora: LoraReference) -> str:
    prefix = f"{lora.kind}:" if lora.kind and lora.kind != "lora" else ""
    if lora.weight is not None and lora.weight != "":
        return f"{prefix}{lora.name}:{lora.weight}"
    return f"{prefix}{lora.name}"


def _format_loras(loras: tuple[LoraReference, ...]) -> str:
    if not loras:
        return "なし"
    return ", ".join(_format_lora(lora) for lora in loras)


def _format_cfg(cfg_scale: float | None) -> str:
    if cfg_scale is None:
        return "なし"
    return f"{cfg_scale:g}"


@dataclass(frozen=True)
class ComparisonGenerationMetadata:
    """比較の片側に表示する、画像 1 枚の生成メタデータ (Issue #1485)。

    原データ (``sources``) と解析結果の共通項目を保持する。
    未解析 (``status=None``) や生成情報なし (``status=NO_METADATA``) の側は
    ``has_metadata=False`` となり、比較では常に ``"なし"`` として扱う。
    """

    status: GenerationMetadataStatus | None = None
    tool: str | None = None
    positive_prompt: str | None = None
    negative_prompt: str | None = None
    model_name: str | None = None
    model_hash: str | None = None
    seed: str | None = None
    steps: int | None = None
    sampler: str | None = None
    cfg_scale: float | None = None
    loras: tuple[LoraReference, ...] = ()
    extra: dict[str, str] = field(default_factory=dict)
    sources: tuple[GenerationMetadataSource, ...] = ()
    error_message: str | None = None

    @property
    def has_metadata(self) -> bool:
        """比較対象の生成メタデータがあるか。"""
        if self.status in (GenerationMetadataStatus.NO_METADATA, GenerationMetadataStatus.FAILED):
            return False
        if self.status in (
            GenerationMetadataStatus.PARSED,
            GenerationMetadataStatus.PARTIAL,
            GenerationMetadataStatus.UNSUPPORTED,
        ):
            return True
        return any(
            (
                _non_empty_str(self.tool),
                _non_empty_str(self.positive_prompt),
                _non_empty_str(self.negative_prompt),
                _non_empty_str(self.model_name),
                _non_empty_str(self.model_hash),
                _non_empty_str(self.seed),
                self.steps is not None,
                _non_empty_str(self.sampler),
                self.cfg_scale is not None,
                bool(self.loras),
                bool(self.extra),
                bool(self.sources),
            )
        )

    @property
    def scheduler(self) -> str | None:
        """extra から取り出した Scheduler / Schedule type。無ければ None。"""
        for key in _SCHEDULER_KEYS:
            val = _non_empty_str(self.extra.get(key))
            if val is not None:
                return val
        return None

    @property
    def denoise(self) -> str | None:
        """extra から取り出した Denoising strength / Denoise。無ければ None。"""
        for key in _DENOISE_KEYS:
            val = _non_empty_str(self.extra.get(key))
            if val is not None:
                return val
        return None

    @property
    def raw_parameters(self) -> str | None:
        """PNG parameters または EXIF UserComment の原文。無ければ None。"""
        for source in self.sources:
            if source.key in ("parameters", "UserComment") and source.raw_text is not None:
                return source.raw_text
        return None

    @property
    def raw_prompt(self) -> str | None:
        """ComfyUI prompt チャンクの原文。無ければ None。"""
        for source in self.sources:
            if source.key == "prompt" and source.raw_text is not None:
                return source.raw_text
        return None

    @property
    def raw_workflow(self) -> str | None:
        """ComfyUI workflow チャンクの原文。無ければ None。"""
        for source in self.sources:
            if source.key == "workflow" and source.raw_text is not None:
                return source.raw_text
        return None

    def summary_label(self) -> str:
        """出所表示用の短い要約文。"""
        if not self.has_metadata:
            return "なし"
        tool_text = _TOOL_LABELS.get(self.tool or "", self.tool or "不明")
        if self.status is not None:
            status_text = _STATUS_LABELS.get(self.status, self.status.value)
            return f"{tool_text} ({status_text})"
        return tool_text

    def raw_sources_text(self) -> str:
        """原データを整形せずそのまま確認できる文字列で返す。原データが無ければ ``"なし"``。"""
        if not self.sources:
            if self.error_message:
                return f"なし (エラー: {self.error_message})"
            return "なし"
        blocks: list[str] = []
        for source in self.sources:
            header = f"[{source.kind}:{source.key}]"
            if source.raw_text is not None:
                blocks.append(f"{header}\n{source.raw_text}")
            elif source.raw_bytes is not None:
                blocks.append(
                    f"{header}\n(復号できないバイト列: {len(source.raw_bytes)} bytes, sha256={source.sha256})"
                )
            else:
                blocks.append(f"{header}\nなし")
        return "\n\n".join(blocks)


@dataclass(frozen=True)
class GenerationFieldDiff:
    """生成メタデータの 1 項目の比較結果。

    原文の値 (``left_raw`` / ``right_raw``) で一致判定し、表示用の整形文字列
    (``left_display`` / ``right_display``) は別に持つ。欠けている側は常に ``"なし"``。
    """

    key: str
    label: str
    availability: Availability
    left_raw: Any = None
    right_raw: Any = None
    left_display: str = "なし"
    right_display: str = "なし"

    @property
    def identical(self) -> bool:
        """両側に値があり、原文の値が一致するか。両方欠落は「同じ」ではない。"""
        return self.availability is Availability.BOTH and self.left_raw == self.right_raw

    @property
    def changed(self) -> bool:
        """少なくとも片側に値があり、左右で異なるか (片側欠落を含む)。"""
        return self.availability is not Availability.BOTH_MISSING and not self.identical

    @property
    def status_label(self) -> str:
        """項目の比較状態の表示文。"""
        if self.availability is Availability.BOTH_MISSING:
            return "なし"
        if self.availability is Availability.LEFT_MISSING:
            return "右のみ"
        if self.availability is Availability.RIGHT_MISSING:
            return "左のみ"
        return "同じ" if self.identical else "差分あり"


@dataclass(frozen=True)
class GenerationMetadataDiff:
    """生成メタデータの比較結果 (Issue #1485)。"""

    availability: Availability
    fields: tuple[GenerationFieldDiff, ...] = ()
    positive_prompt: CaptionDiff = field(
        default_factory=lambda: CaptionDiff(availability=Availability.BOTH_MISSING)
    )
    negative_prompt: CaptionDiff = field(
        default_factory=lambda: CaptionDiff(availability=Availability.BOTH_MISSING)
    )
    left_status: GenerationMetadataStatus | None = None
    right_status: GenerationMetadataStatus | None = None

    @property
    def identical(self) -> bool:
        """両側に比較可能な生成メタデータがあり、存在する全項目が一致するか。"""
        if self.availability is not Availability.BOTH:
            return False
        if self.left_status in (GenerationMetadataStatus.UNSUPPORTED, GenerationMetadataStatus.FAILED):
            return False
        if self.right_status in (GenerationMetadataStatus.UNSUPPORTED, GenerationMetadataStatus.FAILED):
            return False
        present = [f for f in self.fields if f.availability is not Availability.BOTH_MISSING]
        return bool(present) and all(f.identical for f in present)

    @property
    def matching_fields(self) -> tuple[GenerationFieldDiff, ...]:
        """両側に値があり一致している項目。"""
        return tuple(f for f in self.fields if f.identical)

    @property
    def differing_fields(self) -> tuple[GenerationFieldDiff, ...]:
        """少なくとも片側に値があり、左右で異なる項目。"""
        return tuple(f for f in self.fields if f.changed)

    def get_field(self, key: str) -> GenerationFieldDiff | None:
        """項目キーで比較結果を取り出す。"""
        canonical = _FIELD_ALIASES.get(key, key)
        for item in self.fields:
            if item.key in (key, canonical):
                return item
        return None


def _build_field_diff(
    key: str,
    label: str,
    left_raw: Any,
    right_raw: Any,
    left_display: str | None = None,
    right_display: str | None = None,
) -> GenerationFieldDiff:
    has_left = left_raw is not None
    has_right = right_raw is not None
    availability = _availability(has_left, has_right)
    return GenerationFieldDiff(
        key=key,
        label=label,
        availability=availability,
        left_raw=left_raw if has_left else None,
        right_raw=right_raw if has_right else None,
        left_display=(left_display if left_display is not None else str(left_raw)) if has_left else "なし",
        right_display=(
            (right_display if right_display is not None else str(right_raw)) if has_right else "なし"
        ),
    )


def diff_generation_metadata(
    left: ComparisonGenerationMetadata,
    right: ComparisonGenerationMetadata,
) -> GenerationMetadataDiff:
    """左右の生成メタデータを項目別に比べる (Issue #1485)。

    生成メタデータが無い側 (``has_metadata=False``) の項目はすべて欠落 (``"なし"``) とし、
    空文字や欠落同士を「同じ」とは判定しない。
    """
    has_left = left.has_metadata
    has_right = right.has_metadata
    availability = _availability(has_left, has_right)

    left_tool = _non_empty_str(left.tool) if has_left else None
    right_tool = _non_empty_str(right.tool) if has_right else None
    left_status_raw = left.status.value if (has_left and left.status is not None) else None
    right_status_raw = right.status.value if (has_right and right.status is not None) else None
    left_pos = _non_empty_str(left.positive_prompt) if has_left else None
    right_pos = _non_empty_str(right.positive_prompt) if has_right else None
    left_neg = _non_empty_str(left.negative_prompt) if has_left else None
    right_neg = _non_empty_str(right.negative_prompt) if has_right else None
    left_model = _non_empty_str(left.model_name) if has_left else None
    right_model = _non_empty_str(right.model_name) if has_right else None
    left_hash = _non_empty_str(left.model_hash) if has_left else None
    right_hash = _non_empty_str(right.model_hash) if has_right else None
    left_loras = left.loras if (has_left and left.loras) else None
    right_loras = right.loras if (right_has_loras := (has_right and bool(right.loras))) else None
    left_seed = _non_empty_str(left.seed) if has_left else None
    right_seed = _non_empty_str(right.seed) if has_right else None
    left_steps = left.steps if has_left else None
    right_steps = right.steps if has_right else None
    left_sampler = _non_empty_str(left.sampler) if has_left else None
    right_sampler = _non_empty_str(right.sampler) if has_right else None
    left_scheduler = left.scheduler if has_left else None
    right_scheduler = right.scheduler if has_right else None
    left_cfg = left.cfg_scale if has_left else None
    right_cfg = right.cfg_scale if has_right else None
    left_denoise = left.denoise if has_left else None
    right_denoise = right.denoise if has_right else None

    fields: list[GenerationFieldDiff] = [
        _build_field_diff(
            "tool",
            "生成ツール",
            left_tool,
            right_tool,
            _TOOL_LABELS.get(left_tool, left_tool) if left_tool else None,
            _TOOL_LABELS.get(right_tool, right_tool) if right_tool else None,
        ),
        _build_field_diff(
            "status",
            "解析状態",
            left_status_raw,
            right_status_raw,
            _STATUS_LABELS.get(left.status, left_status_raw) if (left_status_raw and left.status) else None,
            (
                _STATUS_LABELS.get(right.status, right_status_raw)
                if (right_status_raw and right.status)
                else None
            ),
        ),
        _build_field_diff("model_name", "モデル", left_model, right_model),
        _build_field_diff("model_hash", "モデルハッシュ", left_hash, right_hash),
        _build_field_diff(
            "loras",
            "LoRA",
            left_loras,
            right_loras,
            _format_loras(left.loras) if left_loras is not None else None,
            _format_loras(right.loras) if right_has_loras else None,
        ),
        _build_field_diff("positive_prompt", "正プロンプト", left_pos, right_pos),
        _build_field_diff("negative_prompt", "負プロンプト", left_neg, right_neg),
        _build_field_diff("seed", "Seed", left_seed, right_seed),
        _build_field_diff("steps", "Steps", left_steps, right_steps),
        _build_field_diff("sampler", "Sampler", left_sampler, right_sampler),
        _build_field_diff("scheduler", "Scheduler", left_scheduler, right_scheduler),
        _build_field_diff(
            "cfg_scale",
            "CFG scale",
            left_cfg,
            right_cfg,
            _format_cfg(left_cfg) if left_cfg is not None else None,
            _format_cfg(right_cfg) if right_cfg is not None else None,
        ),
        _build_field_diff("denoise", "Denoise", left_denoise, right_denoise),
    ]

    extra_keys: list[str] = []
    if has_left:
        extra_keys.extend(k for k in left.extra if k not in _RESERVED_EXTRA_KEYS)
    if has_right:
        extra_keys.extend(k for k in right.extra if k not in _RESERVED_EXTRA_KEYS and k not in extra_keys)
    for extra_key in extra_keys:
        l_val = _non_empty_str(left.extra.get(extra_key)) if has_left else None
        r_val = _non_empty_str(right.extra.get(extra_key)) if has_right else None
        fields.append(_build_field_diff(f"extra:{extra_key}", extra_key, l_val, r_val))

    return GenerationMetadataDiff(
        availability=availability,
        fields=tuple(fields),
        positive_prompt=diff_caption(left_pos, right_pos),
        negative_prompt=diff_caption(left_neg, right_neg),
        left_status=left.status if has_left else None,
        right_status=right.status if has_right else None,
    )


def _coerce_status(raw_status: Any) -> GenerationMetadataStatus | None:
    if raw_status is None:
        return None
    if isinstance(raw_status, GenerationMetadataStatus):
        return raw_status
    text = str(raw_status).strip().lower()
    if not text:
        return None
    if text == "none":
        return GenerationMetadataStatus.NO_METADATA
    try:
        return GenerationMetadataStatus(text)
    except ValueError:
        return GenerationMetadataStatus.UNSUPPORTED


def _coerce_loras(raw_loras: Any) -> tuple[LoraReference, ...]:
    if not raw_loras:
        return ()
    if isinstance(raw_loras, str):
        try:
            raw_loras = json.loads(raw_loras)
        except json.JSONDecodeError:
            return ()
    if not isinstance(raw_loras, Iterable):
        return ()
    items: list[LoraReference] = []
    for entry in raw_loras:
        if isinstance(entry, LoraReference):
            items.append(entry)
        elif isinstance(entry, dict) and entry.get("name"):
            weight = entry.get("weight")
            items.append(
                LoraReference(
                    name=str(entry["name"]),
                    weight=str(weight) if weight is not None and str(weight) != "" else None,
                    kind=str(entry.get("kind") or "lora"),
                )
            )
        elif isinstance(entry, str) and entry:
            items.append(LoraReference(name=entry, weight=None))
    return tuple(items)


def _coerce_extra(raw_extra: Any) -> dict[str, str]:
    if not raw_extra:
        return {}
    if isinstance(raw_extra, str):
        try:
            raw_extra = json.loads(raw_extra)
        except json.JSONDecodeError:
            return {}
    if not isinstance(raw_extra, dict):
        return {}
    return {str(k): str(v) for k, v in raw_extra.items() if v is not None and str(v) != ""}


def _field_value(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _coerce_sources(
    raw_sources: Iterable[Any] | None, fallback_obj: Any = None
) -> tuple[GenerationMetadataSource, ...]:
    sources: list[GenerationMetadataSource] = []
    for item in raw_sources or ():
        if isinstance(item, GenerationMetadataSource):
            sources.append(item)
        elif isinstance(item, dict):
            kind_str = str(item.get("kind") or item.get("source_kind") or "png_text")
            key_str = str(item.get("key") or item.get("source_key") or "parameters")
            raw_text = item.get("raw_text")
            raw_bytes = item.get("raw_bytes")
            sources.append(
                GenerationMetadataSource(
                    kind=kind_str,
                    key=key_str,
                    raw_text=str(raw_text) if raw_text is not None else None,
                    raw_bytes=bytes(raw_bytes) if isinstance(raw_bytes, (bytes, bytearray)) else None,
                )
            )
        else:
            raw_kind = getattr(item, "kind", None) or getattr(item, "source_kind", None)
            raw_key = getattr(item, "key", None) or getattr(item, "source_key", None)
            if raw_kind and raw_key:
                raw_text = getattr(item, "raw_text", None)
                raw_bytes = getattr(item, "raw_bytes", None)
                sources.append(
                    GenerationMetadataSource(
                        kind=str(raw_kind),
                        key=str(raw_key),
                        raw_text=str(raw_text) if raw_text is not None else None,
                        raw_bytes=bytes(raw_bytes) if isinstance(raw_bytes, (bytes, bytearray)) else None,
                    )
                )
    if not sources and fallback_obj is not None:
        for attr, key_name in (
            ("raw_parameters", "parameters"),
            ("raw_prompt", "prompt"),
            ("raw_workflow", "workflow"),
        ):
            val = _field_value(fallback_obj, attr)
            if isinstance(val, str) and val != "":
                sources.append(GenerationMetadataSource(kind="png_text", key=key_name, raw_text=val))
    return tuple(sources)


def generation_metadata_from_record(
    record: Any,
    sources: Iterable[Any] = (),
) -> ComparisonGenerationMetadata:
    """DB 行・``GenerationMetadataResult``・辞書から ``ComparisonGenerationMetadata`` を作る。"""
    if record is None:
        coerced_sources = _coerce_sources(sources)
        if not coerced_sources:
            return ComparisonGenerationMetadata()
        return ComparisonGenerationMetadata(
            status=GenerationMetadataStatus.UNSUPPORTED,
            sources=coerced_sources,
        )
    if isinstance(record, ComparisonGenerationMetadata):
        if sources and not record.sources:
            return ComparisonGenerationMetadata(
                status=record.status,
                tool=record.tool,
                positive_prompt=record.positive_prompt,
                negative_prompt=record.negative_prompt,
                model_name=record.model_name,
                model_hash=record.model_hash,
                seed=record.seed,
                steps=record.steps,
                sampler=record.sampler,
                cfg_scale=record.cfg_scale,
                loras=record.loras,
                extra=dict(record.extra),
                sources=_coerce_sources(sources, record),
                error_message=record.error_message,
            )
        return record
    if isinstance(record, GenerationMetadataResult):
        params = record.parameters
        combined_sources = _coerce_sources(sources or record.sources)
        return ComparisonGenerationMetadata(
            status=record.status,
            tool=_non_empty_str(record.tool),
            positive_prompt=_non_empty_str(params.positive_prompt) if params else None,
            negative_prompt=_non_empty_str(params.negative_prompt) if params else None,
            model_name=_non_empty_str(params.model_name) if params else None,
            model_hash=_non_empty_str(params.model_hash) if params else None,
            seed=_non_empty_str(params.seed) if params else None,
            steps=params.steps if params else None,
            sampler=_non_empty_str(params.sampler) if params else None,
            cfg_scale=params.cfg_scale if params else None,
            loras=params.loras if params else (),
            extra=dict(params.extra) if params else {},
            sources=combined_sources,
            error_message=_non_empty_str(record.error_message),
        )

    status = _coerce_status(_field_value(record, "status"))
    loras = _coerce_loras(_field_value(record, "loras") or _field_value(record, "loras_json"))
    extra = _coerce_extra(_field_value(record, "extra") or _field_value(record, "extra_json"))
    scheduler_val = _non_empty_str(_field_value(record, "scheduler"))
    if scheduler_val is not None and not any(k in extra for k in _SCHEDULER_KEYS):
        extra["Schedule type"] = scheduler_val
    denoise_val = _non_empty_str(
        _field_value(record, "denoise") or _field_value(record, "denoising_strength")
    )
    if denoise_val is not None and not any(k in extra for k in _DENOISE_KEYS):
        extra["Denoising strength"] = denoise_val

    cfg_raw = _field_value(record, "cfg_scale")
    if cfg_raw is None:
        cfg_raw = _field_value(record, "cfg")
    cfg_scale = float(cfg_raw) if isinstance(cfg_raw, (int, float)) else None
    steps_raw = _field_value(record, "steps")
    steps = int(steps_raw) if isinstance(steps_raw, int) and not isinstance(steps_raw, bool) else None
    seed_raw = _field_value(record, "seed")
    seed = str(seed_raw) if seed_raw is not None and str(seed_raw) != "" else None
    record_sources = _field_value(record, "sources")
    combined_sources = _coerce_sources(sources or record_sources, record)

    return ComparisonGenerationMetadata(
        status=status,
        tool=_non_empty_str(_field_value(record, "tool")),
        positive_prompt=_non_empty_str(_field_value(record, "positive_prompt")),
        negative_prompt=_non_empty_str(_field_value(record, "negative_prompt")),
        model_name=_non_empty_str(_field_value(record, "model_name")),
        model_hash=_non_empty_str(_field_value(record, "model_hash")),
        seed=seed,
        steps=steps,
        sampler=_non_empty_str(_field_value(record, "sampler")),
        cfg_scale=cfg_scale,
        loras=loras,
        extra=extra,
        sources=combined_sources,
        error_message=_non_empty_str(_field_value(record, "error_message")),
    )


@dataclass(frozen=True)
class ComparisonTag:
    """比較用のタグ 1 件と、その出所 (``モデル名 (AI)`` / ``手動`` 等)。"""

    tag: str
    origins: tuple[str, ...]


@dataclass(frozen=True)
class ComparisonSnapshot:
    """比較の片側に表示する、画像 1 枚の現在の注釈と生成メタデータ。

    Attributes:
        image_id: 画像 ID。
        found: DB に画像が見つかったか。
        stored_image_path: 表示に使う保存先パス (DB の値のまま)。
        original_file_name: 登録元のファイル名。
        image_size: (幅, 高さ)。不明なら None。
        tags: 採用中のタグ (重複をまとめた並び順)。0 件なら空。
        caption: 採用中の最新キャプション。未登録なら None。
        caption_origin: キャプションの出所。未登録なら None。
        generation_metadata: 生成メタデータ (原データと共通項目)。無ければ ``has_metadata=False``。
    """

    image_id: int
    found: bool
    stored_image_path: str | None = None
    original_file_name: str = ""
    image_size: tuple[int, int] | None = None
    tags: tuple[ComparisonTag, ...] = ()
    caption: str | None = None
    caption_origin: str | None = None
    generation_metadata: ComparisonGenerationMetadata = field(default_factory=ComparisonGenerationMetadata)
    _tag_origin_counts: tuple[tuple[str, int], ...] = field(default=(), repr=False)

    @property
    def tag_names(self) -> tuple[str, ...]:
        """タグ名の並び。"""
        return tuple(t.tag for t in self.tags)

    def provenance_lines(self) -> list[str]:
        """表示中の情報の出所を、人が読む行の並びで返す。"""
        if not self.found:
            return [f"画像 ID: {self.image_id}", "DB に画像が見つかりません"]
        lines = [f"画像 ID: {self.image_id}"]
        if self.original_file_name:
            lines.append(f"ファイル: {self.original_file_name}")
        if self.stored_image_path:
            lines.append(f"保存先: {self.stored_image_path}")
        if self.image_size is not None:
            lines.append(f"解像度: {self.image_size[0]} × {self.image_size[1]} px")
        if self.tags:
            sources = ", ".join(f"{origin} ×{count}" for origin, count in self._tag_origin_counts)
            lines.append(f"タグ: {len(self.tags)} 件 ({sources})")
        else:
            lines.append("タグ: なし")
        if self.caption is not None:
            lines.append(f"キャプション: {self.caption_origin or '出所不明'}")
        else:
            lines.append("キャプション: なし")
        lines.append(f"生成メタデータ: {self.generation_metadata.summary_label()}")
        return lines


def _origin_label(annotation: dict[str, Any]) -> str:
    """タグ / キャプション 1 件の出所の表示名。"""
    model_name = annotation.get("model_name")
    has_model = bool(model_name) and model_name != "Unknown"
    manual = bool(annotation.get("is_edited_manually")) or annotation.get("source") == "Manual"
    if has_model:
        return f"{model_name} ({'手動編集' if manual else 'AI'})"
    return "手動" if manual else "出所不明"


def _caption_entry(metadata: dict[str, Any]) -> tuple[str | None, str | None]:
    """表示する最新キャプションと出所を返す (詳細ペインと同じく created_at 最新を採る)。"""
    captions = [c for c in metadata.get("captions") or [] if isinstance(c, dict) and c.get("caption")]
    if captions:
        latest = max(captions, key=lambda c: c.get("created_at") or datetime.min)
        return str(latest["caption"]), _origin_label(latest)
    caption_text = metadata.get("caption_text")
    if caption_text:
        return str(caption_text), None
    return None, None


def snapshot_from_metadata(
    image_id: int,
    metadata: dict[str, Any] | None,
    *,
    generation_metadata: Any = None,
    generation_sources: Iterable[Any] = (),
) -> ComparisonSnapshot:
    """``ImageRepository.get_image_metadata`` の辞書から比較用スナップショットを作る。

    Args:
        image_id: 要求した画像 ID。
        metadata: 画像メタデータ。画像が見つからなければ None。
        generation_metadata: 生成メタデータの解析結果 (省略時は ``metadata["generation_metadata"]``)。
        generation_sources: 生成メタデータの原データ一覧。

    Returns:
        比較の片側に表示するスナップショット。
    """
    if metadata is None:
        return ComparisonSnapshot(image_id=image_id, found=False)

    origins_by_tag: dict[str, list[str]] = {}
    origin_counter: Counter[str] = Counter()
    for entry in metadata.get("tags") or []:
        if not isinstance(entry, dict) or not entry.get("tag"):
            continue
        tag = str(entry["tag"])
        origin = _origin_label(entry)
        origin_counter[origin] += 1
        origins = origins_by_tag.setdefault(tag, [])
        if origin not in origins:
            origins.append(origin)

    caption, caption_origin = _caption_entry(metadata)
    width = metadata.get("width")
    height = metadata.get("height")
    image_size = (int(width), int(height)) if width and height else None
    original_path = metadata.get("original_image_path") or ""
    stored_path = metadata.get("stored_image_path")
    gen_record = (
        generation_metadata if generation_metadata is not None else metadata.get("generation_metadata")
    )
    gen_sources = generation_sources or metadata.get("generation_metadata_sources") or ()

    return ComparisonSnapshot(
        image_id=image_id,
        found=True,
        stored_image_path=str(stored_path) if stored_path else None,
        original_file_name=PurePath(str(original_path)).name if original_path else "",
        image_size=image_size,
        tags=tuple(ComparisonTag(tag=t, origins=tuple(o)) for t, o in origins_by_tag.items()),
        caption=caption,
        caption_origin=caption_origin,
        generation_metadata=generation_metadata_from_record(gen_record, gen_sources),
        _tag_origin_counts=tuple(origin_counter.most_common()),
    )


@dataclass(frozen=True)
class ComparisonResult:
    """左右の比較結果。"""

    left_id: int
    right_id: int
    tags: TagDiff
    caption: CaptionDiff
    generation: GenerationMetadataDiff = field(
        default_factory=lambda: GenerationMetadataDiff(availability=Availability.BOTH_MISSING)
    )


def compare_snapshots(left: ComparisonSnapshot, right: ComparisonSnapshot) -> ComparisonResult:
    """左右のスナップショットのタグ・キャプション・生成メタデータを比べる。"""
    return ComparisonResult(
        left_id=left.image_id,
        right_id=right.image_id,
        tags=diff_tags(left.tag_names, right.tag_names),
        caption=diff_caption(left.caption, right.caption),
        generation=diff_generation_metadata(left.generation_metadata, right.generation_metadata),
    )


class ImageMetadataSource(Protocol):
    """画像メタデータの取得元 (``ImageDatabaseManager`` が満たす)。"""

    def get_image_metadata(self, image_id: int) -> dict[str, Any] | None:
        """画像 1 枚のメタデータ。見つからなければ None。"""
        ...


class ImageComparisonService:
    """比較画面のための読み取り専用サービス。"""

    def __init__(self, source: ImageMetadataSource) -> None:
        """取得元を受け取る。

        Args:
            source: 画像メタデータの取得元。
        """
        self._source = source

    def load_snapshot(self, image_id: int) -> ComparisonSnapshot:
        """画像 1 枚の現在の注釈と生成メタデータを読む (書き込みはしない)。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元へ伝播する。
        """
        metadata = self._source.get_image_metadata(image_id)
        if metadata is None:
            return ComparisonSnapshot(image_id=image_id, found=False)
        get_gen = getattr(self._source, "get_generation_metadata", None)
        gen_record = get_gen(image_id) if callable(get_gen) else None
        get_sources = getattr(self._source, "get_generation_metadata_sources", None)
        gen_sources = get_sources(image_id) if callable(get_sources) else ()
        return snapshot_from_metadata(
            image_id,
            metadata,
            generation_metadata=gen_record,
            generation_sources=gen_sources,
        )


class ComparisonSelection:
    """比較の左右に表示する画像と、片側固定の状態。

    候補は重複を除いた順序付きの画像 ID。左右に同じ画像は置かない。
    """

    def __init__(self, candidates: list[int]) -> None:
        """候補の先頭 2 枚を左右に置く。

        Raises:
            ValueError: 重複を除いた候補が 2 枚未満のとき。
        """
        unique = tuple(dict.fromkeys(candidates))
        if len(unique) < 2:
            raise ValueError("比較には異なる画像が 2 枚以上必要です")
        self._candidates = unique
        self._ids: dict[Side, int] = {Side.LEFT: unique[0], Side.RIGHT: unique[1]}
        self._pinned: dict[Side, bool] = {Side.LEFT: False, Side.RIGHT: False}

    @property
    def candidates(self) -> tuple[int, ...]:
        """候補の画像 ID。"""
        return self._candidates

    @property
    def left_id(self) -> int:
        """左の画像 ID。"""
        return self._ids[Side.LEFT]

    @property
    def right_id(self) -> int:
        """右の画像 ID。"""
        return self._ids[Side.RIGHT]

    def image_id(self, side: Side) -> int:
        """指定した側の画像 ID。"""
        return self._ids[side]

    def is_pinned(self, side: Side) -> bool:
        """指定した側が固定されているか。"""
        return self._pinned[side]

    def set_pinned(self, side: Side, pinned: bool) -> None:
        """指定した側の固定を切り替える。"""
        self._pinned[side] = pinned

    def swap(self) -> None:
        """左右を入れ替える。固定は画像と一緒に移る。"""
        self._ids[Side.LEFT], self._ids[Side.RIGHT] = self._ids[Side.RIGHT], self._ids[Side.LEFT]
        self._pinned[Side.LEFT], self._pinned[Side.RIGHT] = (
            self._pinned[Side.RIGHT],
            self._pinned[Side.LEFT],
        )

    def set_side(self, side: Side, image_id: int) -> bool:
        """指定した側の画像を変える。

        Returns:
            変えたら True。固定中・候補外・反対側と同じ画像のときは False。
        """
        if self._pinned[side] or image_id not in self._candidates:
            return False
        if image_id == self._ids[side.other]:
            return False
        changed = self._ids[side] != image_id
        self._ids[side] = image_id
        return changed

    def step(self, side: Side, delta: int) -> bool:
        """指定した側を候補の前後に送る (反対側の画像は飛ばし、端で一周する)。

        Returns:
            変えたら True。固定中や他に候補が無いときは False。
        """
        if self._pinned[side] or delta == 0:
            return False
        count = len(self._candidates)
        index = self._candidates.index(self._ids[side])
        direction = 1 if delta > 0 else -1
        for offset in range(1, count):
            candidate = self._candidates[(index + direction * offset) % count]
            if candidate != self._ids[side.other]:
                self._ids[side] = candidate
                return True
        return False
