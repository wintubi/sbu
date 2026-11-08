from __future__ import annotations

import logging

from tests.conftest import work_body


def test_request_id_and_access_log_without_body(client, caplog):
    caplog.set_level(logging.INFO, logger="heritage.access")
    response = client.get("/health/live")
    assert response.status_code == 200
    request_id = response.headers.get("x-request-id")
    assert request_id and request_id.startswith("req_")
    messages = [record.getMessage() for record in caplog.records
                if record.name == "heritage.access"]
    assert any(request_id in message and "/health/live" in message for message in messages)
    assert all("image_base64" not in message for message in messages)


def test_non_local_host_is_rejected(client):
    response = client.get("/health/live", headers={"host": "evil.example"})
    assert response.status_code == 403
    assert response.json()["code"] == "HOST_NOT_ALLOWED"


def test_works_and_knowledge_pagination(client, source, work):
    second = client.post("/api/v1/heritage/works", json=work_body(source["source_id"]),
                         headers={"Idempotency-Key": "pagination-second"})
    assert second.status_code == 201

    page = client.get("/api/v1/heritage/works?limit=1&offset=0").json()
    assert page["count"] == 1
    assert page["total"] == 2
    assert page["has_more"] is True
    next_page = client.get("/api/v1/heritage/works?limit=1&offset=1").json()
    assert next_page["count"] == 1
    assert next_page["has_more"] is False

    reviewed = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                           json={"expected_version": 1, "reviewer": "r",
                                 "reason": "pagination publish",
                                 "decisions": [
                                     {"claim_id": "c-title", "action": "approve",
                                      "support_status": "supported"},
                                     {"claim_id": "c-category", "action": "approve",
                                      "support_status": "supported"},
                                 ]},
                           headers={"Idempotency-Key": "pagination-review"})
    assert reviewed.status_code == 200
    published = client.post("/api/v1/heritage/publications",
                            json={"work_id": work["work_id"], "expected_version": 2},
                            headers={"Idempotency-Key": "pagination-publish"})
    assert published.status_code == 201
    knowledge = client.get("/api/v1/heritage/knowledge?limit=1").json()
    assert knowledge["count"] == 1
    assert knowledge["total"] == 1
    assert knowledge["has_more"] is False

    invalid = client.get("/api/v1/heritage/works?limit=0")
    assert invalid.status_code == 422
