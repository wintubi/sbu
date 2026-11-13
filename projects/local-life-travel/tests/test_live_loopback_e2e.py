"""独立进程 loopback 烟测的 pytest 包装：只运行本地脚本，不访问真实供应商。"""
from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "live_loopback_e2e.py"


def test_independent_process_loopback_smoke():
    # 故意在环境里放一个“真实 Key”哨兵：脚本必须继续用显式合成 Key + MockTransport。
    env = os.environ.copy()
    env["AMAP_API_KEY"] = "real-key-must-not-be-used"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=str(ROOT), env=env, capture_output=True,
        text=True, timeout=180)
    combined = completed.stdout + "\n" + completed.stderr
    assert completed.returncode == 0, combined
    assert "E2E_OK" in completed.stdout
    # 汇总必须来自真实计数，不是预写常量。
    assert '"create"' in completed.stdout and '"revision"' in completed.stdout
    assert '"transport_sends": 3' in completed.stdout
    assert "real-key-must-not-be-used" not in combined
    assert "Traceback" not in combined


def _script_module():
    spec = importlib.util.spec_from_file_location("live_loopback_e2e_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _HangingProcess:
    """stdout 永不产出 PORT=；用于验证握手超时不再卡死。"""

    def __init__(self):
        read_fd, self._write_fd = os.pipe()
        self.stdout = os.fdopen(read_fd, "r", encoding="utf-8")
        self.stderr = io.StringIO("")
        self.stdin = io.StringIO()
        self.returncode = None
        self.killed = False

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        if self._write_fd is not None:
            os.close(self._write_fd)
            self._write_fd = None
        self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("fake-child", timeout)
        return self.returncode


def test_port_handshake_timeout_fails_fast_and_kills_child(monkeypatch, tmp_path):
    module = _script_module()
    fake = _HangingProcess()
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: fake)
    monkeypatch.setattr(module.ChildApp, "HANDSHAKE_TIMEOUT", 0.2)
    child = module.ChildApp(tmp_path / "db.sqlite3", tmp_path / "log.jsonl",
                            tmp_path / "gate", "", "=")
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        child.__enter__()
    assert time.monotonic() - started < 5  # 不再挂在无超时 readline 上
    assert fake.killed  # 握手失败仍停止自己启动的子进程
