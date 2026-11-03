"""Durable, opt-in annotation progress; uncertain sends are never automatically retried."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

STATES = ("pending", "in_flight", "completed", "failed", "skipped")
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_RESERVED_IDS = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{index}" for prefix in ("COM", "LPT") for index in range(1, 10)
}
_SECRET = re.compile(
    r"api.?key|secret|password|credential|access.?token|auth.?token|authorization|headers", re.I
)


def validate_run_id(run_id: str) -> None:
    if not _RUN_ID.fullmatch(run_id) or run_id.upper() in _RESERVED_IDS:
        raise ValueError(
            "Run ID must be 1-64 ASCII letters/digits, '_' or '-', starting with a letter/digit; "
            "reserved device names are not allowed"
        )


def _without_credentials(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _without_credentials(item)
            for key, item in value.items()
            if not _SECRET.search(str(key))
            and str(key).lower() not in {"key", "token"}
            and not str(key).lower().endswith(("_key", "_token"))
        }
    if isinstance(value, (list, tuple)):
        return [_without_credentials(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    raise ValueError("Unsupported annotation configuration value; cannot safely bind this run")


def configuration_digest(settings: Mapping[str, Any]) -> str:
    """Persist only a digest of settings; credential rotation does not invalidate progress."""
    encoded = json.dumps(_without_credentials(settings), sort_keys=True, ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def database_identity(database: Path) -> dict[str, Any]:
    database = database.resolve(strict=True)
    stat = database.stat()
    if not stat.st_ino:
        raise ValueError("Filesystem does not expose a stable project database identity")
    return {"path": str(database), "device": stat.st_dev, "inode": stat.st_ino}


def image_identity(record: Mapping[str, Any], path: Path | None) -> str:
    """Bind both DB identity and actual inference bytes, not mutable annotation rows."""
    identity = {key: record.get(key) for key in ("id", "uuid", "phash", "stored_image_path")}
    if not identity["uuid"] or not identity["phash"]:
        raise ValueError("Selected image has no stable UUID/pHash")
    if path is not None:
        path = path.resolve(strict=True)
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        identity.update(path=str(path), sha256=digest.hexdigest())
    return configuration_digest(identity)


class AnnotationRunLedger:
    """SQLite commits precede every send and follow confirmed per-image completion.

    A separate SQLite transaction holds the process lock without preventing progress
    commits. The OS releases that lock after crashes; persisted in_flight remains.
    """

    def __init__(self, project_path: Path, run_id: str) -> None:
        validate_run_id(run_id)
        self.run_id = run_id
        root = project_path.resolve(strict=True)
        directory = root / ".lorairo" / "annotation-runs"
        if not directory.resolve().is_relative_to(root):
            raise ValueError("Annotation run directory resolves outside this project")
        self.path = directory / f"{run_id}.sqlite3"
        self._connection: sqlite3.Connection | None = None

    @contextmanager
    def locked(self, *, resume: bool) -> Iterator[AnnotationRunLedger]:
        if resume and not self.path.is_file():
            raise ValueError(f"Annotation run '{self.run_id}' does not exist in this project")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(".lock.sqlite3")
        if self.path.is_symlink() or lock_path.is_symlink():
            raise ValueError("Annotation run files must not be symbolic links")
        lock = sqlite3.connect(lock_path, timeout=0)
        try:
            lock.execute("BEGIN EXCLUSIVE")
            if not resume:
                # Never truncate an existing run, even when it has no valid schema.
                with self.path.open("xb"):
                    pass
            self._connection = sqlite3.connect(self.path, timeout=0)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA synchronous=FULL")
            yield self
        finally:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            lock.close()

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("Annotation run must be locked")
        return self._connection

    def initialize(self, binding: dict[str, Any], images: list[dict[str, Any]]) -> None:
        with self.connection:
            self.connection.execute("CREATE TABLE run (version INTEGER NOT NULL, binding TEXT NOT NULL)")
            self.connection.execute(
                "CREATE TABLE images (image_id INTEGER PRIMARY KEY, identity TEXT NOT NULL, "
                "state TEXT NOT NULL CHECK (state IN ('pending','in_flight','completed','failed','skipped')), "
                "reason TEXT, saved INTEGER NOT NULL DEFAULT 0)"
            )
            self.connection.execute("INSERT INTO run VALUES (1, ?)", (json.dumps(binding, sort_keys=True),))
            self.connection.executemany(
                "INSERT INTO images (image_id, identity, state, reason) VALUES (?, ?, ?, ?)",
                [(row["image_id"], row["identity"], row["state"], row.get("reason")) for row in images],
            )

    def binding(self) -> dict[str, Any]:
        try:
            rows = self.connection.execute("SELECT version, binding FROM run").fetchall()
            if len(rows) != 1 or rows[0]["version"] != 1:
                raise ValueError("Unsupported or incomplete annotation run")
            binding = json.loads(rows[0]["binding"])
            if not isinstance(binding, dict):
                raise ValueError("Invalid annotation run binding")
            return binding
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise ValueError("Unreadable or incomplete annotation run; it cannot be resumed") from exc

    def images(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute("SELECT * FROM images ORDER BY image_id")]

    def transition(
        self, image_id: int, state: str, *, reason: str | None = None, saved: bool = False
    ) -> None:
        expected = "pending" if state == "in_flight" else "in_flight"
        if state not in STATES or state == "pending":
            raise ValueError("Invalid annotation run transition")
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE images SET state=?, reason=?, saved=? WHERE image_id=? AND state=?",
                (state, reason, int(saved), image_id, expected),
            )
            if cursor.rowcount != 1:
                raise ValueError("Annotation run state changed; refusing to repeat a sent image")
