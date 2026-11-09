"""生成メタデータの共有型 (ADR 0105, Issue #1481 / #1503)。

parser (`services/generation_metadata_parser.py`)・Repository・登録経路が共有する plain な型。
Qt / DB / service を import しない。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

PARSER_VERSION = "2"
GENERATION_METADATA_PARSER_VERSION = PARSER_VERSION


class GenerationMetadataStatus(StrEnum):
    """解析状態。未解析 (行が無い) とは別に、解析した結果の状態を表す。"""

    PARSED = "parsed"  # 対応形式で、主要項目をすべて取得できた
    PARTIAL = "partial"  # 対応形式だが、一部の項目が無い / 値を解釈できない
    UNSUPPORTED = "unsupported"  # 原データはあるが、項目を抽出できる形式ではない
    NO_METADATA = "no_metadata"  # 生成情報の原データが見つからない
    FAILED = "failed"  # 原データの取得・復号・解析に失敗した


@dataclass(frozen=True)
class GenerationMetadataSource:
    """解析前の原データ 1 件 (整形しない)。

    Attributes:
        kind: 取得元の種類 (``png_text`` / ``exif``)。
        key: 取得元のキー (PNG チャンク名、EXIF タグ名)。
        raw_text: 文字列として取り出した原文 (PNG チャンクは Pillow の復号結果そのまま)。
            EXIF は ``raw_bytes`` を復号できたときだけ入る。
        raw_bytes: バイト列の原データ (EXIF UserComment)。PNG チャンクは None。
    """

    kind: str
    key: str
    raw_text: str | None
    raw_bytes: bytes | None = None

    @property
    def payload(self) -> bytes:
        """ハッシュ計算に使うバイト列。"""
        if self.raw_bytes is not None:
            return self.raw_bytes
        return (self.raw_text or "").encode("utf-8")

    @property
    def sha256(self) -> str:
        """原データの SHA-256 (16 進)。"""
        return hashlib.sha256(self.payload).hexdigest()


@dataclass(frozen=True)
class LoraReference:
    """プロンプトまたはノード内の LoRA 参照。重みは表記のまま文字列で持つ。"""

    name: str
    weight: str | None
    kind: str = "lora"


@dataclass(frozen=True)
class GenerationParameters:
    """解析で取り出した共通項目。取得できなかった項目は None。"""

    positive_prompt: str | None = None
    negative_prompt: str | None = None
    model_name: str | None = None
    model_hash: str | None = None
    seed: str | None = None
    steps: int | None = None
    sampler: str | None = None
    cfg_scale: float | None = None
    loras: tuple[LoraReference, ...] = ()
    # 共通項目に含めなかった key: value (原文の値のまま)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationMetadataResult:
    """1 画像の生成メタデータの解析結果。"""

    status: GenerationMetadataStatus
    parser_name: str
    parser_version: str = PARSER_VERSION
    tool: str | None = None
    sources: tuple[GenerationMetadataSource, ...] = ()
    parameters: GenerationParameters | None = None
    error_message: str | None = None

    @property
    def error_reason(self) -> str | None:
        """エラー理由 (``error_message`` の別名)。"""
        return self.error_message

    @property
    def input_sha256(self) -> str | None:
        """解析に使った原データ全体の SHA-256。原データが無ければ None。"""
        if not self.sources:
            return None
        digest = hashlib.sha256()
        for source in sorted(self.sources, key=lambda s: (s.kind, s.key)):
            digest.update(f"{source.kind}\0{source.key}\0".encode())
            digest.update(source.sha256.encode("ascii"))
        return digest.hexdigest()

    @property
    def is_ai_generation_evidence(self) -> bool:
        """生成ツール固有の形式に一致したか (#1396 の判定材料)。"""
        return is_ai_generation_evidence(self.tool, self.status)


def is_ai_generation_evidence(tool: str | None, status: GenerationMetadataStatus) -> bool:
    """生成ツールと解析状態から、AI 生成の根拠になるかを返す。

    生成ツールが特定でき、解析状態が parsed / partial / unsupported (ComfyUI の判定のみ)
    のいずれかであるときに True。汎用の文字列一致や画像寸法は根拠にしない。
    """
    if tool is None:
        return False
    return status in (
        GenerationMetadataStatus.PARSED,
        GenerationMetadataStatus.PARTIAL,
        GenerationMetadataStatus.UNSUPPORTED,
    )


@dataclass(frozen=True)
class GenerationEvidence:
    """保存済みの解析結果のうち、AI 生成の判定に使う部分 (ADR 0106)。"""

    tool: str | None
    status: GenerationMetadataStatus

    @property
    def is_ai_generated(self) -> bool:
        """生成ツール固有の形式に一致したか。"""
        return is_ai_generation_evidence(self.tool, self.status)


@dataclass(frozen=True)
class GenerationMetadataAnalysisItem:
    """再解析 1 画像分の処理結果 (ADR 0106)。

    Attributes:
        image_id: 画像 ID。
        action: ``analyzed`` / ``skipped_analyzed`` (解析済みで飛ばした) / ``not_found`` /
            ``file_missing`` / ``save_failed``。
        status: 解析した場合の解析状態。
        tool: 解析した場合の生成ツール。
    """

    image_id: int
    action: str
    status: GenerationMetadataStatus | None = None
    tool: str | None = None


@dataclass(frozen=True)
class AiGeneratedTagBatchResult:
    """保存済みの生成メタデータを根拠に ``ai generated`` を一括付与・取消した結果 (ADR 0107, #1502)。"""

    target_images: int
    evidence_images: int = 0
    tags_added: int = 0
    tags_skipped: int = 0
    tags_revoked: int = 0
    dry_run: bool = False
    revoked: bool = False
