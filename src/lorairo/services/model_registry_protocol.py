# src/lorairo/services/model_registry_protocol.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

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
