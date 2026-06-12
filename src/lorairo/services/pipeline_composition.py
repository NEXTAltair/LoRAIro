# src/lorairo/services/pipeline_composition.py
"""アノテーションパイプライン構成の Qt-free ドメインモデル (Wireframes v11 Frame 2A / Phase 6a)。

ステージ中心パイプライン (TAGS/CAPTION/SCORE/RATING) のモデル割当状態と、
multimodal 派生出力・推論台帳 (INFERENCE LEDGER) の計算を担う。

設計確定事項 (デザインセッション 2026-06-11 / docs/design/wireframes-v11):
- multimodal の AnnotationSchema は {tags, captions, score} 固定 — 派生は
  TAGS / CAPTION / SCORE のみで RATING には決して届かない (ADR 0023/0031)
- 派生チップは read-only (opt-out なし)。不要な派生出力は Results の
  soft-reject (#719) で事後却下する
- 推論回数 = ユニークモデル数 × ステージング枚数。同一モデルを複数ステージに
  明示割当しても dedupe され、コストは増えない
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class PipelineStage(StrEnum):
    """パイプラインの出力ステージ (Wireframes v11 Frame 2A の 4 行)。"""

    TAGS = "tags"
    CAPTION = "caption"
    SCORE = "score"
    RATING = "rating"


# capability 名 (model_types) → ステージの対応。
# "multimodal" は capability ではなく派生挙動のマーカーなので含めない。
CAPABILITY_TO_STAGE: dict[str, PipelineStage] = {
    "tags": PipelineStage.TAGS,
    "caption": PipelineStage.CAPTION,
    "scores": PipelineStage.SCORE,
    "ratings": PipelineStage.RATING,
}

# multimodal モデルの 1 推論が埋めるステージ集合 (AnnotationSchema 固定)。
MULTIMODAL_FILL_STAGES: frozenset[PipelineStage] = frozenset(
    {PipelineStage.TAGS, PipelineStage.CAPTION, PipelineStage.SCORE}
)


@dataclass(frozen=True)
class StageModelInfo:
    """ステージに割り当てるモデルの表示・計算用スナップショット。

    Attributes:
        litellm_model_id: モデルの一意キー (Model.litellm_model_id)。
        display_name: チップに表示する名前 (Model.name)。
        provider: プロバイダ名。ローカル ML は None。
        is_api: WebAPI モデルなら True、ローカル ML なら False。
        capabilities: model_types 由来の capability 名集合
            ({"tags", "caption", "scores", "ratings", "multimodal"} の部分集合)。
        input_cost_per_token: LiteLLM 由来の input トークン単価 (USD/token)。
            ローカル ML / pricing 未取得の API モデルは None (Issue #747)。
        output_cost_per_token: LiteLLM 由来の output トークン単価 (USD/token)。
            ローカル ML / pricing 未取得の API モデルは None (Issue #747)。
    """

    litellm_model_id: str
    display_name: str
    provider: str | None
    is_api: bool
    capabilities: frozenset[str]
    input_cost_per_token: float | None = None
    output_cost_per_token: float | None = None

    @property
    def is_multimodal(self) -> bool:
        """1 推論で複数出力を返す WebAPI multimodal モデルか。"""
        return self.is_api and "multimodal" in self.capabilities

    def fill_stages(self) -> frozenset[PipelineStage]:
        """このモデルの 1 推論が出力を届けるステージ集合を返す。"""
        if self.is_multimodal:
            return MULTIMODAL_FILL_STAGES
        stages = {CAPABILITY_TO_STAGE[name] for name in self.capabilities if name in CAPABILITY_TO_STAGE}
        return frozenset(stages)


@dataclass(frozen=True)
class DerivedChip:
    """派生チップ (↝): 同一推論の副産物としてステージに届く出力。read-only。"""

    model: StageModelInfo
    origin_stage: PipelineStage


@dataclass(frozen=True)
class StageRow:
    """ステージテーブルの 1 行分の表示データ。"""

    stage: PipelineStage
    primary_models: tuple[StageModelInfo, ...]
    derived_chips: tuple[DerivedChip, ...]


@dataclass(frozen=True)
class LedgerEntry:
    """推論台帳の 1 エントリ (ユニークモデル単位)。"""

    model: StageModelInfo
    stage_count: int  # このモデルが出力を届けるステージ数 (明示+派生)


@dataclass(frozen=True)
class InferenceLedger:
    """INFERENCE LEDGER: 推論回数 = ユニークモデル × ステージング枚数。"""

    entries: tuple[LedgerEntry, ...]
    staged_count: int
    unique_model_count: int = field(init=False)
    total_jobs: int = field(init=False)
    local_count: int = field(init=False)
    api_count: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "unique_model_count", len(self.entries))
        object.__setattr__(self, "total_jobs", len(self.entries) * self.staged_count)
        object.__setattr__(self, "local_count", sum(1 for e in self.entries if not e.model.is_api))
        object.__setattr__(self, "api_count", sum(1 for e in self.entries if e.model.is_api))


class PipelineCompositionService:
    """ステージ割当状態を保持し、派生表示と推論台帳を計算する (Qt-free)。

    Phase 6a では選択モデル集合からの自動仕分け (`compose_from_models`) を
    入力経路とし、Phase 6b で per-stage 明示割当 (`assign`/`remove`) に拡張する。
    """

    def __init__(self) -> None:
        self._assignments: dict[PipelineStage, list[StageModelInfo]] = {
            stage: [] for stage in PipelineStage
        }

    # --- 入力 (Track A 実装) -------------------------------------------------

    def compose_from_models(self, models: list[StageModelInfo]) -> None:
        """選択モデル集合をステージへ自動仕分けする (Phase 6a の入力経路)。

        - multimodal モデルは CAPTION に明示割当 (v11: 1 推論の主目的を caption とみなす)
        - 非 multimodal は capability が対応する各ステージに明示割当
        - 同一 litellm_model_id の重複入力は 1 つに dedupe
        - 呼ぶたびに既存の割当をクリアして作り直す
        """
        self._assignments = {stage: [] for stage in PipelineStage}
        seen_ids: set[str] = set()
        for model in models:
            if model.litellm_model_id in seen_ids:
                continue
            seen_ids.add(model.litellm_model_id)
            if model.is_multimodal:
                self.assign(PipelineStage.CAPTION, model)
                continue
            target_stages = model.fill_stages()
            for stage in PipelineStage:
                if stage in target_stages:
                    self.assign(stage, model)

    def assign(self, stage: PipelineStage, model: StageModelInfo) -> None:
        """モデルをステージに明示割当する (Phase 6b)。同一モデルの重複割当は無視。"""
        assigned = self._assignments[stage]
        if any(m.litellm_model_id == model.litellm_model_id for m in assigned):
            return
        assigned.append(model)

    def remove(self, stage: PipelineStage, litellm_model_id: str) -> None:
        """ステージから明示割当を外す (Phase 6b)。派生チップは外せない。該当なしは no-op。"""
        self._assignments[stage] = [
            m for m in self._assignments[stage] if m.litellm_model_id != litellm_model_id
        ]

    # --- 出力 (Track A 実装) -------------------------------------------------

    def stage_rows(self) -> list[StageRow]:
        """4 ステージ分の表示行 (明示チップ + 派生チップ) を返す。

        派生チップは明示割当済み multimodal モデルの fill_stages のうち、
        そのモデルが明示割当されていないステージに出す。RATING は
        MULTIMODAL_FILL_STAGES に含まれないため派生が届くことはない。
        """
        origins = self._multimodal_origins()
        rows: list[StageRow] = []
        for stage in PipelineStage:
            primary = tuple(self._assignments[stage])
            primary_ids = {m.litellm_model_id for m in primary}
            chips: list[DerivedChip] = []
            for model_id, (model, origin_stage) in origins.items():
                if stage not in model.fill_stages() or model_id in primary_ids:
                    continue
                chips.append(DerivedChip(model=model, origin_stage=origin_stage))
            rows.append(StageRow(stage=stage, primary_models=primary, derived_chips=tuple(chips)))
        return rows

    def ledger(self, staged_count: int) -> InferenceLedger:
        """推論台帳を返す。multimodal の多段出現は dedupe する。"""
        unique_models: dict[str, StageModelInfo] = {}
        explicit_stages: dict[str, set[PipelineStage]] = {}
        for stage in PipelineStage:
            for model in self._assignments[stage]:
                unique_models.setdefault(model.litellm_model_id, model)
                explicit_stages.setdefault(model.litellm_model_id, set()).add(stage)
        entries: list[LedgerEntry] = []
        for model_id, model in unique_models.items():
            delivered = set(explicit_stages[model_id])
            if model.is_multimodal:
                delivered |= model.fill_stages()
            entries.append(LedgerEntry(model=model, stage_count=len(delivered)))
        return InferenceLedger(entries=tuple(entries), staged_count=staged_count)

    def unique_model_ids(self) -> list[str]:
        """実行に渡すユニーク litellm_model_id リストを返す (割当順)。"""
        ordered_ids: list[str] = []
        for stage in PipelineStage:
            for model in self._assignments[stage]:
                if model.litellm_model_id not in ordered_ids:
                    ordered_ids.append(model.litellm_model_id)
        return ordered_ids

    # --- private -------------------------------------------------------------

    def _multimodal_origins(self) -> dict[str, tuple[StageModelInfo, PipelineStage]]:
        """明示割当済み multimodal モデル → (モデル, 最初の明示割当ステージ)。

        ステージは PipelineStage 定義順に走査し、同一モデルが複数ステージに
        明示割当されている場合は最初に見つかったステージを origin とする。
        """
        origins: dict[str, tuple[StageModelInfo, PipelineStage]] = {}
        for stage in PipelineStage:
            for model in self._assignments[stage]:
                if model.is_multimodal and model.litellm_model_id not in origins:
                    origins[model.litellm_model_id] = (model, stage)
        return origins
