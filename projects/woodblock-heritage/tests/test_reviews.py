from __future__ import annotations

from tests.conftest import work_body


def _approve_body(version: int = 1, claim_id: str = "c-title") -> dict:
    return {"expected_version": version, "reviewer": "local-reviewer",
            "reason": "核对合成页与证据后批准",
            "decisions": [{"claim_id": claim_id, "action": "approve",
                           "support_status": "supported"}]}


def test_approve_creates_immutable_version_and_event(client, work):
    response = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                           json=_approve_body(), headers={"Idempotency-Key": "rev-1"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["work"]["current_version"] == 2
    assert data["event"]["from_version"] == 1 and data["event"]["to_version"] == 2
    claim = next(item for item in data["work"]["payload"]["claims"] if item["id"] == "c-title")
    assert claim["review_status"] == "approved"
    assert claim["support_status"] == "supported"

    old = client.get(f"/api/v1/heritage/works/{work['work_id']}?version=1")
    assert old.status_code == 200
    assert next(item for item in old.json()["payload"]["claims"]
                if item["id"] == "c-title")["review_status"] == "unreviewed"


def test_review_idempotency_and_stale_version(client, work):
    first = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                        json=_approve_body(), headers={"Idempotency-Key": "same-review"})
    assert first.status_code == 200
    replay = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                         json=_approve_body(), headers={"Idempotency-Key": "same-review"})
    assert replay.status_code == 200
    assert replay.json()["work"]["current_version"] == 2
    assert len(replay.json()["work"]["events"]) == 1

    stale = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                        json=_approve_body(1), headers={"Idempotency-Key": "stale"})
    assert stale.status_code == 409
    assert stale.json()["code"] == "VERSION_CONFLICT"

    changed = _approve_body(2)
    changed["reason"] = "different payload"
    conflict = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                           json=changed, headers={"Idempotency-Key": "same-review"})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_approve_invalid_claim_is_rejected(client, source):
    body = work_body(source["source_id"])
    body["claims"][0]["predicate"] = "invented_predicate"
    work = client.post("/api/v1/heritage/works", json=body,
                       headers={"Idempotency-Key": "invalid-work"}).json()
    response = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                           json=_approve_body(), headers={"Idempotency-Key": "invalid-approve"})
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REVIEW"
    current = client.get(f"/api/v1/heritage/works/{work['work_id']}")
    assert current.json()["current_version"] == 1
    assert current.json()["events"] == []


def test_revise_returns_to_unreviewed(client, work):
    response = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                           json={"expected_version": 1, "reviewer": "local-reviewer",
                                 "reason": "修正谓词后重新审核",
                                 "decisions": [{"claim_id": "c-title", "action": "revise",
                                                "predicate": "source_category",
                                                "evidence_refs": ["r-title"]}]},
                           headers={"Idempotency-Key": "revise-1"})
    assert response.status_code == 200, response.text
    claim = next(item for item in response.json()["work"]["payload"]["claims"]
                 if item["id"] == "c-title")
    assert claim["predicate"] == "source_category"
    assert claim["review_status"] == "unreviewed"
    assert claim["support_status"] == "insufficient"


def test_revise_can_fix_missing_evidence(client, source):
    body = work_body(source["source_id"])
    body["claims"][0]["evidence_refs"] = []
    work = client.post("/api/v1/heritage/works", json=body,
                       headers={"Idempotency-Key": "fix-evidence"}).json()
    response = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                           json={"expected_version": 1, "reviewer": "local-reviewer",
                                 "reason": "补上原文证据",
                                 "decisions": [{"claim_id": "c-title", "action": "revise",
                                                "evidence_refs": ["r-title"]}]},
                           headers={"Idempotency-Key": "fix-evidence-review"})
    assert response.status_code == 200, response.text
    claim = next(item for item in response.json()["work"]["payload"]["claims"]
                 if item["id"] == "c-title")
    assert claim["validation_status"] == "valid"
    assert claim["review_status"] == "unreviewed"


def test_structural_issue_cannot_be_dismissed_by_reason(client, source):
    body = work_body(source["source_id"])
    body["claims"][0]["predicate"] = "invented_predicate"
    work = client.post("/api/v1/heritage/works", json=body,
                       headers={"Idempotency-Key": "issue-work"}).json()
    issue = next(item for item in work["payload"]["issues"] if item["code"] == "UNKNOWN_PREDICATE")
    response = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                           json={"expected_version": 1, "reviewer": "local-reviewer",
                                 "reason": "声称已解决",
                                 "decisions": [],
                                 "issue_resolutions": [{"issue_id": issue["id"],
                                                        "reason": "已人工确认"}]},
                           headers={"Idempotency-Key": "dismiss-issue"})
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_ISSUE_RESOLUTION"
