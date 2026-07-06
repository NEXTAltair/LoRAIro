# src/lorairo/gui/workers/sql_abort.py
"""worker スレッドの実行中 SQL を協調キャンセルで中断するためのレジストリ (#1206)。

genai-tag-db-tools の ``set_query_abort_check`` は「クエリを実行しているスレッド上で」
呼ばれる判定関数を 1 つだけ受け取る。本モジュールはスレッド ident ->
:class:`CancellationController` のレジストリを持ち、worker スレッドが自分の
キャンセル状態を判定関数越しに公開できるようにする。

これにより ``LoRAIroWorkerBase.cancel()`` (キャンセルチェックポイント間でしか効かない)
が、tag DB の長時間クエリ実行中でも SQLite progress handler 経由でクエリを
``OperationalError`` (interrupted) として打ち切れる。
"""

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import CancellationController

_lock = threading.Lock()
_controllers_by_thread: dict[int, "CancellationController"] = {}


def register_current_thread(controller: "CancellationController") -> None:
    """現在のスレッドのキャンセル状態を SQL 中断判定に公開する。"""
    with _lock:
        _controllers_by_thread[threading.get_ident()] = controller


def unregister_current_thread() -> None:
    """現在のスレッドの登録を解除する (worker 終了時に必ず呼ぶ)。"""
    with _lock:
        _controllers_by_thread.pop(threading.get_ident(), None)


def current_thread_cancel_requested() -> bool:
    """現在のスレッドにキャンセル要求が出ているか (SQLite progress handler から呼ばれる)。

    genai-tag-db-tools の ``set_query_abort_check`` へ渡す判定関数。
    未登録スレッド (メインスレッドの同期クエリ等) では常に False。
    """
    controller = _controllers_by_thread.get(threading.get_ident())
    return controller is not None and controller.is_canceled()
