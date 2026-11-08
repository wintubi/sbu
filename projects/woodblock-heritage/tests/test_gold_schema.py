from __future__ import annotations

import json
from datetime import datetime, timezone

from app.gold import validate_file, validate_record


def base_record(**overrides):
    record = {
        "gold_id": "gold_000001",
        "work_ref": "work_demo",
        "source_manifest_sha256": "a" * 64,
        "schema_version": "heritage-review-v1",
        "claim_id": "c-title",
        "predicate": "source_title",
        "object": {"kind": "literal", "value": "合成门神示例"},
        "evidence_refs": ["r-title"],
        "support_status": "supported",
        "decision": "approve",
        "reviewer": "reviewer-1",
        "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "notes": "synthetic fixture",
    }
    record.update(overrides)
    return record


def test_valid_record_has_no_errors():
    assert validate_record(base_record()) == []


def test_approve_without_evidence_or_value_is_rejected():
    errors = validate_record(base_record(evidence_refs=[]))
    assert any("approve requires evidence_refs" in item for item in errors)
    errors = validate_record(base_record(object={"kind": "literal", "value": ""}))
    assert any("non-empty value" in item for item in errors)


def test_unknown_predicate_is_rejected():
    errors = validate_record(base_record(predicate="invented_predicate"))
    assert any("predicate" in item for item in errors)


def test_invalid_enum_and_schema_are_rejected():
    errors = validate_record(base_record(support_status="yes", decision="maybe",
                                         schema_version="v0"))
    assert any("support_status" in item for item in errors)
    assert any("decision" in item for item in errors)
    assert any("schema_version" in item for item in errors)


def test_file_rejects_duplicate_ids_and_bad_json(tmp_path):
    path = tmp_path / "gold.jsonl"
    path.write_text(
        json.dumps(base_record(), ensure_ascii=False) + "\n"
        + json.dumps(base_record(), ensure_ascii=False) + "\n"
        + "{not-json}\n",
        encoding="utf-8",
    )
    result = validate_file(path)
    assert result["ok"] is False
    assert result["count"] == 3
    assert any("duplicate gold_id" in error for row in result["errors"] for error in row["errors"])
    assert any("invalid JSON" in error for row in result["errors"] for error in row["errors"])


def test_reject_may_have_no_evidence_but_still_needs_a_record(tmp_path):
    path = tmp_path / "gold.jsonl"
    path.write_text(json.dumps(base_record(decision="reject", support_status="insufficient",
                                          evidence_refs=[], object={"kind": "literal", "value": None}),
                               ensure_ascii=False) + "\n", encoding="utf-8")
    assert validate_file(path)["ok"] is True
