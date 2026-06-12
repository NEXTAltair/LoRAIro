# src/lorairo/gui/workers/__init__.py
"""
GUI統合型ワーカーシステム

PySide6標準機能を活用したシンプルなワーカー実装。
QObject + QThread による効率的な非同期処理を提供。
進捗はステータスバー通知 + Jobs タブ台帳 (ADR 0066) で表示する。
"""

from .base import (
    CancellationController,
    LoRAIroWorkerBase,
    ProgressReporter,
    WorkerProgress,
    WorkerStatus,
)

__all__ = [
    "CancellationController",
    "LoRAIroWorkerBase",
    "ProgressReporter",
    "WorkerProgress",
    "WorkerStatus",
]
