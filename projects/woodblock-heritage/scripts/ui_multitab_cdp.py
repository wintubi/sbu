"""Two real Chrome tabs: one review wins, the stale tab gets 409 and reloads."""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import websocket

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.images import synthetic_png  # noqa: E402


class CDP:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=20)
        self.counter = 0

    def cmd(self, method, params=None):
        self.counter += 1
        ident = self.counter
        self.ws.send(json.dumps({"id": ident, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == ident:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})

    def eval(self, expression):
        result = self.cmd("Runtime.evaluate", {"expression": expression, "awaitPromise": True,
                                               "returnByValue": True, "userGesture": True})
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    def wait(self, expression, timeout=20.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.eval(expression):
                return
            time.sleep(0.2)
        raise TimeoutError(expression)


def create_work(base_url: str) -> str:
    with httpx.Client(base_url=base_url, timeout=10.0, trust_env=False) as client:
        source = client.post("/api/v1/heritage/sources", json={
            "filename": "multitab.png", "source_note": "multi-tab synthetic",
            "access_policy": "synthetic-only",
            "image_base64": base64.b64encode(synthetic_png(66, 96)).decode("ascii"),
        })
        assert source.status_code in (200, 201), source.text
        source_id = source.json()["source_id"]
        work = client.post("/api/v1/heritage/works", headers={"Idempotency-Key": "multitab-work"}, json={
            "schema_version": "heritage-review-v1", "source_ids": [source_id],
            "regions": [{"id": "r-title", "source_id": source_id, "kind": "text",
                         "bbox": [0.05, 0.05, 0.7, 0.15], "coordinate_system": "normalized",
                         "text": "合成门神", "text_kind": "exact"}],
            "claims": [
                {"id": "c-title", "predicate": "source_title",
                 "object": {"kind": "literal", "value": "合成门神"}, "evidence_refs": ["r-title"]},
                {"id": "c-category", "predicate": "source_category",
                 "object": {"kind": "literal", "value": "门神"}, "evidence_refs": ["r-title"]},
            ],
            "issues": [],
        })
        assert work.status_code in (200, 201), work.text
        return work.json()["work_id"]


def open_tab(port: int, base: str) -> CDP:
    tab = httpx.put(f"http://127.0.0.1:{port}/json/new?{base}/", timeout=5.0,
                    trust_env=False).json()
    cdp = CDP(tab["webSocketDebuggerUrl"])
    cdp.cmd("Page.enable")
    cdp.cmd("Runtime.enable")
    cdp.wait("document.readyState === 'complete'")
    cdp.wait("document.querySelectorAll('#work-list button').length > 0")
    cdp.eval("document.querySelector('#work-list button').click()")
    cdp.wait("document.getElementById('work-detail').hidden === false")
    return cdp


def approve(cdp: CDP, reason: str):
    cdp.eval(f"""
      (() => {{
        document.querySelectorAll('.claim').forEach(card => {{
          const select = card.querySelector('.action');
          select.value = 'approve';
          select.dispatchEvent(new Event('change', {{bubbles: true}}));
        }});
        document.getElementById('review-reason').value = {json.dumps(reason)};
        document.getElementById('submit-review').click();
        return true;
      }})()
    """)


def main() -> int:
    base = "http://127.0.0.1:8770"
    work_id = create_work(base)
    profile = str(Path(tempfile.gettempdir()) / "chrome-heritage-multitab")
    Path(profile).mkdir(parents=True, exist_ok=True)
    chrome = subprocess.Popen([
        r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new",
        "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        f"--user-data-dir={profile}", "--remote-debugging-port=9226", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                httpx.get("http://127.0.0.1:9226/json/version", timeout=1.0, trust_env=False)
                break
            except Exception:
                time.sleep(0.2)
        tab_a = open_tab(9226, base)
        tab_b = open_tab(9226, base)
        approve(tab_a, "标签页 A 先提交")
        tab_a.wait("document.getElementById('work-header').textContent.includes('当前 v2')")
        # B still shows v1; its submit must hit 409 and reload v2.
        approve(tab_b, "标签页 B 旧版本提交")
        tab_b.wait("document.getElementById('work-header').textContent.includes('当前 v2')")
        events = tab_b.eval("document.getElementById('events').textContent")
        assert "v1 → v2" in events, events
        print(f"work={work_id} tab_a=v2 tab_b_reloaded_v2 conflict_handled=true")
        return 0
    finally:
        chrome.terminate()
        try:
            chrome.wait(timeout=5)
        except subprocess.TimeoutExpired:
            chrome.kill()


if __name__ == "__main__":
    raise SystemExit(main())
