"""LIVE进程内控制；不进入request/state，不改变replay工具计数语义。

时间只用可注入的单调时钟（默认``time.monotonic``），不读取UTC墙钟；
取消只通过短DB探针观察持久状态，探针不包HTTP、不持长事务。
"""
from __future__ import annotations

import time
from threading import Lock
from typing import Any, Callable

from .domain import ToolResult

DEFAULT_MAX_TOTAL_SECONDS = 90.0


class BudgetExhausted(RuntimeError):
    def __init__(self, reason: str = "call_limit"):
        self.reason = reason
        super().__init__("live HTTP attempt limit exhausted" if reason == "call_limit"
                         else "live runtime deadline exhausted")


class RunCancelled(RuntimeError):
    """持久状态已显示取消。

    取消不是执行错误，也不覆盖更早的主失败；最终保存会按已提交状态归一。
    """


class RuntimeControlError(RuntimeError):
    """取消探针不可用。

    只暴露固定分类与安全异常类型名，绝不携带原始异常串、Key或带query的URL。
    """

    def __init__(self, category: str, safe_exception_type: str | None = None):
        self.category = category
        self.safe_exception_type = safe_exception_type
        message = category if safe_exception_type is None else f"{category}: {safe_exception_type}"
        super().__init__(message)


class LiveRuntime:
    def __init__(self, budget: dict[str, Any], *,
                 clock: Callable[[], float] | None = None,
                 cancel_probe: Callable[[], str | None] | None = None,
                 on_evidence: Callable[[str, ToolResult], None] | None = None):
        self.budget = budget
        self._lock = Lock()
        self._clock = time.monotonic if clock is None else clock
        self._cancel_probe = cancel_probe
        self._on_evidence = on_evidence
        # factory之前取一次单调开始值；之后所有边界都由同一基准计算。
        self.started_at = self._clock()
        self.max_total_seconds = float(
            budget.get("max_total_seconds", DEFAULT_MAX_TOTAL_SECONDS))

    def elapsed(self) -> float:
        """单调时钟差；UTC跳变不影响，可为收尾后的最终采样。"""
        return max(self._clock() - self.started_at, 0.0)

    def _observe_cancel(self) -> None:
        probe = self._cancel_probe
        if probe is None:
            return
        try:
            status = probe()
        except Exception as exc:  # noqa: BLE001 - 分类为固定类别，不重放原始异常串
            raise RuntimeControlError("CANCEL_PROBE_READ_FAILED",
                                      type(exc).__name__) from None
        if status is None:
            raise RuntimeControlError("RUN_STATE_MISSING")
        if status == "cancelled":
            raise RunCancelled("live run was cancelled by persistent state")

    def check(self) -> None:
        """先观察取消，再判总deadline；顺序不可交换。"""
        self._observe_cancel()
        if self.elapsed() >= self.max_total_seconds:
            raise BudgetExhausted("deadline")

    def reserve_http(self, base_timeout: float) -> float:
        """准入一次HTTP并返回本操作的有限timeout。

        timeout取配置操作值与剩余时间的较小者：既不放大更短的配置，也不关闭超时。
        """
        self.check()
        elapsed = self.elapsed()  # 准入前即刻采样，避免用过期剩余时间
        with self._lock:
            if self.budget["tool_calls"] >= self.budget["max_tool_calls"]:
                raise BudgetExhausted("call_limit")
            remaining = self.max_total_seconds - elapsed
            if remaining <= 0:
                raise BudgetExhausted("deadline")
            timeout = min(float(base_timeout), remaining)
            if timeout <= 0:  # 配置本身非正时也不把非正timeout交给httpx
                raise BudgetExhausted("deadline")
            self.budget["tool_calls"] += 1
        return timeout

    def deliver_evidence(self, tool: str, result: ToolResult) -> None:
        self.check()
        if self._on_evidence is not None:
            self._on_evidence(tool, result)
