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
    litellm_model_id: 外部APIで使用するモデルID（該当しない場合はNone）
    requires_api_key: APIキーの要否
    estimated_size_gb: ローカルモデルの推定サイズ（APIモデルはNone）
    """

    name: str
    provider: str
    capabilities: list[str]
    litellm_model_id: str | None
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


def selection_includes_webapi_model(
    litellm_model_ids: list[str],
    model_registry: ModelRegistryServiceProtocol,
) -> bool:
    """選択されたモデルに WebAPI モデル (`requires_api_key=True`) が含まれるか判定。

    ADR 0023 Phase 1.5 (Issue #42): SafetyRefusal / ContentPolicyRefusal は
    WebAPI 推論経路 (cloud provider の content policy 拒否) でのみ発生する概念。
    ローカル ML モデル (WD-Tagger 等) の推論は同じ画像でも refusal を返さない
    ため、refusal による事前 filter はローカルモデル単独実行に対して適用しない。

    本関数は Qt-free な pure helper として `services/` 層に置く。GUI 層
    (`worker_service`) と Worker 層 (`gui/workers/annotation_worker`) の双方から
    参照されるため、いずれにも依存しない neutral な場所に配置する必要がある
    (Codex P2 review feedback, PR #233 r3209342204: filter を Worker 内で実行する
    設計に伴う再配置)。

    Issue #245 / ADR 0023 Phase 1.11: lookup キーは `Model.litellm_model_id`
    (registry key SSoT)。`ModelInfo.name` は `AnnotatorInfo.name` をそのまま受け
    継ぐため、WebAPI 経路では `litellm_model_id == ModelInfo.name`、ローカル ML
    経路でも bare 名で同値となる。

    Args:
        litellm_model_ids: 選択されたモデルの `litellm_model_id` リスト。
        model_registry: モデル情報を引ける Protocol 実装。

    Returns:
        bool: 1 つでも `requires_api_key=True` のモデルがあれば True。
            registry に未登録の litellm_model_id は WebAPI ではないと扱う
            (defensive default)。

    Raises:
        例外は呼び出し元で吸収する契約 (Codex P2 review feedback,
        PR #233 r3208793528)。registry の一時的な障害は filter skip の signal と
        して扱い、annotation 全体を abort させない。
    """
    if not litellm_model_ids:
        return False
    available = {info.name: info for info in model_registry.get_available_models()}
    return any(
        (info := available.get(key)) is not None and info.requires_api_key for key in litellm_model_ids
    )
