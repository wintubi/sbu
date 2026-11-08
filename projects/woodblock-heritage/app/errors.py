"""Uniform API errors. Messages are data for the page, never executable instructions."""
from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        cause: str = "",
        fix: str = "",
        retryable: bool = False,
        field_errors: list[dict[str, str]] | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.status = status
        self.code = code
        self.message = message
        self.cause = cause
        self.fix = fix
        self.retryable = retryable
        self.field_errors = field_errors or []
        self.details = details or {}

    def body(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "cause": self.cause,
            "fix": self.fix,
            "retryable": self.retryable,
        }
        if self.field_errors:
            payload["field_errors"] = self.field_errors
        if self.details:
            payload["details"] = self.details
        return payload
