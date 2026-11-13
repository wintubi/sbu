"""独立进程 loopback 烟测的 pytest 包装：只运行本地脚本，不访问真实供应商。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

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
