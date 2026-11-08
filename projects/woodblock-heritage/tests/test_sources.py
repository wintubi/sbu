from __future__ import annotations

import base64
import io

from PIL import Image

from app.images import synthetic_png


def test_source_create_dedupe_and_image(client):
    png = synthetic_png()
    body = {
        "filename": "synthetic.png", "source_note": "synthetic only",
        "access_policy": "synthetic-only", "physical_index": None,
        "printed_label": "040", "image_base64": base64.b64encode(png).decode("ascii"),
    }
    first = client.post("/api/v1/heritage/sources", json=body)
    assert first.status_code == 201, first.text
    source = first.json()
    assert source["media_type"] == "image/png"
    assert source["width"] == 64 and source["height"] == 96
    assert source["physical_index"] is None

    second = client.post("/api/v1/heritage/sources", json=body)
    assert second.status_code == 200
    assert second.json()["source_id"] == source["source_id"]

    conflict = client.post("/api/v1/heritage/sources", json={**body, "source_note": "different"})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "SOURCE_METADATA_CONFLICT"

    image = client.get(f"/api/v1/heritage/sources/{source['source_id']}/image")
    assert image.status_code == 200
    assert image.content == png
    assert image.headers["x-content-type-options"] == "nosniff"


def test_source_rejects_bad_base64_and_truncated_png(client):
    bad = client.post("/api/v1/heritage/sources", json={
        "filename": "x.png", "source_note": "x", "access_policy": "synthetic-only",
        "image_base64": "not-base64!!",
    })
    assert bad.status_code == 422
    assert bad.json()["code"] == "INVALID_BASE64"

    truncated = synthetic_png()[:80]
    response = client.post("/api/v1/heritage/sources", json={
        "filename": "x.png", "source_note": "x", "access_policy": "synthetic-only",
        "image_base64": base64.b64encode(truncated).decode("ascii"),
    })
    assert response.status_code == 415
    assert response.json()["code"] in {"INVALID_IMAGE", "UNSUPPORTED_IMAGE_TYPE"}


def test_source_byte_and_pixel_limits(client, monkeypatch):
    import app.images as images
    body = {
        "filename": "synthetic.png", "source_note": "synthetic only",
        "access_policy": "synthetic-only",
        "image_base64": base64.b64encode(synthetic_png()).decode("ascii"),
    }
    monkeypatch.setattr(images, "MAX_SOURCE_BYTES", 10)
    response = client.post("/api/v1/heritage/sources", json=body)
    assert response.status_code == 413
    assert response.json()["code"] == "SOURCE_TOO_LARGE"

    monkeypatch.undo()
    monkeypatch.setattr(images, "MAX_PIXELS", 10)
    response = client.post("/api/v1/heritage/sources", json=body)
    assert response.status_code == 413
    assert response.json()["code"] == "IMAGE_TOO_MANY_PIXELS"


def test_pixel_limit_is_checked_before_full_load(client, monkeypatch):
    import PIL.Image
    import app.images as images
    png = synthetic_png()  # create before patching load; putpixel itself loads
    monkeypatch.setattr(images, "MAX_PIXELS", 10)

    def boom(self):
        raise AssertionError("full load must not happen for oversized dimensions")

    monkeypatch.setattr(PIL.Image.Image, "load", boom)
    response = client.post("/api/v1/heritage/sources", json={
        "filename": "big.png", "source_note": "pixel limit",
        "access_policy": "synthetic-only",
        "image_base64": base64.b64encode(png).decode("ascii"),
    })
    assert response.status_code == 413
    assert response.json()["code"] == "IMAGE_TOO_MANY_PIXELS"


def test_unknown_access_policy_is_rejected(client):
    response = client.post("/api/v1/heritage/sources", json={
        "filename": "policy.png", "source_note": "policy test",
        "access_policy": "local_unverified_no_publication",
        "image_base64": base64.b64encode(synthetic_png(71, 96)).decode("ascii"),
    })
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_non_local_origin_write_is_rejected(client):
    response = client.post("/api/v1/heritage/sources", headers={"Origin": "https://evil.example"},
                           json={"filename": "x", "source_note": "x", "access_policy": "x",
                                 "image_base64": "eA=="})
    assert response.status_code == 403
    assert response.json()["code"] == "ORIGIN_NOT_ALLOWED"


def _synthetic_jpeg(width: int = 64, height: int = 96) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()


def test_jpeg_source_upload_and_truncation(client):
    jpeg = _synthetic_jpeg()
    source = client.post("/api/v1/heritage/sources", json={
        "filename": "synthetic.jpg", "source_note": "jpeg test",
        "access_policy": "synthetic-only",
        "image_base64": base64.b64encode(jpeg).decode("ascii"),
    })
    assert source.status_code == 201, source.text
    assert source.json()["media_type"] == "image/jpeg"

    truncated = client.post("/api/v1/heritage/sources", json={
        "filename": "truncated.jpg", "source_note": "jpeg truncation",
        "access_policy": "synthetic-only",
        "image_base64": base64.b64encode(jpeg[:100]).decode("ascii"),
    })
    assert truncated.status_code == 415
    assert truncated.json()["code"] in {"INVALID_IMAGE", "UNSUPPORTED_IMAGE_TYPE"}


def test_jpeg_pixel_limit_is_checked_before_full_load(client, monkeypatch):
    import PIL.Image
    import app.images as images
    jpeg = _synthetic_jpeg()
    monkeypatch.setattr(images, "MAX_PIXELS", 10)

    def boom(self):
        raise AssertionError("full JPEG load must not happen before pixel check")

    monkeypatch.setattr(PIL.Image.Image, "load", boom)
    response = client.post("/api/v1/heritage/sources", json={
        "filename": "big.jpg", "source_note": "jpeg pixel limit",
        "access_policy": "synthetic-only",
        "image_base64": base64.b64encode(jpeg).decode("ascii"),
    })
    assert response.status_code == 413
    assert response.json()["code"] == "IMAGE_TOO_MANY_PIXELS"
