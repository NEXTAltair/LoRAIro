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
