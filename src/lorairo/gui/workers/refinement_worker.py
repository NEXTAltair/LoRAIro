"""タグ refinement リコメンドの非同期評価ワーカー (#931)。

選択画像のタグ集合を `RefinementService` で評価し、結果を `finished` Signal で返す。
UI スレッドをブロックしないため `LoRAIroWorkerBase` (QObject) 上で実行する。
画像高速切替時のレース対策として結果に image_id を含め、受信側が照合する。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ...utils.log import logger
from .base import LoRAIroWorkerBase

if TYPE_CHECKING:
    from genai_tag_db_tools.models import RefinementRecommendation

    from ...services.refinement_service import RefinementService


@dataclass
class RefinementResult:
    """refinement 評価結果。

    Attributes:
        image_id: 評価対象だった画像 ID (受信側のレース照合用)。
        generation: 起動時の世代番号 (同一 image_id の A→B→A 再選択でも古い結果を弾く)。
        recommendations: needs_refinement=True のタグ → リコメンド。
    """

    image_id: int
    generation: int
    recommendations: dict[str, RefinementRecommendation]
    # 候補タグ -> {format_name: usage_count} (#1052)。評価時に一括解決済み
    candidate_counts: dict[str, dict[str, int]] = field(default_factory=dict)


class RefinementWorker(LoRAIroWorkerBase[RefinementResult]):
    """選択画像のタグ集合を非同期に refinement 評価するワーカー。"""

    _OPERATION_TYPE = "refinement"

    def __init__(
        self,
        refinement_service: RefinementService,
        image_id: int,
        tags: Iterable[str],
        format_map: Mapping[str, str] | None = None,
        repo: object | None = None,
        generation: int = 0,
    ) -> None:
        """RefinementWorker を初期化する。

        Args:
            refinement_service: 評価を委譲する Qt-free サービス。
            image_id: 評価対象の画像 ID。
            tags: 評価対象のタグ文字列。
            format_map: タグ→format_name のマップ。
            repo: lib に渡す DB リーダー。
            generation: 起動世代 (受信側のレース照合用)。
        """
        super().__init__()
        self._service = refinement_service
        self._image_id = image_id
        self._tags = list(tags)
        self._format_map = format_map
        self._repo = repo
        self._generation = generation

    def execute(self) -> RefinementResult:
        """タグ集合を評価し RefinementResult を返す。

        `cancel_check` として `_check_cancellation` を渡し、prefetch / per-tag 評価の
        DB 往復の合間で協調キャンセルを効かせる (#1024)。キャンセル時は
        `CancellationError` が伝播し、`run()` が canceled シグナルで終端する。
        """
        recommendations = self._service.recommend_for_tags(
            self._tags,
            format_map=self._format_map,
            repo=self._repo,
            cancel_check=self._check_cancellation,
        )
        # 候補タグの使用カウントも worker スレッド内で一括解決する
        # (メインスレッドで tag DB を待たない #1046 方針と整合。#1052)
        candidate_counts = self._service.resolve_candidate_counts(recommendations, repo=self._repo)
        logger.debug(
            f"refinement worker 完了: image_id={self._image_id}, gen={self._generation}, "
            f"対象={len(self._tags)}, 表示={len(recommendations)}"
        )
        return RefinementResult(
            image_id=self._image_id,
            generation=self._generation,
            recommendations=recommendations,
            candidate_counts=candidate_counts,
        )
