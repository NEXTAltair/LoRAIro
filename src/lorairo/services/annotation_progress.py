"""Confirmed annotation boundaries and elapsed time, without inference API estimates."""

from dataclasses import dataclass
from enum import Enum
from time import monotonic


class AnnotationPhase(Enum):
    PREPARING = "準備中"
    RUNNING = "アノテーション実行中"
    SAVING = "結果保存中"
    CANCELING = "キャンセル要求済み・停止待ち"
    COMPLETED = "完了"
    FAILED = "失敗"
    CANCELED = "キャンセル完了"

    @property
    def is_terminal(self) -> bool:
        return self in {self.COMPLETED, self.FAILED, self.CANCELED}


@dataclass(frozen=True)
class AnnotationProgress:
    """Session-local snapshot; totals are targets, never processed counts."""

    phase: AnnotationPhase
    total_images: int
    total_models: int
    started_at: float
    stopped_at: float | None = None
    result_summary: str = ""

    def elapsed_text(self) -> str:
        end = self.stopped_at if self.stopped_at is not None else monotonic()
        seconds = max(0, int(end - self.started_at))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}時間{minutes:02d}分{seconds:02d}秒"
        return f"{minutes}分{seconds:02d}秒"

    def context_text(self) -> str:
        return f"対象 {self.total_images}枚 / {self.total_models}モデル    経過 {self.elapsed_text()}"

    def detail_text(self) -> str:
        if self.phase in {AnnotationPhase.RUNNING, AnnotationPhase.CANCELING}:
            return "処理済み件数・残り時間は取得できません"
        return self.result_summary
