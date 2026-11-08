from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from app.errors import ApiError
from app.models import Decision, ReviewCreate
from app.service import review_work
from app.store import Store


def test_two_reviews_with_same_expected_version_only_one_wins(client, work):
    db_path = client.app.state.store.db_path
    barrier = threading.Barrier(2)

    def run(key: str, action: str):
        store = Store(db_path)
        barrier.wait(timeout=5)
        try:
            body = ReviewCreate(
                expected_version=1,
                reviewer="local-reviewer",
                reason=f"concurrent {action}",
                decisions=[Decision(claim_id="c-title", action=action,
                                    support_status="supported" if action == "approve" else None)],
            )
            response, status = review_work(store, work["work_id"], body, key)
            return ("ok", status, response["work"]["current_version"])
        except ApiError as exc:
            return ("error", exc.status, exc.code)
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(run, "concurrent-a", "approve"),
                   pool.submit(run, "concurrent-b", "reject")]
        outcomes = [future.result(timeout=10) for future in results]

    successes = [item for item in outcomes if item[0] == "ok"]
    conflicts = [item for item in outcomes if item[0] == "error"]
    assert len(successes) == 1
    assert successes[0][2] == 2
    assert len(conflicts) == 1
    assert conflicts[0][1] == 409
    assert conflicts[0][2] == "VERSION_CONFLICT"
    current = client.get(f"/api/v1/heritage/works/{work['work_id']}")
    assert current.json()["current_version"] == 2
    assert len(current.json()["events"]) == 1
