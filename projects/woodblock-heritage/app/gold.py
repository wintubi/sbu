"""Structural validation for gold-standard JSONL.

This validates the annotation contract only. It does not decide whether a
claim is true, and it does not turn synthetic or unreviewed data into gold.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import PREDICATES

SCHEMA_VERSION = "heritage-review-v1"
SUPPORT = {"supported", "disputed", "insufficient"}
DECISIONS = {"approve", "reject", "revise"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED = (
    "gold_id", "work_ref", "source_manifest_sha256", "schema_version",
    "claim_id", "predicate", "object", "evidence_refs",
    "support_status", "decision", "reviewer", "reviewed_at", "notes",
)


def validate_record(record: Any, index: int = 0) -> list[str]:
    errors: list[str] = []
    prefix = f"record[{index}]"
    if not isinstance(record, dict):
        return [f"{prefix}: must be a JSON object"]
    missing = [key for key in REQUIRED if key not in record]
    if missing:
        errors.append(f"{prefix}: missing fields {missing}")
        return errors
    for key in ("gold_id", "work_ref", "claim_id", "predicate", "reviewer", "notes"):
        if not isinstance(record[key], str):
            errors.append(f"{prefix}.{key}: must be a string")
    for key in ("gold_id", "work_ref", "claim_id", "predicate", "reviewer"):
        if isinstance(record[key], str) and not record[key].strip():
            errors.append(f"{prefix}.{key}: must not be empty")
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{prefix}.schema_version: must be {SCHEMA_VERSION}")
    predicate = record.get("predicate")
    if isinstance(predicate, str) and predicate not in PREDICATES:
        errors.append(f"{prefix}.predicate: not in the frozen predicate set")
    digest = record.get("source_manifest_sha256")
    if not isinstance(digest, str) or not HEX64.match(digest):
        errors.append(f"{prefix}.source_manifest_sha256: must be 64 lowercase hex")
    obj = record.get("object")
    if not isinstance(obj, dict) or obj.get("kind") != "literal":
        errors.append(f"{prefix}.object: must be {{kind: literal, ...}}")
    else:
        value = obj.get("value")
        if value is not None and not isinstance(value, str):
            errors.append(f"{prefix}.object.value: must be string or null")
    refs = record.get("evidence_refs")
    if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref.strip() for ref in refs):
        errors.append(f"{prefix}.evidence_refs: must be a list of non-empty strings")
        refs = []
    support = record.get("support_status")
    if support not in SUPPORT:
        errors.append(f"{prefix}.support_status: must be one of {sorted(SUPPORT)}")
    decision = record.get("decision")
    if decision not in DECISIONS:
        errors.append(f"{prefix}.decision: must be one of {sorted(DECISIONS)}")
    reviewed_at = record.get("reviewed_at")
    if not isinstance(reviewed_at, str):
        errors.append(f"{prefix}.reviewed_at: must be RFC3339 with offset")
    else:
        try:
            parsed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("missing offset")
        except ValueError:
            errors.append(f"{prefix}.reviewed_at: must be RFC3339 with offset")
    value = (obj or {}).get("value") if isinstance(obj, dict) else None
    if decision == "approve":
        if support != "supported":
            errors.append(f"{prefix}: approve requires support_status=supported")
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{prefix}: approve requires a non-empty value")
        if not refs:
            errors.append(f"{prefix}: approve requires evidence_refs")
    return errors


def validate_file(path: str | Path) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    count = 0
    source = Path(path)
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return {"ok": False, "count": 0, "errors": [{"line": 0, "errors": [str(exc)]}]}
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        count += 1
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append({"line": line_number, "errors": [f"invalid JSON: {exc}"]})
            continue
        row_errors = validate_record(record, count - 1)
        if isinstance(record, dict):
            gold_id = record.get("gold_id")
            if isinstance(gold_id, str):
                if gold_id in seen:
                    row_errors.append(f"duplicate gold_id: {gold_id}")
                seen.add(gold_id)
        if row_errors:
            errors.append({"line": line_number, "errors": row_errors})
    return {"ok": not errors, "count": count, "unique_ids": len(seen), "errors": errors}
