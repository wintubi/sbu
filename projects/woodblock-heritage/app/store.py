"""SQLite persistence with explicit write transactions.

One process-level lock serializes writers; SQLite itself allows concurrent
readers with WAL. All business writes use BEGIN IMMEDIATE so that idempotency,
version checks and audit rows commit atomically.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL UNIQUE,
    media_type TEXT NOT NULL,
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    content BLOB NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS works (
    id TEXT PRIMARY KEY,
    current_version INTEGER NOT NULL DEFAULT 1 CHECK (current_version > 0),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS work_versions (
    work_id TEXT NOT NULL REFERENCES works(id),
    version INTEGER NOT NULL CHECK (version > 0),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (work_id, version)
);
CREATE TABLE IF NOT EXISTS review_events (
    id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL REFERENCES works(id),
    from_version INTEGER NOT NULL,
    to_version INTEGER NOT NULL,
    reviewer TEXT NOT NULL,
    reason TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (work_id, to_version)
);
CREATE TABLE IF NOT EXISTS publications (
    id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (work_id, version),
    FOREIGN KEY (work_id, version) REFERENCES work_versions(work_id, version)
);
CREATE TABLE IF NOT EXISTS idempotency (
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (scope, key)
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Store:
    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.executescript(SCHEMA)
            row = self._conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if row is None:
                self._conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                                   (str(SCHEMA_VERSION),))
                self._conn.commit()
            elif int(row["value"]) != SCHEMA_VERSION:
                raise RuntimeError(f"unsupported database schema version {row['value']}")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    # -- sources ----------------------------------------------------------- #
    def get_source(self, source_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        return dict(row) if row else None

    def get_source_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM sources WHERE content_hash=?",
                                     (content_hash,)).fetchone()
        return dict(row) if row else None

    def insert_source(self, conn: sqlite3.Connection, *, source_id: str, content_hash: str,
                      media_type: str, width: int, height: int, content: bytes,
                      metadata: dict[str, Any], created_at: str) -> None:
        conn.execute(
            "INSERT INTO sources (id, content_hash, media_type, width, height, content, metadata_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (source_id, content_hash, media_type, width, height, content, dumps(metadata), created_at),
        )

    # -- works ------------------------------------------------------------- #
    def get_work(self, work_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM works WHERE id=?", (work_id,)).fetchone()
        return dict(row) if row else None

    def get_version(self, conn: sqlite3.Connection, work_id: str, version: int) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM work_versions WHERE work_id=? AND version=?",
                           (work_id, version)).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        payload["_created_at"] = row["created_at"]
        return payload

    def read_version(self, work_id: str, version: int) -> dict[str, Any] | None:
        """Read-only version access; no BEGIN IMMEDIATE, so it does not block writers."""
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json, created_at FROM work_versions WHERE work_id=? AND version=?",
                (work_id, version),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        payload["_created_at"] = row["created_at"]
        return payload

    def insert_work(self, conn: sqlite3.Connection, *, work_id: str, created_at: str) -> None:
        conn.execute("INSERT INTO works (id, current_version, created_at) VALUES (?,1,?)",
                     (work_id, created_at))

    def insert_version(self, conn: sqlite3.Connection, *, work_id: str, version: int,
                       payload: dict[str, Any], created_at: str) -> None:
        conn.execute(
            "INSERT INTO work_versions (work_id, version, payload_json, created_at) VALUES (?,?,?,?)",
            (work_id, version, dumps(payload), created_at),
        )

    def set_current_version(self, conn: sqlite3.Connection, work_id: str, version: int) -> None:
        conn.execute("UPDATE works SET current_version=? WHERE id=?", (version, work_id))

    def list_works(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM works ORDER BY created_at, id").fetchall()
        return [dict(row) for row in rows]

    # -- review events ----------------------------------------------------- #
    def insert_event(self, conn: sqlite3.Connection, *, event_id: str, work_id: str,
                     from_version: int, to_version: int, reviewer: str, reason: str,
                     payload: dict[str, Any], created_at: str) -> None:
        conn.execute(
            "INSERT INTO review_events (id, work_id, from_version, to_version, reviewer, reason, payload_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (event_id, work_id, from_version, to_version, reviewer, reason, dumps(payload), created_at),
        )

    def get_events(self, work_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM review_events WHERE work_id=? ORDER BY to_version", (work_id,)
            ).fetchall()
        events = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            events.append(item)
        return events

    # -- publications ------------------------------------------------------ #
    def get_publication(self, work_id: str, version: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM publications WHERE work_id=? AND version=?", (work_id, version)
            ).fetchone()
        return self._publication_row(row) if row else None

    def get_publication_by_id(self, publication_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM publications WHERE id=?",
                                     (publication_id,)).fetchone()
        return self._publication_row(row) if row else None

    @staticmethod
    def _publication_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json"))
        return item

    def insert_publication(self, conn: sqlite3.Connection, *, publication_id: str,
                           work_id: str, version: int, payload: dict[str, Any],
                           created_at: str) -> None:
        conn.execute(
            "INSERT INTO publications (id, work_id, version, payload_json, created_at) VALUES (?,?,?,?,?)",
            (publication_id, work_id, version, dumps(payload), created_at),
        )

    def list_publications(self, work_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM publications WHERE work_id=? ORDER BY version", (work_id,)
            ).fetchall()
        return [self._publication_row(row) for row in rows]

    def list_current_publications(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT p.* FROM publications p JOIN works w ON p.work_id=w.id "
                "WHERE p.version=w.current_version ORDER BY p.created_at, p.id"
            ).fetchall()
        return [self._publication_row(row) for row in rows]

    # -- idempotency ------------------------------------------------------- #
    def get_idempotency(self, conn: sqlite3.Connection, scope: str, key: str) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT request_hash, response_json FROM idempotency WHERE scope=? AND key=?",
            (scope, key),
        ).fetchone()
        return dict(row) if row else None

    def put_idempotency(self, conn: sqlite3.Connection, *, scope: str, key: str,
                        request_hash: str, response: dict[str, Any], created_at: str) -> None:
        conn.execute(
            "INSERT INTO idempotency (scope, key, request_hash, response_json, created_at) VALUES (?,?,?,?,?)",
            (scope, key, request_hash, dumps(response), created_at),
        )
