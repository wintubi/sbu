from __future__ import annotations

from tests.conftest import work_body


def _approve_both(version: int = 1) -> dict:
    return {"expected_version": version, "reviewer": "local-reviewer",
            "reason": "逐条核对证据后批准",
            "decisions": [
                {"claim_id": "c-title", "action": "approve", "support_status": "supported"},
                {"claim_id": "c-category", "action": "approve", "support_status": "supported"},
            ]}


def test_publication_is_blocked_until_reviewed(client, work):
    response = client.post("/api/v1/heritage/publications",
                           json={"work_id": work["work_id"], "expected_version": 1},
                           headers={"Idempotency-Key": "publish-too-early"})
    assert response.status_code == 409
    assert response.json()["code"] == "PUBLICATION_BLOCKED"
    assert client.get("/api/v1/heritage/knowledge").json()["count"] == 0


def test_publish_is_unique_current_and_historical(client, work):
    review = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                         json=_approve_both(), headers={"Idempotency-Key": "approve-both"})
    assert review.status_code == 200, review.text
    assert review.json()["work"]["current_version"] == 2

    first = client.post("/api/v1/heritage/publications",
                        json={"work_id": work["work_id"], "expected_version": 2},
                        headers={"Idempotency-Key": "pub-1"})
    assert first.status_code == 201, first.text
    publication = first.json()
    assert len(publication["claims"]) == 2
    assert publication["historical"] is False

    repeat = client.post("/api/v1/heritage/publications",
                         json={"work_id": work["work_id"], "expected_version": 2},
                         headers={"Idempotency-Key": "pub-2"})
    assert repeat.status_code == 200
    assert repeat.json()["publication_id"] == publication["publication_id"]

    knowledge = client.get("/api/v1/heritage/knowledge").json()
    assert knowledge["count"] == 1
    assert knowledge["items"][0]["publication_id"] == publication["publication_id"]

    # Advance the reviewed version; the old snapshot must stop being current.
    advance = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                          json={"expected_version": 2, "reviewer": "local-reviewer",
                                "reason": "重新裁决第二项",
                                "decisions": [{"claim_id": "c-category", "action": "reject"}]},
                          headers={"Idempotency-Key": "advance"})
    assert advance.status_code == 200
    assert client.get("/api/v1/heritage/knowledge").json()["count"] == 0

    old = client.get(f"/api/v1/heritage/publications/{publication['publication_id']}")
    assert old.status_code == 200
    assert old.json()["historical"] is True
    assert old.json()["current_version"] == 3

    new_pub = client.post("/api/v1/heritage/publications",
                          json={"work_id": work["work_id"], "expected_version": 3},
                          headers={"Idempotency-Key": "pub-3"})
    assert new_pub.status_code == 201
    assert len(new_pub.json()["claims"]) == 1
    assert client.get("/api/v1/heritage/publications/" + publication["publication_id"]).json()[
        "historical"] is True


def test_rejected_invalid_claim_does_not_block_good_claim(client, source):
    body = work_body(source["source_id"])
    body["claims"].append({"id": "c-bad", "predicate": "invented_predicate",
                           "object": {"kind": "literal", "value": "不可靠"},
                           "evidence_refs": ["r-title"]})
    work = client.post("/api/v1/heritage/works", json=body,
                       headers={"Idempotency-Key": "with-bad"}).json()
    review = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                         json={"expected_version": 1, "reviewer": "local-reviewer",
                               "reason": "批准可靠项，驳回不可靠项",
                               "decisions": [
                                   {"claim_id": "c-title", "action": "approve",
                                    "support_status": "supported"},
                                   {"claim_id": "c-bad", "action": "reject"},
                                   {"claim_id": "c-category", "action": "reject"},
                               ]},
                         headers={"Idempotency-Key": "review-with-bad"})
    assert review.status_code == 200, review.text
    bad = next(item for item in review.json()["work"]["payload"]["claims"]
               if item["id"] == "c-bad")
    assert bad["review_status"] == "rejected"
    publication = client.post("/api/v1/heritage/publications",
                              json={"work_id": work["work_id"], "expected_version": 2},
                              headers={"Idempotency-Key": "publish-good"})
    assert publication.status_code == 201, publication.text
    ids = {claim["id"] for claim in publication.json()["claims"]}
    assert ids == {"c-title"}


def test_publication_idempotency_conflict(client, work):
    client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                json=_approve_both(), headers={"Idempotency-Key": "prep"})
    first = client.post("/api/v1/heritage/publications",
                        json={"work_id": work["work_id"], "expected_version": 2},
                        headers={"Idempotency-Key": "same-pub"})
    assert first.status_code == 201
    conflict = client.post("/api/v1/heritage/publications",
                           json={"work_id": work["work_id"], "expected_version": 3},
                           headers={"Idempotency-Key": "same-pub"})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
