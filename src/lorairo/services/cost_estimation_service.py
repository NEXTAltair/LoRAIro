# src/lorairo/services/cost_estimation_service.py
"""アノテーション推論のコスト概算サービス (Wireframes v11 Frame 2B / Issue #747)。

モデルピッカーのカードと INFERENCE LEDGER に「$/img・推定時間」を概算表示する
ための Qt-free ドメインサービス。litellm の per-token 単価 (実行時取得) に粗い
固定 token 仮定を掛けて 1 枚あたりコストを算出する。

設計判断 (Issue #747):
- ワイヤーフレームは「概算」明示なので **粗い固定 token 仮定** を使う。実際の
  入出力トークン数は画像内容・プロンプト・出力長に依存するため厳密値は出さない。
- litellm pricing は変動するので DB には保存せず実行時に AnnotatorInfo から取得する
  (provider_batch_eligibility と同じ on-demand 思想)。
- ローカル ML モデルは API 課金がないため per-image cost = 0.0 (None ではない)。
  推定時間にはジョブ数として寄与する。
- pricing 未取得の API モデル (litellm に単価がない) は per-image cost = None。
  表示は "—"、バッチ合計では「一部不明」フラグを立てる。
"""

from __future__ import annotations

from dataclasses import dataclass

from lorairo.services.pipeline_composition import InferenceLedger, StageModelInfo

# --- 概算用の固定仮定 (後から調整可能なよう module 定数に集約) ---------------

INPUT_TOKENS_PER_IMAGE = 1500
"""画像 high-detail エンコード + システムプロンプト相当の input トークン概算。"""

OUTPUT_TOKENS_PER_IMAGE = 400
"""構造化出力 (tags + caption + score) 相当の output トークン概算。"""

SECONDS_PER_JOB = 3.0
"""推論 1 ジョブの粗い所要秒数 (ワイヤーの `18 jobs · 推定 48s` ≈ 2.7s/job 由来)。"""

_LOCAL_FREE_LABEL = "ローカル（無料）"
_UNKNOWN_COST_LABEL = "—"


def format_per_image_cost(per_image_usd: float | None, is_api: bool) -> str:
    """1 枚あたりコストを表示用文字列に整形する (カード直載せ用)。

    Args:
        per_image_usd: ``CostEstimationService.per_image_usd`` の戻り値。
        is_api: API モデルなら True。ローカル ML の 0.0 を「無料」と区別するため使う。

    Returns:
        ローカルは "ローカル（無料）"、pricing 未取得は "—"、それ以外は "$0.0050/img"。
    """
    if not is_api:
        return _LOCAL_FREE_LABEL
    if per_image_usd is None:
        return _UNKNOWN_COST_LABEL
    return f"${per_image_usd:.4f}/img"


def format_duration(seconds: float) -> str:
    """推定秒数を表示用文字列に整形する ("48s" / "2m30s")。"""
    total = round(seconds)
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    return f"{minutes}m{secs:02d}s"


@dataclass(frozen=True)
class BatchCostEstimate:
    """バッチ全体のコスト・時間概算。

    Attributes:
        total_usd: per-image cost が判明したモデルの概算コスト合計 (USD)。
        has_unknown: pricing 未取得 (per-image cost = None) のモデルを含むか。
            True のとき total_usd は「判明分のみの下限」を意味する。
        est_seconds: 総推論ジョブ数 × SECONDS_PER_JOB の推定所要秒数。
    """

    total_usd: float
    has_unknown: bool
    est_seconds: float


class CostEstimationService:
    """StageModelInfo / InferenceLedger からコストと時間を概算する (Qt-free)。"""

    def per_image_usd(self, model: StageModelInfo) -> float | None:
        """1 枚あたりの概算コスト (USD) を返す。

        Args:
            model: 対象モデルのスナップショット。

        Returns:
            ローカル ML モデルは 0.0。pricing 未取得の API モデルは None。
            それ以外は固定 token 仮定による概算値。
        """
        if not model.is_api:
            return 0.0
        if model.input_cost_per_token is None or model.output_cost_per_token is None:
            return None
        return (
            INPUT_TOKENS_PER_IMAGE * model.input_cost_per_token
            + OUTPUT_TOKENS_PER_IMAGE * model.output_cost_per_token
        )

    def estimate_batch(self, ledger: InferenceLedger) -> BatchCostEstimate:
        """推論台帳からバッチ全体のコスト・時間概算を返す。

        各ユニークモデルの per-image cost × ステージング枚数を合計する。
        per-image cost が None (pricing 未取得) のモデルは合計から除外しつつ
        has_unknown を立てる。総時間は総ジョブ数 × SECONDS_PER_JOB。

        Args:
            ledger: PipelineCompositionService.ledger() の戻り値。

        Returns:
            BatchCostEstimate: total_usd / has_unknown / est_seconds。
        """
        total_usd = 0.0
        has_unknown = False
        for entry in ledger.entries:
            per_image = self.per_image_usd(entry.model)
            if per_image is None:
                has_unknown = True
                continue
            total_usd += per_image * ledger.staged_count
        est_seconds = ledger.total_jobs * SECONDS_PER_JOB
        return BatchCostEstimate(total_usd=total_usd, has_unknown=has_unknown, est_seconds=est_seconds)
