# CR 修复回执 r1（cr-fix-r1）

- run_id：`20261113T091208Z-cr-RW1pFk`
- task_id：`cr-fix-r1`
- 仓库：`D:/workspace-dsh/tmp/sbu-travel-runtime-budget`
- 项目根：`projects/local-life-travel`
- HEAD：`111f274`；分支：`feat/travel-runtime-budget`
- 修复范围：CRD-02、CRD-03、CRD-04、CRD-05，以及 scope medium 的两处文档事实错误。
- 明确未修：CRD-01（归 T12）；EP-01/EP-02（base 既有）。`design/specs/tasks/tickets` 未改。
- 工作树状态：改动全部未提交；未 push/merge/reset；未访问真实供应商；未派子代理。

## CRD-02 cancel 路由把 `missing` 落成成功路径

**finding**：`app/main.py:382` 只处理 `terminal`，`Store.cancel_run` 的第三值 `missing` 继续进入成功路径：LIVE 分支先写 `CANCELLED` 事件，再用取消前旧快照返回 200；replay 分支直接硬编码 `status="cancelled"`。对已不存在的行报成功。

**修法**：`app/main.py` cancel 路由在 `terminal` 判断前增加：

```python
if outcome == "missing":
    raise ApiError(404, "RUN_NOT_FOUND", f"运行 {run_id} 不存在", run_id=run_id)
```

沿用既有 `RUN_NOT_FOUND` 错误体；抛出点在 `add_event`/LIVE 分支之前，因此不写事件。replay/LIVE 其余成功/409 分支未改。

**测试**：`tests/test_api.py::test_cancel_missing_run_returns_404_without_event`。构造方式：创建 replay run 后，用独立 SQLite 连接删除该 run 行，再把 `store.cancel_run` 包装成“先删后调用原实现”，确定性触发 `get_run` 与条件取消之间的缺行竞态。

**红**（修前，连同 CRD-03 新测试一起跑）：

```text
FAILED tests/test_api.py::test_cancel_missing_run_returns_404_without_event
E       assert 200 == 404
4 failed in 1.73s
```

**绿**（修后）：

```text
....                                                                     [100%]
4 passed in 1.13s
```

测试同时断言 404 后 `events` 与取消前完全一致、无 `CANCELLED` 事件。

## CRD-03 reserve_http 把非正 operation timeout 伪装成 deadline 耗尽

**finding**：`app/runtime.py:97-98` 在 `remaining <= 0` 之外只可能来自配置 `base_timeout <= 0`，却抛 `BudgetExhausted("deadline")`，经 `app/live.py:_mark_exhausted` 落成 `budget.exhaustion_reason="deadline"` 与 `BUDGET_EXHAUSTED`，把操作级配置错误指向供应商延迟。

**修法**：

- `app/runtime.py`：`timeout <= 0` 改为 `raise RuntimeControlError("INVALID_OPERATION_TIMEOUT")`，复用既有固定分类，不写 `exhaustion_reason`、不递增 `tool_calls`、不发送。
- `app/live.py`：`RuntimeControlError` 分类新增固定安全文案分支：`INVALID_OPERATION_TIMEOUT` → `_mark_execution_failure(... "操作级 timeout 配置非法（INVALID_OPERATION_TIMEOUT）")`，落在既有 `STAGE_EXECUTION_ERROR`；其他控制错误文案不变。

**测试**：

- `tests/test_live_deadline_cancel.py::test_reserve_http_rejects_non_positive_configured_timeout[0.0]` / `[-1.0]`：断言抛 `RuntimeControlError`、不是 `BudgetExhausted`、`category == "INVALID_OPERATION_TIMEOUT"`、无 `exhaustion_reason`、`tool_calls == 0`。
- `tests/test_live_deadline_cancel.py::test_configured_zero_timeout_is_not_reported_as_deadline`：真实 `AmapClient(timeout=0.0)` + `MockTransport` 走 API 全路径；断言 `status=failed`、`budget.status=failed`、无 `exhaustion_reason`、`tool_calls=0`、transport `sent == []`、`STAGE_EXECUTION_ERROR` 且文案含 `INVALID_OPERATION_TIMEOUT`、`result=None`/`quality=unverified`。

