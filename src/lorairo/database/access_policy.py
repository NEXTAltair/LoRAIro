"""Synchronous opt-in database access policy, shared by CLI and Python callers."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_READ_ONLY: ContextVar[bool] = ContextVar("lorairo_read_only", default=False)


def is_read_only() -> bool:
    return _READ_ONLY.get()


@contextmanager
def read_only_scope() -> Iterator[None]:
    """Require existing compatible databases; never prepare/migrate them implicitly."""
    token = _READ_ONLY.set(True)
    try:
        yield
    finally:
        _READ_ONLY.reset(token)
