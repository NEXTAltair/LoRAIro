"""Worker terminal event types."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class WorkerOutcome(Enum):
    """Authoritative terminal outcome for a worker."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    CANCEL_TIMEOUT = "cancel_timeout"
    TERMINATED = "terminated"
    UNRESPONSIVE = "unresponsive"


class CancelReason(Enum):
    """Reason a worker cancellation was requested."""

    USER_REQUESTED = "user_requested"
    PIPELINE_CANCEL = "pipeline_cancel"
    SEARCH_REPLACED = "search_replaced"
    THUMBNAIL_REPLACED = "thumbnail_replaced"
    PREFETCH_REPLACED = "prefetch_replaced"
    PROGRESS_DIALOG = "progress_dialog"
    SHUTDOWN = "shutdown"
    TIMEOUT_FALLBACK = "timeout_fallback"


@dataclass(frozen=True)
class WorkerTerminalEvent:
    """Single terminal event emitted once per worker."""

    worker_id: str
    worker_type: str
    outcome: WorkerOutcome
    result: Any | None = None
    error: str | None = None
    cancel_reason: CancelReason | None = None
