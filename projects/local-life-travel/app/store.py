"""SQLite persistence for replay runs.

Single connection guarded by an RLock. Every stage writes state back
immediately, so a new Store/Worker pointing at the same file can resume.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .domain import DEFAULT_BUDGET, TERMINAL_STATUSES, utc_now


def _normalize_cancelled(run: dict[str, Any]) -> None:
    """取消胜出时的单次快照归一：保留计数/elapsed/证据/原诊断。"""
    run["status"] = "cancelled"
    budget = run.setdefault("budget", {})
    budget["status"] = "cancelled"
    budget.pop("exhaustion_reason", None)
    state = run.setdefault("state", {})
    state["quality_status"] = "unverified"
    state["result"] = None


def new_state() -> dict[str, Any]:
    """The single source of truth for a run's in-flight data."""
    return {
        "completed_stages": [],
        "stage_log": [],
        "tool_results": [],
        "poi_records": [],
        "facts": [],
        "legs": [],
        "leg_durations": {},
        "hours": {},
        "issues": [],
        "changes": [],
        "candidates_for_input": [],
        "order": [],
        "poi_by_key": {},
        "quality_status": "unverified",
        "degraded": False,
        "executed_stages": 0,
        "result": None,
    }


class Store:
    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    parent_run_id TEXT,
                    request_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_stage TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    versions TEXT NOT NULL,
                    budget TEXT NOT NULL,
                    request TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    idempotency_key TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS idempotency (
                    key TEXT PRIMARY KEY,
                    request_hash TEXT NOT NULL,
                    run_id TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
                CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id);
                """
            )
            self._conn.commit()

    @staticmethod
    def _dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _loads(value: str | None, default: Any) -> Any:
        if value is None:
            return default
        return json.loads(value)

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "run_id": row["run_id"],
            "request_id": row["request_id"],
            "parent_run_id": row["parent_run_id"],
            "request_hash": row["request_hash"],
            "status": row["status"],
            "current_stage": row["current_stage"],
            "revision": row["revision"],
            "versions": Store._loads(row["versions"], []),
            "budget": Store._loads(row["budget"], dict(DEFAULT_BUDGET)),
            "request": Store._loads(row["request"], {}),
            "state": Store._loads(row["state"], new_state()),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "mode": row["mode"],
            "scenario_id": row["scenario_id"],
            "idempotency_key": row["idempotency_key"],
        }

    def _insert_run_locked(self, run: dict[str, Any]) -> None:
        self._conn.execute(
            """INSERT INTO runs
               (run_id, request_id, parent_run_id, request_hash, status,
                current_stage, revision, versions, budget, request, state,
                created_at, updated_at, mode, scenario_id, idempotency_key)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run["run_id"], run["request_id"], run.get("parent_run_id"),
                run["request_hash"], run["status"], run["current_stage"],
                run["revision"], self._dumps(run["versions"]),
                self._dumps(run["budget"]), self._dumps(run["request"]),
                self._dumps(run["state"]), run["created_at"], run["updated_at"],
                run["mode"], run["scenario_id"], run.get("idempotency_key"),
            ),
        )

    def _intake_event_locked(self, run_id: str, reason: str) -> None:
        self._conn.execute(
            "INSERT INTO events (run_id, stage, action, reason, created_at) VALUES (?,?,?,?,?)",
            (run_id, "intake", "RUN_CREATED", reason, utc_now()),
        )

    def create_run(self, run: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._insert_run_locked(run)
            self._intake_event_locked(run["run_id"], "回放运行创建")
            self._conn.commit()
        return run

    def create_run_atomic(self, run: dict[str, Any], key: str,
                          request_hash: str) -> tuple[str, Any]:
        """Insert run + idempotency row + intake event in ONE transaction.

        BEGIN IMMEDIATE serialises concurrent submitters of the same key, so
        two simultaneous requests can never both create a run.
        Returns ("created", run) or ("existing", {request_hash, run_id}).
        """
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT request_hash, run_id FROM idempotency WHERE key=?", (key,)
                ).fetchone()
                if row:
                    self._conn.rollback()
                    return "existing", {"request_hash": row["request_hash"], "run_id": row["run_id"]}
                self._insert_run_locked(run)
                self._conn.execute(
                    "INSERT INTO idempotency (key, request_hash, run_id) VALUES (?,?,?)",
                    (key, request_hash, run["run_id"]),
                )
                self._intake_event_locked(run["run_id"], "回放运行创建（幂等事务）")
                self._conn.commit()
                return "created", run
            except Exception:
                self._conn.rollback()
                raise

    def cancel_run(self, run_id: str) -> str:
        """条件取消；LIVE在同一短事务内一致归一整个终态快照。

        Returns 'ok' | 'missing' | 'terminal'.
        """
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT * FROM runs WHERE run_id=?", (run_id,)
                ).fetchone()
                if row is None:
                    self._conn.rollback()
                    return "missing"
                run = self._row_to_run(row)
                if run["status"] in TERMINAL_STATUSES:
                    self._conn.rollback()
                    return "terminal"
                if run["mode"] == "live":
                    # 与状态同一事务写budget/state，禁止先写cancelled再修补混合终态。
                    _normalize_cancelled(run)
                    cur = self._conn.execute(
                        "UPDATE runs SET status=?, budget=?, state=?, updated_at=? "
                        "WHERE run_id=? AND status IN ('queued','running')",
                        (run["status"], self._dumps(run["budget"]),
                         self._dumps(run["state"]), utc_now(), run_id),
                    )
                else:
                    cur = self._conn.execute(
                        "UPDATE runs SET status='cancelled', updated_at=? "
                        "WHERE run_id=? AND status IN ('queued','running')",
                        (utc_now(), run_id),
                    )
                self._conn.commit()
                return "ok" if cur.rowcount else "terminal"
            except Exception:
                self._conn.rollback()
                raise

    def probe_run_status(self, run_id: str) -> str | None:
        """取消探针：单行短读，不开显式事务、不包HTTP。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT status FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
        return row["status"] if row else None

    def finalize_run(self, run: dict[str, Any]) -> dict[str, Any]:
        """LIVE最终提交：单次短事务重新判定取消并返回canonical快照。

        取消若已在并发中提交，则对包含实际计数/elapsed/证据的内存快照做同样归一，
        与状态一起一次写入；否则按内存快照写入。读取发生在同一事务内，
        GET/同键重放不可能看到cancelled与verified/ok混合的中间态。
        """
        run_id = run["run_id"]
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT status FROM runs WHERE run_id=?", (run_id,)
                ).fetchone()
                if row is None:
                    raise RuntimeError("RUN_ROW_MISSING")
                if row["status"] == "cancelled":
                    _normalize_cancelled(run)
                run["updated_at"] = utc_now()
                self._conn.execute(
                    """UPDATE runs SET
                         status=?, current_stage=?, revision=?, versions=?, budget=?,
                         request=?, state=?, updated_at=?, parent_run_id=?
                       WHERE run_id=?""",
                    (
                        run["status"], run["current_stage"], run["revision"],
                        self._dumps(run["versions"]), self._dumps(run["budget"]),
                        self._dumps(run["request"]), self._dumps(run["state"]),
                        run["updated_at"], run.get("parent_run_id"), run_id,
                    ),
                )
                persisted = self._conn.execute(
                    "SELECT * FROM runs WHERE run_id=?", (run_id,)
                ).fetchone()
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return self._row_to_run(persisted)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._row_to_run(row) if row else None

    def save_run(self, run: dict[str, Any]) -> None:
        """replay/worker保存；LIVE必须走 ``finalize_run`` 以避免混合终态。"""
        run["updated_at"] = utc_now()
        with self._lock:
            self._conn.execute(
                """UPDATE runs SET
                     status = CASE WHEN status='cancelled' AND ? != 'cancelled'
                                   THEN 'cancelled' ELSE ? END,
                     current_stage=?, revision=?, versions=?, budget=?, request=?, state=?,
                     updated_at=?, parent_run_id=?
                   WHERE run_id=?""",
                (
                    run["status"], run["status"], run["current_stage"], run["revision"],
                    self._dumps(run["versions"]), self._dumps(run["budget"]),
                    self._dumps(run["request"]), self._dumps(run["state"]),
                    run["updated_at"], run.get("parent_run_id"), run["run_id"],
                ),
            )
            self._conn.commit()

    def list_runnable(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM runs WHERE status IN ('queued','running') AND mode='replay' "
                "ORDER BY created_at, run_id"
            ).fetchall()
        return [self._row_to_run(r) for r in rows]

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM runs ORDER BY created_at, run_id").fetchall()
        return [self._row_to_run(r) for r in rows]

    def count_runs(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])

    def add_event(self, run_id: str, stage: str, action: str, reason: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (run_id, stage, action, reason, created_at) VALUES (?,?,?,?,?)",
                (run_id, stage, action, reason, utc_now()),
            )
            self._conn.commit()

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, stage, action, reason, created_at FROM events WHERE run_id=? ORDER BY id",
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_idempotency(self, key: str) -> dict[str, str] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT key, request_hash, run_id FROM idempotency WHERE key=?", (key,)
            ).fetchone()
        return dict(row) if row else None

    def set_idempotency(self, key: str, request_hash: str, run_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO idempotency (key, request_hash, run_id) VALUES (?,?,?)",
                (key, request_hash, run_id),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
