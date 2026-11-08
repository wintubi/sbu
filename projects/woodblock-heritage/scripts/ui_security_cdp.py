"""Chrome/CDP check that hostile claim text is rendered as text, not HTML."""
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

HOSTILE = '<b>不是标签</b><img src=x onerror="window.__xss=1">'


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


def create_hostile_work(base_url: str) -> str:
    with httpx.Client(base_url=base_url, timeout=10.0, trust_env=False) as client:
        source = client.post("/api/v1/heritage/sources", json={
            "filename": "hostile.png", "source_note": "hostile text synthetic",
            "access_policy": "synthetic-only",
            "image_base64": base64.b64encode(synthetic_png(65, 96)).decode("ascii"),
        })
        assert source.status_code in (200, 201), source.text
        source_id = source.json()["source_id"]
        work = client.post("/api/v1/heritage/works", headers={"Idempotency-Key": "hostile-work"}, json={
            "schema_version": "heritage-review-v1", "source_ids": [source_id],
            "regions": [{"id": "r-title", "source_id": source_id, "kind": "text",
                         "bbox": [0.05, 0.05, 0.7, 0.15], "coordinate_system": "normalized",
                         "text": "原文", "text_kind": "exact"}],
            "claims": [{"id": "c-hostile", "predicate": "source_title",
                        "object": {"kind": "literal", "value": HOSTILE},
                        "evidence_refs": ["r-title"]}],
            "issues": [],
        })
        assert work.status_code in (200, 201), work.text
        return work.json()["work_id"]


def main() -> int:
    base = "http://127.0.0.1:8770"
    work_id = create_hostile_work(base)
    profile = str(Path(tempfile.gettempdir()) / "chrome-heritage-security")
    Path(profile).mkdir(parents=True, exist_ok=True)
    chrome = subprocess.Popen([
        r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--headless=new",
        "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        f"--user-data-dir={profile}", "--remote-debugging-port=9225", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                httpx.get("http://127.0.0.1:9225/json/version", timeout=1.0, trust_env=False)
                break
            except Exception:
                time.sleep(0.2)
        tab = httpx.put(f"http://127.0.0.1:9225/json/new?{base}/", timeout=5.0,
                        trust_env=False).json()
        cdp = CDP(tab["webSocketDebuggerUrl"])
        cdp.cmd("Page.enable")
        cdp.cmd("Runtime.enable")
        cdp.wait("document.readyState === 'complete'")
        cdp.wait("document.querySelectorAll('#work-list button').length > 0")
        cdp.eval("document.querySelector('#work-list button').click()")
        cdp.wait("document.getElementById('work-detail').hidden === false")
        injected = cdp.eval("document.querySelectorAll('.claim b, .claim img').length")
        xss = cdp.eval("window.__xss === undefined ? 'undefined' : String(window.__xss)")
        text = cdp.eval("document.querySelector('.claim').textContent")
        assert injected == 0, f"hostile HTML injected: {injected}"
        assert xss == "undefined", f"onerror executed: {xss}"
        assert "<b>不是标签</b>" in text, text
        print(f"work={work_id} injected_elements=0 xss=undefined literal_text=true")
        return 0
    finally:
        chrome.terminate()
        try:
            chrome.wait(timeout=5)
        except subprocess.TimeoutExpired:
            chrome.kill()


if __name__ == "__main__":
    raise SystemExit(main())
