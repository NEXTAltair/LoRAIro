"""Operation lifecycle events derived from worker terminal facts."""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from lorairo.gui.workers.terminal import CancelReason, WorkerTerminalEvent


class OperationType(Enum):
    """User operation categories managed by WorkerService."""

    BATCH_REGISTRATION = "batch_registration"
    BATCH_IMPORT = "batch_import"
    ANNOTATION = "annotation"
    MODEL_INSTALL = "model_install"  # Issue #754: JOB_TYPE_MODEL_INSTALL (ADR 0066 §5)
    SEARCH = "search"
    THUMBNAIL = "thumbnail"
    UNKNOWN = "unknown"


class OperationOutcome(Enum):
    """Operation lifecycle outcome visible to pipeline/UI services."""

    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    SUPERSEDED = "superseded"
    TERMINATED = "terminated"
    UNRESPONSIVE = "unresponsive"


@dataclass(frozen=True)
class OperationContext:
    """Current/stale correlation data for one worker-backed operation."""

    operation_id: str
    operation_type: OperationType
    worker_id: str
    request_id: str | None = None
    generation: int | None = None


@dataclass(frozen=True)
class WorkerOperationEvent:
    """Operation event emitted by WorkerService after current/stale resolution."""

    operation_id: str
    operation_type: OperationType
    worker_id: str
    outcome: OperationOutcome
    is_current: bool
    request_id: str | None = None
    generation: int | None = None
    result: Any | None = None
    error: str | None = None
    cancel_reason: CancelReason | None = None
    worker_terminal: WorkerTerminalEvent | None = None