**红**（修前）：

```text
FAILED ...::test_reserve_http_rejects_non_positive_configured_timeout[0.0]
E  app.runtime.BudgetExhausted: live runtime deadline exhausted
FAILED ...::test_reserve_http_rejects_non_positive_configured_timeout[-1.0]
E  app.runtime.BudgetExhausted: live runtime deadline exhausted
FAILED ...::test_configured_zero_timeout_is_not_reported_as_deadline
E  AssertionError: assert 'exhausted' == 'failed'
```

**绿**（修后）：

```text
......                                                                   [100%]
6 passed in 1.10s
```

（含既有 `test_cancel_probe_failure_does_not_leak_raw_exception` 回归，确认探针文案分支未被破坏。）

## CRD-04 端口握手无超时阻塞 / stderr 管道互锁

**finding**：`scripts/live_loopback_e2e.py:196-209` 先执行无超时的 `self.proc.stdout.readline()`，25 秒 deadline 只在其后判断；子进程不打印 `PORT=` 时父进程永久挂起，kill 收尾不可达。`stderr=subprocess.PIPE` 握手期无人 drain，还存在管道缓冲互锁。

**修法**：

- 握手改为“stdout 读线程 + `queue.Queue` + `Queue.get(timeout=remaining)`”：主线程不再阻塞在无超时 `readline` 上，25 秒 deadline 真正生效，超时抛 `TimeoutError`。
- stderr 由后台 daemon 线程用 `read(4096)` 持续 drain，有界保留（最多 32 个 chunk，展示截断 2000 字符），消除管道互锁；失败信息改用 `stderr_text()`。
- 握手失败在 `__enter__` 的 `except` 中 kill 并 `wait` 自己启动的子进程；`__exit__` 改为只要 `proc` 存在就 `stop()`，不再以 `stdin.closed` 作为是否收尾的条件。`stop()` 增加 `stdin` 已关闭时的 `ValueError` 兜底，并在等待/终止后 join 读线程。
- 超时经 `main()` 既有 `except Exception` 走 `E2E_FAILED` + `return 1`。

**测试**：`tests/test_live_loopback_e2e.py::test_port_handshake_timeout_fails_fast_and_kills_child`。用 importlib 加载脚本，替换 `subprocess.Popen` 为 stdout 永不产出 `PORT=` 的假进程，并注入 `HANDSHAKE_TIMEOUT=0.2`；断言 5 秒内抛 `TimeoutError` 且假进程被 `kill()`。

**红**：修复前为静态路径（`readline` 无超时，deadline 判断在阻塞之后；评审已静态定位，未构造会真占用 25s+ 的挂起进程）。

**绿**：

```text
..                                                                       [100%]
2 passed in 13.78s
```

同时全量 suite 与独立脚本均通过（见“最终证据”）。

## CRD-05 mkdtemp 在 try 外且假定 data/ 存在

**finding**：`scripts/live_loopback_e2e.py:456` 的 `tempfile.mkdtemp(dir=PROJECT_ROOT/"data")` 在 `try` 外；新 clone 无 `data/`，直接抛裸 `FileNotFoundError`，不打印 `E2E_FAILED`，也不走清理/退出码约定。

**修法**：把工作目录准备移入 `try`，先 `data_dir.mkdir(parents=True, exist_ok=True)`，再 `mkdtemp`；`work` 初始化为 `None`，失败时打印 `E2E_FAILED; work directory could not be created`（工作目录已建失败）或 `E2E_FAILED; artifacts kept at ...`，统一 `return 1`；`finally` 只在成功且 `work` 存在时清理。

**红**（修前，从 `HEAD` 的 git archive 复制到无 `data/` 的临时目录单跑）：

```text
DATA_EXISTS=False
  File "...\scripts\live_loopback_e2e.py", line 456, in main
    work = Path(tempfile.mkdtemp(prefix="live-loopback-", dir=str(PROJECT_ROOT / "data")))
FileNotFoundError: [WinError 3] 系统找不到指定的路径。: '...\data\live-loopback-8y3ud2ud'
EXIT=1
```

