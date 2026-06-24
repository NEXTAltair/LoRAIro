"""Annotate の async batch dispatch を GUI スレッド外で実行する worker。

ADR 0076 §1 / ADR 0044: ``submit_images()`` は DB / filesystem / network I/O を
行うため、複数モデル射影の submit ループを GUI スレッドから外す。本 worker は
:func:`project_async_batch_dispatch` が生成した :class:`DispatchEntry` 群を
1 entry = 1 ``submit_images`` 呼び出し (= 1 provider batch job) でループ送信する。

呼び出し側 (MainWindow) は busy/再入ガードと QThread 配線を担う
(``ProviderBatchJobWidget._start_submit_worker`` と同形)。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from lorairo.services.dispatch_projection_service import DispatchEntry


class AsyncBatchDispatchWorker(QObject):
    """射影 entries を provider batch job として順次 submit する worker。"""

    succeeded = Signal(list)  # list[int]: 生成された job_id
    failed = Signal(object, list)  # (例外, 失敗前に送信済みの job_id list)
    finished = Signal()

    def __init__(self, workflow_service: Any, entries: Sequence[DispatchEntry]) -> None:
        super().__init__()
        self._workflow_service = workflow_service
        self._entries = tuple(entries)

    @Slot()
    def run(self) -> None:
        """全 entry を submit し、生成 job_id を ``succeeded`` で通知する。

        いずれかの entry で例外が出た場合は、それまでに送信済みの job_id を添えて
        ``failed`` で送出する (worker thread 境界なので全例外を marshalする、ADR 0044)。
        部分送信済み job_id を呼び出し側へ渡すことで、再送信による重複ジョブを防ぐ。
        """
        job_ids: list[int] = []
        try:
            for entry in self._entries:
                job_id = self._workflow_service.submit_images(
                    provider=entry.provider,
                    endpoint=entry.endpoint,
                    litellm_model_id=entry.litellm_model_id,
                    prompt_profile=entry.prompt_profile,
                    image_ids=list(entry.image_ids),
                    model_id=entry.model_id,
                    description=entry.description,
                    task_type=entry.task_type,
                    image_paths=dict(entry.image_paths) if entry.image_paths else None,
                )
                job_ids.append(int(job_id))
            self.succeeded.emit(job_ids)
        except Exception as e:
            # worker thread 境界では全例外を捕捉し GUI へ marshal する (ADR 0044)。
            # 部分送信済みの job_ids を添えて重複送信を防ぐ。
            self.failed.emit(e, job_ids)
        finally:
            self.finished.emit()
