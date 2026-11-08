from __future__ import annotations

import base64

from app.images import synthetic_png
from tests.conftest import work_body


def test_source_policy_blocks_publication_even_when_review_ready(client):
    source = client.post("/api/v1/heritage/sources", json={
        "filename": "local-policy.png", "source_note": "local permission test",
        "access_policy": "local-unverified-no-publication",
        "image_base64": base64.b64encode(synthetic_png(70, 96)).decode("ascii"),
    })
    assert source.status_code == 201, source.text
    source_id = source.json()["source_id"]
    work = client.post("/api/v1/heritage/works", json=work_body(source_id),
                       headers={"Idempotency-Key": "policy-work"})
    assert work.status_code == 201, work.text
    work_id = work.json()["work_id"]
    reviewed = client.post(f"/api/v1/heritage/works/{work_id}/reviews",
                           json={"expected_version": 1, "reviewer": "r",
                                 "reason": "policy test",
                                 "decisions": [
                                     {"claim_id": "c-title", "action": "approve",
                                      "support_status": "supported"},
                                     {"claim_id": "c-category", "action": "approve",
                                      "support_status": "supported"},
                                 ]},
                           headers={"Idempotency-Key": "policy-review"})
    assert reviewed.status_code == 200, reviewed.text
    published = client.post("/api/v1/heritage/publications",
                            json={"work_id": work_id, "expected_version": 2},
                            headers={"Idempotency-Key": "policy-publish"})
    assert published.status_code == 409
    assert published.json()["code"] == "PUBLICATION_POLICY_BLOCKED"
    assert published.json()["details"]["restricted_sources"][0]["source_id"] == source_id
    assert client.get(f"/api/v1/heritage/works/{work_id}/publications").json()["count"] == 0
