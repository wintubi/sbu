"""Persistent single-process worker.

tick() advances exactly one stage of one queued/running run. A background
thread can be started for the live server; tests disable it and call drain()
explicitly so results are deterministic.

Unexpected exceptions are logged AND persisted as a terminal failure, so a
broken run cannot be retried forever by the polling loop.
"""
from __future__ import annotations

import logging
import threading
import time

from .domain import TERMINAL_STATUSES, make_issue
from .engine import advance
from .store import Store

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, store: Store, *, autostart: bool = True, interval: float = 0.05):
        self.store = store
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None
        if autostart:
            self.start()

    def tick(self) -> bool:
        runnable = self.store.list_runnable()
        if not runnable:
            return False
        run_id = runnable[0]["run_id"]
        try:
            advance(self.store, run_id)
            self.last_error = None
        except Exception as exc:  # noqa: BLE001 - must not silently spin
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("stage execution failed for run %s", run_id)
            current = self.store.get_run(run_id)
            if current and current["status"] not in TERMINAL_STATUSES:
                current["status"] = "failed"
                current["state"]["issues"].append(make_issue(
                    "STAGE_EXECUTION_ERROR", "blocker",
                    "阶段执行出现未预期异常，运行已终止且不再重试；详见服务端日志",
                ))
                self.store.save_run(current)
                self.store.add_event(run_id, current["current_stage"], "STAGE_ERROR",
                                     self.last_error)
        return True

    def drain(self, max_ticks: int = 1000) -> int:
        ticks = 0
        while ticks < max_ticks and self.tick():
            ticks += 1
        return ticks

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.tick():
                    self._stop.wait(self.interval)
            except Exception:  # defensive: tick() should contain its own errors
                logger.exception("worker tick failed")
                self._stop.wait(self.interval)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="replay-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    @property
    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())
