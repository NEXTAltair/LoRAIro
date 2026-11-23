"""DB エラー判定ユーティリティ (Qt-free / 重依存なし)。

SQLite の書き込みロック競合 (``database is locked`` / ``database is busy``) を、
SQLAlchemy / sqlite3 のどちらの層から送出されても検出する。CLI のエラー分類
(:mod:`lorairo.cli._errors`) と GUI ワーカー (:mod:`lorairo.gui.workers.base`) の
両方から共有するため、ここでは ``sqlalchemy`` 等を import せず例外の型名・メッセージ
だけで判定する (Issue #767)。

SQLite は WAL + ``busy_timeout`` を設定しても、待機時間内に他プロセスが書き込み
ロックを解放しなければ ``database is locked`` を送出する。GUI を開いたまま CLI で
書き込むといった同時利用ではこの一時的競合が起こり得るため、内部 DB エラーとは
区別して「再試行可能な競合」として扱えるようにする。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

# タグ DB 境界の縮退処理で SQL 中断を再送出するか (#1621)。既定は従来どおり縮退する。
# 画像登録だけが opt-in する。アノテーション保存はキャンセル後も同じスレッドで部分結果を
# 保存する (ADR 0109) ため、中断で保存を失敗させてはいけない。
_propagate_sqlite_interrupts: ContextVar[bool] = ContextVar("propagate_sqlite_interrupts", default=False)

# SQLite ロック競合を示すメッセージ断片 (sqlite3 / SQLAlchemy 共通)。
_LOCK_MESSAGE_FRAGMENTS = ("database is locked", "database is busy")


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    """``__cause__`` / ``__context__`` を遡って例外チェーンを列挙する。

    SQLAlchemy は sqlite3 の ``OperationalError`` を ``raise ... from orig`` で
    包むため、真因を辿らないと wrap された層でロックを見逃す。
    """
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def is_sqlite_lock_error(exc: BaseException) -> bool:
    """例外 (または cause chain) が SQLite の書き込みロック競合かを判定する。

    Args:
        exc: 判定対象の例外。

    Returns:
        ``database is locked`` / ``database is busy`` を示す ``OperationalError`` が
        チェーン上に存在すれば ``True``。
    """
    for item in _iter_exception_chain(exc):
        if type(item).__name__ != "OperationalError":
            continue
        message = str(item).lower()
        if any(fragment in message for fragment in _LOCK_MESSAGE_FRAGMENTS):
            return True
    return False


def is_sqlite_disk_io_error(exc: BaseException) -> bool:
    """例外 (または cause chain) が SQLite の ``disk I/O error`` かを判定する。

    WAL の ``-shm`` 共有メモリは OS 境界 (Windows GUI × コンテナ CLI の 9p 越し等) では
    mmap 共有できず、読み取りでも ``disk I/O error`` になる (Issue #1169)。CLI はこの
    判定で「実行環境を揃える」案内を出す (Issue #1175)。

    Args:
        exc: 判定対象の例外。

    Returns:
        ``disk I/O error`` を示す ``OperationalError`` がチェーン上に存在すれば ``True``。
    """
    for item in _iter_exception_chain(exc):
        if type(item).__name__ != "OperationalError":
            continue
        if "disk i/o error" in str(item).lower():
            return True
    return False


def is_sqlite_interrupt_error(exc: BaseException) -> bool:
    """例外 (または cause chain) が SQLite の実行中 SQL 中断 (``interrupted``) かを判定する。

    tag DB の接続には progress handler が入っており、worker スレッドへのキャンセル要求が
    あると実行中の SQL を ``OperationalError("interrupted")`` で打ち切る (#1206)。
    この例外はキャンセル要求でしか起きないため、縮退保存・retry・個別フォールバックへ
    進めず呼び出し元へ伝播させる判定に使う (#1621)。genai-tag-db-tools が ``ValueError``
    に包んで送出する場合も cause chain から検出する。

    Args:
        exc: 判定対象の例外。

    Returns:
        ``interrupted`` を示す ``OperationalError`` がチェーン上に存在すれば ``True``。
    """
    for item in _iter_exception_chain(exc):
        if type(item).__name__ != "OperationalError":
            continue
        if "interrupted" in str(item).lower():
            return True
    return False


@contextmanager
def propagate_sqlite_interrupts() -> Iterator[None]:
    """この文脈の間だけ、タグ DB 境界でキャンセル由来の SQL 中断を縮退させず伝播させる (#1621)。

    ``ContextVar`` なので、設定したスレッド (と、その中で作られた文脈) だけに効く。
    画像一括登録の worker が ``execute`` 全体を囲む。
    """
    token = _propagate_sqlite_interrupts.set(True)
    try:
        yield
    finally:
        _propagate_sqlite_interrupts.reset(token)


def should_propagate_sqlite_interrupt(exc: BaseException) -> bool:
    """縮退処理で ``exc`` を再送出すべきか (中断を伝播する文脈の SQL 中断のときだけ True)。

    Args:
        exc: タグ DB 境界で捕捉した例外。

    Returns:
        :func:`propagate_sqlite_interrupts` の文脈内で、``exc`` が SQL 中断なら ``True``。
    """
    return _propagate_sqlite_interrupts.get() and is_sqlite_interrupt_error(exc)
