from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from app.images import synthetic_png
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "heritage.sqlite3"))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def source(client):
    response = client.post("/api/v1/heritage/sources", json={
        "filename": "synthetic-page.png",
        "source_note": "synthetic test page; not a real heritage image",
        "access_policy": "synthetic-only",
        "physical_index": None,
        "printed_label": "040",
        "image_base64": base64.b64encode(synthetic_png()).decode("ascii"),
    })
    assert response.status_code == 201, response.text
    return response.json()


def work_body(source_id: str = "src_demo") -> dict:
    return {
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
    }


@pytest.fixture
def work(client, source):
    response = client.post("/api/v1/heritage/works", json=work_body(source["source_id"]),
                           headers={"Idempotency-Key": "work-key-1"})
    assert response.status_code == 201, response.text
    return response.json()
