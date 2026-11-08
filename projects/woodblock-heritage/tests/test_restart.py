from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from app.images import synthetic_png
from app.main import create_app
from tests.conftest import work_body


def test_committed_review_survives_restart(tmp_path):
    db_path = str(tmp_path / "restart.sqlite3")
    app = create_app(db_path=db_path)
    with TestClient(app) as client:
        source = client.post("/api/v1/heritage/sources", json={
            "filename": "restart.png", "source_note": "synthetic restart",
            "access_policy": "synthetic-only",
            "image_base64": base64.b64encode(synthetic_png()).decode("ascii"),
        }).json()
        work = client.post("/api/v1/heritage/works", json=work_body(source["source_id"]),
                           headers={"Idempotency-Key": "restart-work"}).json()
        review = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                             json={"expected_version": 1, "reviewer": "local-reviewer",
                                   "reason": "restart test",
                                   "decisions": [{"claim_id": "c-title", "action": "approve",
                                                  "support_status": "supported"}]},
                             headers={"Idempotency-Key": "restart-review"})
        assert review.status_code == 200
        work_id = work["work_id"]
        source_id = source["source_id"]

    with TestClient(create_app(db_path=db_path)) as client:
        current = client.get(f"/api/v1/heritage/works/{work_id}")
        assert current.status_code == 200
        assert current.json()["current_version"] == 2
        assert len(current.json()["events"]) == 1
        image = client.get(f"/api/v1/heritage/sources/{source_id}/image")
        assert image.status_code == 200
        assert image.content == synthetic_png()
