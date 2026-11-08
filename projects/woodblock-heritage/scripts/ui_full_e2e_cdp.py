"""Full Chrome/CDP UI flow for the heritage review slice.

Covers: real file upload -> candidate import -> approve -> stale-version 409
-> reload current -> revise -> approve -> publish -> current knowledge/history.
Still not covered: canvas hit-testing, drag/drop, multi-tab concurrent UI.

Usage: start `python run.py` on 8770, then run this script.
"""
from __future__ import annotations

import argparse
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

    def cmd(self, method: str, params: dict | None = None) -> dict:
        self.counter += 1
        ident = self.counter
        self.ws.send(json.dumps({"id": ident, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == ident:
                if "error" in message:
                    raise RuntimeError(f"CDP {method}: {message['error']}")
                return message.get("result", {})

    def eval(self, expression: str):
        result = self.cmd("Runtime.evaluate", {
            "expression": expression, "awaitPromise": True,
            "returnByValue": True, "userGesture": True,
        })
        if "exceptionDetails" in result:
            raise RuntimeError(f"page exception: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")

    def wait(self, expression: str, timeout: float = 20.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.eval(expression):
                return True
            time.sleep(0.2)
        raise TimeoutError(f"page condition not met: {expression}")


def api_reject(base_url: str, work_id: str, version: int):
    with httpx.Client(base_url=base_url, timeout=10.0, trust_env=False) as client:
        response = client.post(f"/api/v1/heritage/works/{work_id}/reviews",
                               headers={"Idempotency-Key": "cdp-conflict-advance"},
                               json={"expected_version": version, "reviewer": "cdp-other-tab",
                                     "reason": "另一页面推进版本，制造冲突",
                                     "decisions": [{"claim_id": "c-category", "action": "reject"}]})
        assert response.status_code == 200, response.text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8770")
    parser.add_argument("--chrome", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--profile", default=str(Path(tempfile.gettempdir()) / "chrome-heritage-full"))
    parser.add_argument("--screenshot", default=str(Path(tempfile.gettempdir()) / "chrome-heritage-full" / "ui-full.png"))
    parser.add_argument("--port", type=int, default=9224)
    args = parser.parse_args()

    upload = Path(args.profile) / "upload.png"
    Path(args.profile).mkdir(parents=True, exist_ok=True)
    upload.write_bytes(synthetic_png())
    chrome = subprocess.Popen([
        args.chrome, "--headless=new", "--disable-gpu", "--no-first-run",
        "--no-default-browser-check", f"--user-data-dir={args.profile}",
        f"--remote-debugging-port={args.port}", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 15
        ready = False
        while time.time() < deadline:
            try:
                httpx.get(f"http://127.0.0.1:{args.port}/json/version", timeout=1.0,
                          trust_env=False).raise_for_status()
                ready = True
                break
            except Exception:
                time.sleep(0.2)
        assert ready, "Chrome CDP endpoint not ready"
        tab = httpx.put(f"http://127.0.0.1:{args.port}/json/new?{args.base_url}/",
                        timeout=5.0, trust_env=False).json()
        cdp = CDP(tab["webSocketDebuggerUrl"])
        cdp.cmd("Page.enable")
        cdp.cmd("DOM.enable")
        cdp.cmd("Runtime.enable")
        cdp.wait("document.readyState === 'complete'")

        # 1. Real file input upload.
        document = cdp.cmd("DOM.getDocument", {"depth": -1})
        node = cdp.cmd("DOM.querySelector", {"nodeId": document["root"]["nodeId"],
                                             "selector": "#source-file"})
        if not node.get("nodeId"):
            raise RuntimeError("file input not found")
        cdp.cmd("DOM.setFileInputFiles", {"nodeId": node["nodeId"], "files": [str(upload)]})
        cdp.eval("document.getElementById('source-note').value = 'CDP 上传合成页'; true")
        cdp.eval("document.getElementById('source-form').requestSubmit(); true")
        cdp.wait("!document.getElementById('source-result').hidden")
        cdp.wait("document.getElementById('source-image').naturalWidth > 0")

        # 2. Generate candidate from source and import.
        cdp.eval("document.getElementById('make-sample').click(); true")
        cdp.wait("document.getElementById('work-json').value.length > 0")
        cdp.eval("document.getElementById('import-work').click(); true")
        cdp.wait("document.getElementById('work-detail').hidden === false", 20)
        count = cdp.eval("document.querySelectorAll('.claim').length")
        assert count == 2, f"expected 2 claims, got {count}"
        canvas_width = cdp.eval("document.getElementById('region-canvas').width")
        assert canvas_width and canvas_width > 0, f"canvas not drawn: {canvas_width}"
        hit = cdp.eval("""
          (() => {
            const canvas = document.getElementById('region-canvas');
            const rect = canvas.getBoundingClientRect();
            canvas.dispatchEvent(new MouseEvent('click', {
              clientX: rect.left + rect.width * 0.3,
              clientY: rect.top + rect.height * 0.1,
              bubbles: true,
            }));
            return document.getElementById('region-info').textContent;
          })()
        """)
        assert "命中 r-title" in hit, hit

        # 3. Approve both, then create a stale version from another client.
        cdp.eval("""
          (() => {
            document.querySelectorAll('.claim').forEach(card => {
              const select = card.querySelector('.action');
              select.value = 'approve';
              select.dispatchEvent(new Event('change', {bubbles: true}));
            });
            document.getElementById('review-reason').value = 'CDP 首次审核';
            document.getElementById('submit-review').click();
            return true;
          })()
        """)
        cdp.wait("document.getElementById('work-header').textContent.includes('当前 v2')")
        work_id = cdp.eval("""
          (() => {
            const text = document.getElementById('work-header').textContent;
            const match = text.match(/work_[a-f0-9]+/);
            return match ? match[0] : null;
          })()
        """)
        assert work_id, "work id not found in header"
        api_reject(args.base_url, work_id, 2)
        # Page still thinks v2; submitting again must get 409 and reload v3.
        cdp.eval("""
          (() => {
            document.querySelectorAll('.claim').forEach(card => {
              const select = card.querySelector('.action');
              select.value = 'approve';
              select.dispatchEvent(new Event('change', {bubbles: true}));
            });
            document.getElementById('review-reason').value = '旧的 v2 提交';
            document.getElementById('submit-review').click();
            return true;
          })()
        """)
        cdp.wait("document.getElementById('work-header').textContent.includes('当前 v3')", 20)
        events_text = cdp.eval("document.getElementById('events').textContent")
        assert "v2 → v3" in events_text, events_text

        # 4. Revise the title claim, then approve it.
        cdp.eval("""
          (() => {
            const card = [...document.querySelectorAll('.claim')]
              .find(item => item.dataset.claim === 'c-title');
            const select = card.querySelector('.action');
            select.value = 'revise';
            select.dispatchEvent(new Event('change', {bubbles: true}));
            card.querySelector('.revise-value').value = '合成门神示例（修订）';
            card.querySelector('.revise-evidence').value = 'r-title';
            document.getElementById('review-reason').value = 'CDP 修订值';
            document.getElementById('submit-review').click();
            return true;
          })()
        """)
        cdp.wait("document.getElementById('work-header').textContent.includes('当前 v4')", 20)
        cdp.eval("""
          (() => {
            const card = [...document.querySelectorAll('.claim')]
              .find(item => item.dataset.claim === 'c-title');
            const select = card.querySelector('.action');
            select.value = 'approve';
            select.dispatchEvent(new Event('change', {bubbles: true}));
            document.getElementById('review-reason').value = 'CDP 修订后批准';
            document.getElementById('submit-review').click();
            return true;
          })()
        """)
        cdp.wait("document.getElementById('work-header').textContent.includes('当前 v5')", 20)

        # 5. Resolve the synthetic pairing issue, then publish.
        cdp.eval("""
          (() => {
            const checkbox = document.querySelector('#issues .issue-resolve');
            if (checkbox) checkbox.checked = true;
            document.getElementById('review-reason').value = 'CDP 处置配对疑问';
            document.getElementById('submit-review').click();
            return true;
          })()
        """)
        cdp.wait("document.getElementById('work-header').textContent.includes('当前 v6')", 20)
        cdp.eval("""
          (() => {
            document.getElementById('review-reason').value = 'CDP 发布';
            document.getElementById('publish').click();
            return true;
          })()
        """)
        cdp.wait("document.querySelectorAll('#knowledge article').length > 0", 20)
        knowledge = cdp.eval("document.getElementById('knowledge').textContent")
        assert "合成门神示例（修订）" in knowledge, knowledge
        cdp.wait("document.querySelectorAll('#publication-history article').length > 0", 20)
        history_text = cdp.eval("document.getElementById('publication-history').textContent")
        assert "v6" in history_text and "当前发布版本" in history_text, history_text
        # 6. Switch to a historical version (read-only), then back to current.
        cdp.eval("""
          (() => {
            const select = document.getElementById('version-select');
            select.value = '2';
            select.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
          })()
        """)
        cdp.wait("document.getElementById('work-header').textContent.includes('历史·只读')", 20)
        assert cdp.eval("document.getElementById('submit-review').disabled") is True
        assert cdp.eval("document.querySelector('.claim .action').disabled") is True
        assert cdp.eval("document.querySelectorAll('#issues .issue-resolve').length === 0 "
                        "|| document.querySelector('#issues .issue-resolve').disabled") is True
        old_text = cdp.eval("document.getElementById('claims').textContent")
        assert "合成门神示例" in old_text and "（修订）" not in old_text, old_text
        cdp.eval("""
          (() => {
            const select = document.getElementById('version-select');
            select.value = '6';
            select.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
          })()
        """)
        cdp.wait("!document.getElementById('submit-review').disabled", 20)
        assert cdp.eval("document.querySelector('.claim .action').disabled") is False
        current_text = cdp.eval("document.getElementById('claims').textContent")
        assert "（修订）" in current_text, current_text
        cdp.eval("document.getElementById('knowledge').scrollIntoView({block: 'start'}); true")
        time.sleep(0.4)
        shot = cdp.cmd("Page.captureScreenshot", {"format": "png"})
        Path(args.screenshot).parent.mkdir(parents=True, exist_ok=True)
        Path(args.screenshot).write_bytes(base64.b64decode(shot["data"]))
        # 7. Reject a claim in the page; current version advances and the old
        # snapshot must disappear from current knowledge (but stay historical).
        cdp.eval("""
          (() => {
            const card = [...document.querySelectorAll('.claim')]
              .find(item => item.dataset.claim === 'c-category');
            const select = card.querySelector('.action');
            select.value = 'reject';
            select.dispatchEvent(new Event('change', {bubbles: true}));
            document.getElementById('review-reason').value = 'CDP 页面驳回分类断言';
            document.getElementById('submit-review').click();
            return true;
          })()
        """)
        cdp.wait("document.getElementById('work-header').textContent.includes('当前 v7')", 20)
        cdp.wait("document.querySelectorAll('#knowledge article').length === 0", 20)
        print(f"work={work_id} upload=true revise=true conflict_reload=true publish=true ui_reject=true")
        print(f"knowledge={knowledge.strip()[:120]}")
        print(f"screenshot={args.screenshot}")
        return 0
    finally:
        chrome.terminate()
        try:
            chrome.wait(timeout=5)
        except subprocess.TimeoutExpired:
            chrome.kill()


if __name__ == "__main__":
    raise SystemExit(main())