未打印 `E2E_FAILED`，即时复现评审结论。

**绿**（修后，把当前工作树复制到无 `data/` 的临时目录，`DATA_EXISTS_BEFORE=False`）：

```text
SCRIPT_EXIT=0
{"create": ..., "revision": ...}
E2E_OK

PYTEST_EXIT=0
1 passed in 10.61s
```

即新 clone 单跑脚本与 `tests/test_live_loopback_e2e.py` 包装都能自行创建 `data/`。

## scope medium：两份文档仍称 T11 在 git stash

**finding**：`docs/TECH-STACK.md:5` 与 `docs/ARCHITECTURE.md:4` 写“T11 半成品已存入本地 git stash”，与事实不符：T11 票 1–4 已在 `3bed847`/`03cb0d4`/`1aee907`/`111f274` 验收并提交在本分支，`git stash list` 为空。

**修法**：两条改为同一事实口径（只改指定行）：

> T11（LIVE 发送前准入、预算、时限、取消与异常清理）票 1–4 已验收（checkpoint `3bed847`/`03cb0d4`/`1aee907`/`111f274`）；改动在本分支 `feat/travel-runtime-budget`、未合并 main；本地 `git stash` 已恢复（当前无暂存条目）。

**证据**：

```text
git log --oneline -6
111f274 checkpoint(...task4-aggregate)...
1aee907 checkpoint(...task3-cleanup-e2e)...
03cb0d4 checkpoint(...task2-deadline-cancel)...
3bed847 checkpoint(...task1-http-admission)...
795f1de impl(travel-runtime-budget): task1 ...
git stash list   # 空
git branch --show-current
feat/travel-runtime-budget
```

## 最终证据（真实 exit / 计数）

命令与结果均在本工作树、HEAD `111f274` 上执行：

1. `C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider`

```text
159 passed, 2 warnings in 39.47s
EXIT=0
```

测试数由 154 增至 159（+5：cancel 缺行 1、reserve 非正 timeout 参数化 2、API 零 timeout 1、握手超时 1）。

2. `C:/Miniconda3/python.exe scripts/live_loopback_e2e.py`

```text
{"create": {"close_attempts": 1, "run_id": "run_4c1dcda028bd4dc5", "scenario": "create", "status": "cancelled", "tool_calls": 3, "transport_sends": 3}, "revision": {"child_run_id": "run_95e1192d89704d78", "child_tool_calls": 3, "close_attempts": 2, "parent_run_id": "run_489b9a7e284a4e0b", "parent_status": "needs_input", "scenario": "revision", "transport_sends": [11, 3]}, "scope": "independent-process loopback; real AmapAdapter + MockTransport; synthetic key; no real provider"}
E2E_OK
EXIT=0
```

3. 聚焦回归（CRD-02/03 + 既有探针脱敏 + 握手超时）：

```text
6 passed in 1.10s
```

## 改动文件

- `app/main.py`（CRD-02）
- `app/runtime.py`（CRD-03）
- `app/live.py`（CRD-03 固定分类文案）
- `scripts/live_loopback_e2e.py`（CRD-04/05）
- `docs/TECH-STACK.md`、`docs/ARCHITECTURE.md`（scope medium 事实修正）
- `tests/test_api.py`、`tests/test_live_deadline_cancel.py`、`tests/test_live_loopback_e2e.py`（回归测试）

`git diff --stat`：9 files changed, 226 insertions(+), 28 deletions(-)。全部保持未提交。

## 局限 / 未做

- CRD-01 未改（按任务归 T12）；EP-01/EP-02 未改（base 既有）。
- CRD-04 的“旧代码真挂起”未用会占住 25s+ 的进程复现；以静态阻塞点 + 修复后的 0.2s 聚焦测试作为行为证据。
- 未访问真实高德/真实 Key；未做网络抓包层“不出网”验证。
- 未提交、未 push/merge/reset，未改 design/specs/tasks/tickets 复选框。
