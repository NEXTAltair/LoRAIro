# src/lorairo/services/model_registry_protocol.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..utils.log import logger


@dataclass(frozen=True)
class ModelInfo:
    """モデル情報（統一データ型）

    name: 一意なモデル識別名
    provider: 提供元（"openai" / "anthropic" / "google" / "local" / "unknown" 等）
    capabilities: 提供機能 ["caption", "tags", "scores"] など
    api_model_id: 外部APIで使用するモデルID（該当しない場合はNone）
    requires_api_key: APIキーの要否
    estimated_size_gb: ローカルモデルの推定サイズ（APIモデルはNone）
    """

    name: str
    provider: str
    capabilities: list[str]
    api_model_id: str | None
    requires_api_key: bool
    estimated_size_gb: float | None

    # 将来の表示用フラグ等は必要になれば追加する（本サブタスクでは最小）


class ModelRegistryServiceProtocol(Protocol):
    """モデルレジストリ取得の抽象IF（GUIサービス層の統一依存）"""

    def get_available_models(self) -> list[ModelInfo]:
        """利用可能モデル（最小情報を含むModelInfo）の一覧を返す"""
        ...

    def get_available_models_with_metadata(self) -> list[ModelInfo]:
        """同上。互換のための別名（戻り値は同一構造）"""
        ...


class NullModelRegistry(ModelRegistryServiceProtocol):
    """未提供時の縮退用Nullオブジェクト実装（安全フォールバック）

    挙動:
      - 空リストを返却
      - INFOログを記録
      - 例外は発生させない
    ログ方針:
      - 仕様 docs/specs/core/logging_specification.md 準拠
      - 未提供は INFO、実行時障害は WARNING/ERROR（ただし本実装は障害を起こさない）
    """

    def get_available_models(self) -> list[ModelInfo]:
        logger.info("Model registry unavailable; returning empty list (degraded mode)")
        return []

    def get_available_models_with_metadata(self) -> list[ModelInfo]:
        logger.info("Model registry unavailable; returning empty list (degraded mode)")
        return []


def map_annotator_metadata_to_model_info(items: list[dict[str, Any]]) -> list[ModelInfo]:
    """AnnotatorLibAdapterのメタデータ(dict)をModelInfoに正規化

    非スコープ注意:
      - 本サブタスクでは必要最小限のマッピングに留める
      - 欠損値は仕様に沿ってデフォルトへフォールバック
    """
    normalized: list[ModelInfo] = []

    for raw in items:
        # 既存GUIサービス側の期待キーに合わせて安全に取得
        name = str(raw.get("name", "") or "")
        provider_raw = raw.get("provider", None)
        provider = (provider_raw or "unknown") if isinstance(provider_raw, str) else "unknown"

        # 既存コードの推定ロジックと互換になるように簡易推定
        # ただしここでは最小限: 呼び出し側が別途推論する場合もあるため
        capabilities = _infer_capabilities_min(raw)

        api_model_id = raw.get("api_model_id")
        api_model_id = str(api_model_id) if isinstance(api_model_id, str) else None

        requires_api_key = bool(raw.get("requires_api_key", False))

        size_raw = raw.get("estimated_size_gb", None)
        estimated_size_gb = float(size_raw) if isinstance(size_raw, int | float) else None

        normalized.append(
            ModelInfo(
                name=name,
                provider=provider,
                capabilities=capabilities,
                api_model_id=api_model_id,
                requires_api_key=requires_api_key,
                estimated_size_gb=estimated_size_gb,
            )
        )

    return normalized


def _infer_capabilities_min(raw: dict[str, Any]) -> list[str]:
    """最小限の機能推定（互換重視）

    - raw["model_type"] が存在すれば簡易マッピング
    - 無ければ name, provider からの軽い推測
    - どれも無ければ ["caption"] をデフォルト
    """
    try:
        model_type = str(raw.get("model_type", "") or "").lower()
        if model_type:
            mapping = {
                "multimodal": ["caption", "tags"],
                "vision": ["caption", "tags"],
                "caption": ["caption"],
                "tag": ["tags"],
                "tagger": ["tags"],
                "score": ["scores"],
            }
            if model_type in mapping:
                return mapping[model_type]

        name = str(raw.get("name", "") or "").lower()
        provider = str(raw.get("provider", "") or "").lower()

        if any(k in name for k in ["gpt-4", "claude", "gemini"]):
            return ["caption", "tags"]
        if any(k in name for k in ["gpt-4o", "dall-e"]):
            return ["caption"]
        if any(k in name for k in ["tagger", "danbooru", "wd-", "deepdanbooru", "swinv2"]):
            return ["tags"]
        if any(k in name for k in ["aesthetic", "clip", "musiq", "quality", "score"]):
            return ["scores"]
        if provider in ["openai", "anthropic", "google"]:
            return ["caption", "tags"]
    except Exception as e:
        logger.warning(f"Capability inference fallback due to error: {e}")

    return ["caption"]
