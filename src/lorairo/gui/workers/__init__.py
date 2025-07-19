# src/lorairo/gui/workers/__init__.py
"""
GUI統合型ワーカーシステム

PySide6標準機能を活用したシンプルなワーカー実装。
QRunnable + QThreadPool + QProgressDialog による効率的な非同期処理を提供。
"""

from .base import SimpleWorkerBase, WorkerProgress, WorkerSignals

__all__ = [
    "SimpleWorkerBase",
    "WorkerProgress",
    "WorkerSignals",
]
