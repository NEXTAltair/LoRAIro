# src/lorairo/gui/workers/__init__.py
"""
GUI統合型ワーカーシステム

PySide6標準機能を活用したシンプルなワーカー実装。
QRunnable + QThreadPool + QProgressDialog による効率的な非同期処理を提供。
"""

from .base import (
    CancellationController,
    LoRAIroWorkerBase,
    ProgressReporter,
    WorkerProgress,
    WorkerStatus,
)
from .modern_progress_manager import (
    ModernProgressManager,
    create_worker_id,
)

__all__ = [
    "CancellationController",
    "LoRAIroWorkerBase",
    "ModernProgressManager",
    "ProgressReporter",
    "WorkerProgress",
    "WorkerStatus",
    "create_worker_id",
]
