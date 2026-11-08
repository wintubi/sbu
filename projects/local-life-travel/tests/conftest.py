"""Shared fixtures. Keeps every test on an isolated SQLite file."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ["TRAVEL_REPLAY_NO_AUTOSTART"] = "1"
os.environ["TRAVEL_REPLAY_DB"] = str(ROOT / "data" / "pytest_master.sqlite3")

from fastapi.testclient import TestClient  # noqa: E402

from app.domain import TERMINAL_STATUSES  # noqa: E402
from app.engine import advance  # noqa: E402
from app.main import create_app  # noqa: E402
from app.replay_tools import ReplayAdapter, resolve_all  # noqa: E402
from app.store import Store  # noqa: E402
from app.worker import Worker  # noqa: E402


@pytest.fixture
def db_path() -> str:
    # OS temp may be outside the writable scope; keep test DBs inside project.
    folder = ROOT / "data" / "pytest"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}.sqlite3"
    yield str(path)
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            try:
                candidate.unlink()
            except OSError:
                pass


@pytest.fixture
def store(db_path):
    s = Store(db_path)
    yield s
    s.close()


@pytest.fixture
def worker(store):
    w = Worker(store, autostart=False)
    yield w
    w.stop()


@pytest.fixture
def app(store, worker):
    return create_app(store=store, worker=worker, manual_drain=True)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def drain_with(store: Store, run_id: str, adapter: ReplayAdapter, max_ticks: int = 20):
    """Advance one run with an explicitly injected adapter (custom scenarios)."""
    for _ in range(max_ticks):
        run = store.get_run(run_id)
        if run is None or run["status"] in TERMINAL_STATUSES:
            break
        advance(store, run_id, adapter=adapter)
    return store.get_run(run_id)


@pytest.fixture
def scenarios():
    return {s["id"]: s for s in resolve_all()}
