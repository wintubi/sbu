from __future__ import annotations

import sqlite3

import pytest

from app.store import Store
from tests.conftest import work_body


def test_owned_store_closes_with_app_lifespan(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(db_path=str(tmp_path / "close.sqlite3"))
    with TestClient(app):
        store = app.state.store
        assert store.get_work("missing") is None
    with pytest.raises(sqlite3.ProgrammingError):
        store.get_work("missing")


def test_review_failure_rolls_back_event_and_version(client, work, monkeypatch):
    store = client.app.state.store

    def boom(*args, **kwargs):
        raise RuntimeError("injected event failure")

    monkeypatch.setattr(store, "insert_event", boom)
    with pytest.raises(RuntimeError, match="injected"):
        client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                    json={"expected_version": 1, "reviewer": "local-reviewer",
                          "reason": "fault injection",
                          "decisions": [{"claim_id": "c-title", "action": "approve",
                                         "support_status": "supported"}]},
                    headers={"Idempotency-Key": "fault-review"})
    monkeypatch.undo()
    current = client.get(f"/api/v1/heritage/works/{work['work_id']}").json()
    assert current["current_version"] == 1
    assert current["events"] == []
    # The idempotency row must not survive a failed transaction either.
    with store.transaction() as conn:
        row = conn.execute(
            "SELECT 1 FROM idempotency WHERE scope=? AND key=?",
            (f"work:review:{work['work_id']}", "fault-review"),
        ).fetchone()
    assert row is None


def test_replay_after_later_update_returns_original_response(client, work):
    first = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                        json={"expected_version": 1, "reviewer": "r1", "reason": "first",
                              "decisions": [{"claim_id": "c-title", "action": "approve",
                                             "support_status": "supported"}]},
                        headers={"Idempotency-Key": "replay-a"})
    assert first.status_code == 200
    later = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                        json={"expected_version": 2, "reviewer": "r2", "reason": "later",
                              "decisions": [{"claim_id": "c-category", "action": "reject"}]},
                        headers={"Idempotency-Key": "replay-b"})
    assert later.status_code == 200
    assert later.json()["work"]["current_version"] == 3
    replay = client.post(f"/api/v1/heritage/works/{work['work_id']}/reviews",
                         json={"expected_version": 1, "reviewer": "r1", "reason": "first",
                               "decisions": [{"claim_id": "c-title", "action": "approve",
                                              "support_status": "supported"}]},
                         headers={"Idempotency-Key": "replay-a"})
    assert replay.status_code == 200
    assert replay.json()["work"]["current_version"] == 2
    assert client.get(f"/api/v1/heritage/works/{work['work_id']}").json()["current_version"] == 3


def test_health_and_unknown_db_version(tmp_path, client):
    assert client.get("/health/live").status_code == 200
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"

    db = tmp_path / "versioned.sqlite3"
    store = Store(str(db))
    store.close()
    conn = sqlite3.connect(db)
    conn.execute("UPDATE meta SET value='99' WHERE key='schema_version'")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="unsupported database schema"):
        Store(str(db))
