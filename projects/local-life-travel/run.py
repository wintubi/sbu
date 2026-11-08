"""Start the local replay server.

    python run.py
    # then open http://127.0.0.1:8765

No external service is contacted. All data comes from fixtures/scenarios.json.
"""
from __future__ import annotations

import os

import uvicorn

from app.main import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.environ.get("TRAVEL_REPLAY_HOST", "127.0.0.1"),
        port=int(os.environ.get("TRAVEL_REPLAY_PORT", "8765")),
        log_level="info",
    )
