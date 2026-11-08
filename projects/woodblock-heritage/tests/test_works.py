from __future__ import annotations

import copy

import json

from tests.conftest import work_body


def test_work_import_resets_client_management_state(client, source):
    body = work_body(source["source_id"])
    body["claims"][0].update({"support_status": "supported", "review_status": "approved",
                              "validation_status": "valid"})
    response = client.post("/api/v1/heritage/works", json=body,
                           headers={"Idempotency-Key": "reset-1"})
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["version"] == 1
    assert data["payload"]["import_version"] == 1
    assert "raw_import" in data["payload"]
    claim = data["payload"]["claims"][0]
    assert claim["support_status"] == "insufficient"
    assert claim["review_status"] == "unreviewed"


def test_work_idempotency_replay_and_conflict(client, source):
    body = work_body(source["source_id"])
    first = client.post("/api/v1/heritage/works", json=body,
                        headers={"Idempotency-Key": "same-key"})
    assert first.status_code == 201
    replay = client.post("/api/v1/heritage/works", json=body,
                         headers={"Idempotency-Key": "same-key"})
    assert replay.status_code == 200
    assert replay.json()["work_id"] == first.json()["work_id"]

    changed = copy.deepcopy(body)
    changed["claims"][0]["object"]["value"] = "另一个值"
    conflict = client.post("/api/v1/heritage/works", json=changed,
                           headers={"Idempotency-Key": "same-key"})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_idempotency_hash_ignores_json_key_order_and_whitespace(client, source):
    body = work_body(source["source_id"])
    first_raw = json.dumps(body, ensure_ascii=False)
    second_raw = json.dumps(body, ensure_ascii=False, sort_keys=True, indent=1)
    first = client.post("/api/v1/heritage/works", content=first_raw,
                        headers={"Content-Type": "application/json",
                                 "Idempotency-Key": "canonical-1"})
    assert first.status_code == 201, first.text
    replay = client.post("/api/v1/heritage/works", content=second_raw,
                         headers={"Content-Type": "application/json",
                                  "Idempotency-Key": "canonical-1"})
    assert replay.status_code == 200
    assert replay.json()["work_id"] == first.json()["work_id"]


def test_duplicate_region_and_claim_ids_are_rejected(client, source):
    body = work_body(source["source_id"])
    body["regions"].append(copy.deepcopy(body["regions"][0]))
    response = client.post("/api/v1/heritage/works", json=body,
                           headers={"Idempotency-Key": "dup-region"})
    assert response.status_code == 422
    assert response.json()["code"] == "DUPLICATE_ID"

    body = work_body(source["source_id"])
    body["claims"].append(copy.deepcopy(body["claims"][0]))
    response = client.post("/api/v1/heritage/works", json=body,
                           headers={"Idempotency-Key": "dup-claim"})
    assert response.status_code == 422


def test_unknown_predicate_is_persisted_invalid_not_rejected(client, source):
    body = work_body(source["source_id"])
    body["claims"][0]["predicate"] = "invented_predicate"
    response = client.post("/api/v1/heritage/works", json=body,
                           headers={"Idempotency-Key": "bad-predicate"})
    assert response.status_code == 201, response.text
    data = response.json()["payload"]
    claim = next(item for item in data["claims"] if item["id"] == "c-title")
    assert claim["validation_status"] == "invalid"
    assert any(issue["code"] == "UNKNOWN_PREDICATE" for issue in data["issues"])


def test_missing_evidence_is_invalid_but_retained(client, source):
    body = work_body(source["source_id"])
    body["claims"][0]["evidence_refs"] = []
    response = client.post("/api/v1/heritage/works", json=body,
                           headers={"Idempotency-Key": "no-evidence"})
    assert response.status_code == 201
    claim = next(item for item in response.json()["payload"]["claims"] if item["id"] == "c-title")
    assert claim["validation_status"] == "invalid"
    assert claim["evidence_refs"] == []


def test_entity_object_is_rejected(client, source):
    body = work_body(source["source_id"])
    body["claims"][0]["object"] = {"kind": "entity", "id": "person-1"}
    response = client.post("/api/v1/heritage/works", json=body,
                           headers={"Idempotency-Key": "entity"})
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_OBJECT"


def test_pixel_coordinates_are_normalized(client, source):
    body = work_body(source["source_id"])
    body["regions"][1]["coordinate_system"] = "pixels"
    body["regions"][1]["bbox"] = [0, 0, 32, 48]
    response = client.post("/api/v1/heritage/works", json=body,
                           headers={"Idempotency-Key": "pixels"})
    assert response.status_code == 201, response.text
    region = next(item for item in response.json()["payload"]["regions"] if item["id"] == "r-image")
    assert region["bbox"] == [0.0, 0.0, 0.5, 0.5]
    assert region["input_bbox"] == [0, 0, 32, 48]
    assert region["input_coordinate_system"] == "pixels"


def test_per_work_limits_are_rejected_before_write(client, source):
    body = work_body(source["source_id"])
    body["claims"] = [
        {"id": f"c-{index}", "predicate": "source_title",
         "object": {"kind": "literal", "value": f"标题 {index}"},
         "evidence_refs": ["r-title"]}
        for index in range(201)
    ]
    response = client.post("/api/v1/heritage/works", json=body,
                           headers={"Idempotency-Key": "too-many-claims"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_unknown_schema_and_source_are_rejected(client, source):
    body = work_body("missing-source")
    response = client.post("/api/v1/heritage/works", json=body,
                           headers={"Idempotency-Key": "missing-source"})
    assert response.status_code == 422
    assert response.json()["code"] == "UNKNOWN_SOURCE"

    body = work_body(source["source_id"])
    body["schema_version"] = "other-v9"
    response = client.post("/api/v1/heritage/works", json=body,
                           headers={"Idempotency-Key": "bad-schema"})
    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_SCHEMA"

    response = client.post("/api/v1/heritage/works", json=work_body(source["source_id"]))
    assert response.status_code == 422
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"
