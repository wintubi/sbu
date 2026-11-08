from __future__ import annotations


def test_publication_history_lists_current_and_historical(client, work):
    reviewed = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                           json={"expected_version": 1, "reviewer": "r",
                                 "reason": "history publish v2",
                                 "decisions": [
                                     {"claim_id": "c-title", "action": "approve",
                                      "support_status": "supported"},
                                     {"claim_id": "c-category", "action": "approve",
                                      "support_status": "supported"},
                                 ]},
                           headers={"Idempotency-Key": "history-review-1"})
    assert reviewed.status_code == 200
    first = client.post("/api/v1/heritage/publications",
                        json={"work_id": work["work_id"], "expected_version": 2},
                        headers={"Idempotency-Key": "history-publish-1"})
    assert first.status_code == 201

    advanced = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                           json={"expected_version": 2, "reviewer": "r",
                                 "reason": "history publish v3",
                                 "decisions": [{"claim_id": "c-category", "action": "reject"}]},
                           headers={"Idempotency-Key": "history-review-2"})
    assert advanced.status_code == 200
    second = client.post("/api/v1/heritage/publications",
                         json={"work_id": work["work_id"], "expected_version": 3},
                         headers={"Idempotency-Key": "history-publish-2"})
    assert second.status_code == 201

    history = client.get(f"/api/v1/heritage/works/{work['work_id']}/publications")
    assert history.status_code == 200
    data = history.json()
    assert data["count"] == 2
    assert [item["version"] for item in data["items"]] == [2, 3]
    assert data["items"][0]["historical"] is True
    assert data["items"][1]["historical"] is False
    assert data["items"][0]["publication_id"] == first.json()["publication_id"]
    assert data["items"][1]["publication_id"] == second.json()["publication_id"]


def test_publication_history_unknown_work_404(client):
    response = client.get("/api/v1/heritage/works/work_missing/publications")
    assert response.status_code == 404
    assert response.json()["code"] == "WORK_NOT_FOUND"
