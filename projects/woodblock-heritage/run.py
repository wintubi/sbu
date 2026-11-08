"""Local entry point: python run.py, then open http://127.0.0.1:8770.

The UI is intentionally served from the same origin as the JSON API. No
external model, OCR or graph database is called.
"""
from __future__ import annotations

import os

import uvicorn

from app.main import create_app

app = create_app()


if __name__ == "__main__":
    uvicorn.run("run:app", host="127.0.0.1", port=int(os.environ.get("HERITAGE_PORT", "8770")),
                reload=False)
