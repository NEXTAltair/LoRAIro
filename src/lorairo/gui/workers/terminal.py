"""Worker terminal event types."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class WorkerOutcome(Enum):
    """Authoritative worker lifecycle outcome observed by WorkerManager."""

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
    REFINEMENT_REPLACED = "refinement_replaced"
    SHUTDOWN = "shutdown"
    TIMEOUT_FALLBACK = "timeout_fallback"


@dataclass(frozen=True)
class WorkerTerminalEvent:
    """Single worker fact event emitted once per worker observation."""

    worker_id: str
    worker_type: str
    outcome: WorkerOutcome
    result: Any | None = None
    error: str | None = None
    cancel_reason: CancelReason | None = None
