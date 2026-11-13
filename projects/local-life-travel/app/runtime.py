"""LIVE进程内控制；不进入request/state，不改变replay工具计数语义。"""
from __future__ import annotations

from threading import Lock
from typing import Any, Callable

from .domain import ToolResult


class BudgetExhausted(RuntimeError):
    def __init__(self, reason: str = "call_limit"):
        self.reason = reason
        super().__init__("live HTTP attempt limit exhausted" if reason == "call_limit"
                         else "live runtime deadline exhausted")


class LiveRuntime:
    def __init__(self, budget: dict[str, Any], *,
                 on_evidence: Callable[[str, ToolResult], None] | None = None):
        self.budget = budget
        self._lock = Lock()
        self._on_evidence = on_evidence

    def check(self) -> None:
        # Task 2接入单调deadline和持久取消探针；次数只在reserve消费。
        pass

    def reserve_http(self, base_timeout: float) -> float:
        self.check()
        with self._lock:
            if self.budget["tool_calls"] >= self.budget["max_tool_calls"]:
                raise BudgetExhausted()
            self.budget["tool_calls"] += 1
        return base_timeout

    def deliver_evidence(self, tool: str, result: ToolResult) -> None:
        self.check()
        if self._on_evidence is not None:
            self._on_evidence(tool, result)
