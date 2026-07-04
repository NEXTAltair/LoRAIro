"""Provider Batch の結果回収 (refresh→fetch→import) を GUI スレッド外で実行する worker。

Issue #1158: Jobs タブの「結果を取得」/「状態を確認」は ``refresh → fetch_results →
import_results`` を GUI スレッドで直列実行していた。import は画像ごとに数百タグ +
レーティングを DB 書き込みするため、大量結果でイベントループが長時間ブロックし
実機フリーズを起こしていた (#1140 読み取り側フリーズの書き込み版)。本 worker は
その連鎖を専用 QThread へ移し、GUI をブロックしない。

``ProviderBatchWorkflowService`` は Qt-free でスレッド非依存 (repository は呼び出し毎に
短命セッションを開く) なので、そのまま worker スレッドで実行できる。呼び出し側
(``ProviderBatchJobWidget``) は再入ガードと QThread 配線を担う
(``AnnotationWorkflowController._start_async_dispatch_worker`` と同形、ADR 0044)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from PySide6.QtCore import QObject, Signal, Slot

_COMPLETED_STATUS = "completed"
_IMPORTED_STATUS = "imported"

CollectKind = Literal["imported", "collected", "status"]


@dataclass(frozen=True)
class ProviderBatchCollectOutcome:
    """1 ジョブの結果回収の成果 (GUI 側でメッセージ整形に使う純データ)。

    Qt に依存しないため worker スレッドで安全に構築でき、``succeeded`` で GUI へ
    marshal される。GUI 側は本データからステータス文言を組み立てるだけで、DB 再取得
    (2回読み) をしない。

    Attributes:
        kind: ``imported`` = 既に保存済み / ``collected`` = fetch+import を実行した /
            ``status`` = 未完了で状態確認のみ。
        job: refresh 後のジョブレコード (status メッセージ整形用)。
        import_result: ``collected`` のときの ``ProviderBatchImportResult`` (件数表示用)。
    """

    kind: CollectKind
    job: Any
    import_result: Any | None = None


def _job_status(job: Any) -> str:
    return str(getattr(job, "status", "") or "")


def _job_imported(job: Any) -> bool:
    return _job_status(job) == _IMPORTED_STATUS or getattr(job, "imported_at", None) is not None


class ProviderBatchImportWorker(QObject):
    """1 ジョブの refresh→(必要なら)fetch→import を順に実行する worker (#1158)。"""

    succeeded = Signal(int, object)  # (job_id, ProviderBatchCollectOutcome)
    failed = Signal(int, object)  # (job_id, 例外)
    finished = Signal()

    def __init__(self, workflow_service: Any, job_id: int) -> None:
        super().__init__()
        self._workflow_service = workflow_service
        self._job_id = job_id

    @Slot()
    def run(self) -> None:
        """refresh→fetch→import を実行し、成果を ``succeeded`` で通知する。

        完了カードの「結果を取得」も進行中カードの「状態を確認」も同じ経路
        (refresh → completed なら fetch + import)。worker thread 境界なので全例外を
        捕捉して ``failed`` へ marshalする (ADR 0044)。想定内の ``ProviderBatchError``
        も含め、判別は GUI 側 slot が行う。
        """
        job_id = self._job_id
        try:
            outcome = self._collect(job_id)
            self.succeeded.emit(job_id, outcome)
        except Exception as e:
            # worker thread 境界では全例外を捕捉し GUI へ marshal する (ADR 0044)。
            self.failed.emit(job_id, e)
        finally:
            self.finished.emit()

    def _collect(self, job_id: int) -> ProviderBatchCollectOutcome:
        job = self._workflow_service.refresh(job_id)
        if _job_imported(job):
            return ProviderBatchCollectOutcome("imported", job)
        if _job_status(job) == _COMPLETED_STATUS:
            fetch_result = self._workflow_service.fetch_results(job_id)
            import_result = self._workflow_service.import_results(job_id, fetch_result)
            return ProviderBatchCollectOutcome("collected", job, import_result)
        return ProviderBatchCollectOutcome("status", job)
