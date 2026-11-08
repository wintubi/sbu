"""Real-HTTP smoke test against a running local server.

Usage: python scripts/demo_e2e.py http://127.0.0.1:8770
Synthetic image only; no real heritage page, model, OCR or Neo4j.
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.images import synthetic_png  # noqa: E402


def main(base_url: str) -> int:
    # This host's NO_PROXY contains a bracketed IPv6 token that httpx 0.28
    # cannot parse; local smoke tests must not use the system proxy anyway.
    with httpx.Client(base_url=base_url, timeout=10.0, trust_env=False) as client:
        ready = client.get("/health/ready")
        assert ready.status_code == 200 and ready.json()["database"] == "ok", ready.text
        page = client.get("/")
        assert page.status_code == 200 and "default-src 'none'" in page.headers.get(
            "content-security-policy", "")
        source = client.post("/api/v1/heritage/sources", json={
            "filename": "synthetic-demo.png",
            "source_note": "Real-HTTP synthetic smoke; not a heritage original",
            "access_policy": "synthetic-only",
            "physical_index": None,
            "printed_label": "040",
            "image_base64": base64.b64encode(synthetic_png()).decode("ascii"),
        })
        assert source.status_code == 201, source.text
        source_id = source.json()["source_id"]
        work = client.post("/api/v1/heritage/works", headers={"Idempotency-Key": "demo-work"}, json={
            "schema_version": "heritage-review-v1",
            "source_ids": [source_id],
            "regions": [
                {"id": "r-title", "source_id": source_id, "kind": "text",
                 "bbox": [0.05, 0.05, 0.7, 0.15], "coordinate_system": "normalized",
                 "text": "合成门神示例", "text_kind": "exact"},
                {"id": "r-image", "source_id": source_id, "kind": "image",
                 "bbox": [0.1, 0.2, 0.9, 0.95], "coordinate_system": "normalized"},
            ],
            "claims": [
                {"id": "c-title", "predicate": "source_title",
                 "object": {"kind": "literal", "value": "合成门神示例"},
                 "evidence_refs": ["r-title"]},
                {"id": "c-category", "predicate": "source_category",
                 "object": {"kind": "literal", "value": "门神"},
                 "evidence_refs": ["r-title"]},
            ],
            "issues": [],
        })
        assert work.status_code == 201, work.text
        work_id = work.json()["work_id"]
        review = client.post(f"/api/v1/heritage/works/{work_id}/reviews",
                             headers={"Idempotency-Key": "demo-review"}, json={
            "expected_version": 1, "reviewer": "smoke-reviewer",
            "reason": "真实 HTTP 合成链路：逐项核对证据",
            "decisions": [
                {"claim_id": "c-title", "action": "approve", "support_status": "supported"},
                {"claim_id": "c-category", "action": "approve", "support_status": "supported"},
            ],
        })
        assert review.status_code == 200, review.text
        assert review.json()["work"]["current_version"] == 2
        publication = client.post("/api/v1/heritage/publications",
                                  headers={"Idempotency-Key": "demo-publish"}, json={
            "work_id": work_id, "expected_version": 2,
        })
        assert publication.status_code == 201, publication.text
        pub = publication.json()
        knowledge = client.get("/api/v1/heritage/knowledge")
        assert knowledge.status_code == 200, knowledge.text
        assert knowledge.json()["count"] == 1, knowledge.text
        print(f"ready={ready.json()['status']} source={source_id} work={work_id}")
        print(f"publication={pub['publication_id']} version={pub['version']} claims={len(pub['claims'])}")
        print(f"knowledge_count={knowledge.json()['count']} title={knowledge.json()['items'][0]['claims'][0]['object']['value']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8770"))
