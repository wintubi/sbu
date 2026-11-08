"""Real-Chrome travel UI smoke via CDP (no Playwright temp directory).

Covers four frozen replay scenarios: feasible (F01), infeasible (F07),
ambiguity (F11), provider format error (F16). Asserts status/quality/issues
rendered by the actual page, then captures a screenshot.
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import time
from pathlib import Path

import httpx
import websocket


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

    def wait(self, expression, timeout=25.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.eval(expression):
                return
            time.sleep(0.2)
        raise TimeoutError(expression)


def select_and_submit(cdp: CDP, scenario_id: str):
    cdp.eval(f"""
      (() => {{
        const sel = document.getElementById('scenario');
        sel.value = {json.dumps(scenario_id)};
        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
        document.getElementById('load').click();
        return true;
      }})()
    """)
    # loadSelected is async; wait for its explicit status message.
    cdp.wait(f"document.getElementById('formMsg').textContent.includes('已载入 {scenario_id}')")
    cdp.eval("document.getElementById('submit').click(); true")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--chrome", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--profile", default=r"D:\workspace-dsh\tmp\chrome-travel")
    parser.add_argument("--screenshot", default=r"D:\git\sbu\projects\local-life-travel\docs\evidence\ui-travel.png")
    parser.add_argument("--port", type=int, default=9227)
    args = parser.parse_args()
    Path(args.profile).mkdir(parents=True, exist_ok=True)
    chrome = subprocess.Popen([
        args.chrome, "--headless=new", "--disable-gpu", "--no-first-run",
        "--no-default-browser-check", f"--user-data-dir={args.profile}",
        f"--remote-debugging-port={args.port}", "--window-size=1440,1800", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                httpx.get(f"http://127.0.0.1:{args.port}/json/version", timeout=1.0,
                          trust_env=False)
                break
            except Exception:
                time.sleep(0.2)
        tab = httpx.put(f"http://127.0.0.1:{args.port}/json/new?{args.base_url}/",
                        timeout=5.0, trust_env=False).json()
        cdp = CDP(tab["webSocketDebuggerUrl"])
        cdp.cmd("Page.enable")
        cdp.cmd("Runtime.enable")
        cdp.wait("document.readyState === 'complete'")
        cdp.wait("document.querySelectorAll('#scenario option').length >= 20")

        select_and_submit(cdp, "F01")
        cdp.wait("!!document.querySelector('#result .pill.q-verified_feasible')")
        cdp.wait("!!document.querySelector('#result .pill.st-completed')")
        f01_text = cdp.eval("document.getElementById('result').textContent")
        assert "TIME_WINDOW_EXCEEDED" not in f01_text

        select_and_submit(cdp, "F07")
        cdp.wait("!!document.querySelector('#result .pill.q-infeasible')")
        cdp.wait("document.getElementById('result').textContent.includes('TIME_WINDOW_EXCEEDED')")
        f07_text = cdp.eval("document.getElementById('result').textContent")

        select_and_submit(cdp, "F11")
        cdp.wait("!!document.querySelector('#result .pill.st-needs_input')")
        cdp.wait("document.getElementById('result').textContent.includes('需要用户输入')")
        f11_text = cdp.eval("document.getElementById('result').textContent")

        select_and_submit(cdp, "F16")
        cdp.wait("!!document.querySelector('#result .pill.st-failed')")
        cdp.wait("document.getElementById('result').textContent.includes('TOOL_FORMAT_ERROR')")
        f16_text = cdp.eval("document.getElementById('result').textContent")
        cdp.eval("document.getElementById('result').scrollIntoView({block: 'start'}); true")
        time.sleep(0.4)

        shot = cdp.cmd("Page.captureScreenshot", {"format": "png"})
        Path(args.screenshot).parent.mkdir(parents=True, exist_ok=True)
        Path(args.screenshot).write_bytes(base64.b64decode(shot["data"]))
        print("F01=verified_feasible F07=infeasible F11=needs_input F16=failed")
        print(f"issues_visible=F07:{'TIME_WINDOW_EXCEEDED' in f07_text} "
              f"F16:{'TOOL_FORMAT_ERROR' in f16_text} ambiguity:{'需要用户输入' in f11_text}")
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
