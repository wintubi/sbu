# Task 4 聚合验证报告（task4-aggregate）

> run_id：`20261110T182434Z-impl-N2Sw5e` · task_id：`task4-aggregate` · change：`travel-runtime-budget`
> 角色：fresh 收尾票 implementer。本票只收集聚合验证证据，**未改动产品代码**（`app/`、`tests/`、`docs/`、design/specs/tickets/复选框均未改；未 `git add`、未 commit、未 push/merge/reset、未打 checkpoint 标签）。
> 记录日期：2026-11-13（Asia/Shanghai）。分支 `feat/travel-runtime-budget`，测试时 HEAD `1aee907de9f6245877fe03ce77fc24afb7e3f767`。

## 回执：prefix-principles 首行原样回显

```text
<!-- prefix-version: principles-b9a054bafa9c -->
```

## 0. suite-scope 权威输出（工作树模式，stdout 原样粘贴）

命令（起手 MUST 运行的权威 suite-scope；`--head` 缺省 = 工作树模式）：

```text
C:/Miniconda3/python.exe C:/Users/Lenovo/.agents/skills/sdflow-implement/scripts/impl_route.py suite-scope --root D:/workspace-dsh/tmp/sbu-travel-runtime-budget
```

退出码 `0`。stdout 逐字（单行 JSON；由管道直接写入本节，**未手工转录**，`mapping` 顺序与工具输出一致）：

```json
{"base": "6a785607e4bdb52e6c1af95e7b7b585d1b5d035b", "domains_configured": false, "head": "1aee907de9f6245877fe03ce77fc24afb7e3f767", "hit_domains": [], "layers": {}, "mapping": [{"domain": null, "path": "projects/local-life-travel/.gitignore", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/AGENTS.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/CLAUDE.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/README.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/app/amap_tools.py", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/app/domain.py", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/app/live.py", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/app/main.py", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/app/runtime.py", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/app/store.py", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/docs/ACCEPTANCE.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/docs/ARCHITECTURE.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/docs/IMPLEMENTATION.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/docs/LIVE-AMAP.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/docs/TECH-STACK.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/INDEX.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/.gitkeep", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/.openspec.yaml", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/.skip-merge", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/decision-memo.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/design.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/evidence/baseline-overshoot.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/evidence/generation-check.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/evidence/reproduce_budget.py", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-blockers.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/planning-decisions.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/planning-review.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task1-brief.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task1-http-admission.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task1-spec-r1.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task1-spec-r2.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task1-standards-r1.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task1-standards-r2.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task2-brief.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task2-deadline-cancel.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task2-spec-r1.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task2-standards-r1.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task3-brief.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task3-cleanup-e2e.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task3-spec-r1.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task3-standards-r1.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task4-brief.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/implementation-runtime.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/proposal.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review-dispatch.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/amendment-check.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/amendment-citation-check.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/amendment-citations.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/citation-check.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/citation-input.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/cold-findings.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/design-decision.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/design-gate.html", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/design-gate.revisions.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/final-citation-check.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/final-citations.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/final-wording-check.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/implementation-runtime-decision.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/main-findings.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/main-verification.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/planning-dispatch.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/task1-dispatch.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/task1-shared-context.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/task2-dispatch.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/task2-shared-context.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/task3-dispatch.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/task3-shared-context.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/task4-dispatch.json", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/review/task4-shared-context.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/spec-review-report.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/specs/live-runtime-control/spec.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/tasks.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/changes/travel-runtime-budget/tickets.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/config.yaml", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/schemas/sdflow-spec-driven/schema.yaml", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/schemas/sdflow-spec-driven/templates/design.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/schemas/sdflow-spec-driven/templates/proposal.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/schemas/sdflow-spec-driven/templates/spec.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/schemas/sdflow-spec-driven/templates/tasks.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/specs/.gitkeep", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/openspec/workflow/WORKFLOW-GUIDE.md", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/scripts/live_loopback_e2e.py", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/tests/test_live.py", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/tests/test_live_admission.py", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/tests/test_live_cleanup_redaction.py", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/tests/test_live_deadline_cancel.py", "prefix": null}, {"domain": null, "path": "projects/local-life-travel/tests/test_live_loopback_e2e.py", "prefix": null}, {"domain": null, "path": "projects/woodblock-heritage/README.md", "prefix": null}, {"domain": null, "path": "projects/woodblock-heritage/docs/ARCHITECTURE.md", "prefix": null}, {"domain": null, "path": "projects/woodblock-heritage/docs/TECH-STACK.md", "prefix": null}], "skipped_layers": {}}
```

说明（契约第 0 条要求的两句 + 复核）：

- `head` = `1aee907de9f6245877fe03ce77fc24afb7e3f767`，为**运行 suite-scope 时的 HEAD**；本报告在其后提交（本 implementer 不执行 commit，故该值保持为运行时 HEAD，供 `sdflow-done` verify 重跑比对）。**未**把 `head` 改成报告提交 SHA。
- `layers` 为空（`{}`）的原因：**`openspec/config.yaml` 未配置 `test-suites`**——`test-suites.domains` 键缺席 ⇒ `domains_configured=false`、`hit_domains=[]`、`layers={}`、`skipped_layers={}`，`mapping[]` 每项仍含 `path`/`domain`/`prefix` 三键（`domain`/`prefix` 恒为 `null`，字段未省略）。依据：**「聚合套件发现契约」第 0 条**（`C:/Users/Lenovo/.agents/skills/sdflow-implement/SKILL.md` 的「聚合套件发现契约」第 0 条：层集合 SHALL 由 `suite-scope` 产出；`layers` 为空时写一句原因并注明依据本条）。
- 复核依据：`openspec/config.yaml` **无活动的 `test-suites` 键**——锚定命令 `Select-String -Pattern '^test-suites:' openspec/config.yaml` 实测**无任何输出（无命中）**；易误判的 `Select-String -SimpleMatch "test-suites"` 则**命中 4 行、全部是注释**（L100 契约说明注释、L106/L113/L127 被注释掉的示例 `# test-suites:`），不构成配置。确定性依据还有 `suite-scope` 自身输出的 `domains_configured=false` / `layers={}`。本仓唯一测试配置是根级 `pytest.ini`（`testpaths = tests`、`python_files = test_*.py`、`addopts = -p no:cacheprovider`），无 unit/integration/e2e 分层 runner。

## 1. 命令来源：`layers` 为空后的回退与依据

契约第 1 条来源优先级 ① 无可用层（`layers={}`，无任何层命令）；故按 ② 由本票 implementer 依**仓内既有约定**判定，并写明命令原文与依据（通则①：不凭记忆）。下表是**仓内约定命令本身**；实际执行时按契约第 8 条在其环境前注入 `SDFLOW_DIFF_BASE=6a785607e4bdb52e6c1af95e7b7b585d1b5d035b`（见 §2 的实跑命令原文）。

| 用途 | 命令原文 | 依据（仓内既有约定，均已打开核对） |
|---|---|---|
| 完整离线回归 | `C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider` | `README.md:18-25`「跑测试」逐字同命令；`docs/ACCEPTANCE.md` §2/§8/§10.2 与 `docs/LIVE-AMAP.md` §7 同一命令；根级 `pytest.ini` 固定 `testpaths = tests` + `addopts = -p no:cacheprovider` |
| 独立进程 loopback | `C:/Miniconda3/python.exe scripts/live_loopback_e2e.py` | `docs/LIVE-AMAP.md` §6.8、`docs/ACCEPTANCE.md` §10.2、`README.md:41` 逐字同命令；脚本自身启动独立 uvicorn 子进程（`127.0.0.1:0`） |
| loopback pytest 包装 | `C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider tests/test_live_loopback_e2e.py` | `tests/test_live_loopback_e2e.py` 是上述脚本的 pytest 包装；`docs/ACCEPTANCE.md` §10.2 把该文件计入 93 passed 子套件 |

> 环境差异说明（如实记录）：本次三条命令**未在 shell 里** `set TRAVEL_REPLAY_NO_AUTOSTART`（`README.md:20-22` 的「跑测试」节含 `set TRAVEL_REPLAY_NO_AUTOSTART=1`，`docs/ACCEPTANCE.md` §10.2 记录的命令形态不带该变量）；但 `tests/conftest.py:14` 对**全部** pytest 测试**无条件**执行 `os.environ["TRAVEL_REPLAY_NO_AUTOSTART"] = "1"`（第 15 行另设 `TRAVEL_REPLAY_DB`），独立脚本也在自己的子进程里设同名变量（`scripts/live_loopback_e2e.py:66`），故两者**行为等价**。本次全量 154 passed，与 §10.2 记录一致，无测试因缺该变量而失败或跳过。

## 2. 逐层证据（schema：`<层> | <命令原文> | <退出码> | <实际用例数> | <测试时 git rev-parse HEAD>`）

> 前缀注入（契约第 8 条）：三条层命令执行时均以 `SDFLOW_DIFF_BASE=<第 0 条输出的 base>` 注入环境，即 `SDFLOW_DIFF_BASE=6a785607e4bdb52e6c1af95e7b7b585d1b5d035b`。PowerShell 不支持 `VAR=value cmd` 内联前缀，故用 `$env:SDFLOW_DIFF_BASE='…';` 赋值实现同一环境注入（命令原文按实跑形式记录）。本仓命令无 `SDFLOW_DIFF_BASE` 消费者 ⇒ 对结果 no-op；表内数字为注入后 r1 重跑的真实输出。

| 层 | 命令原文 | 退出码 | 实际用例数 | 测试时 HEAD |
|---|---|---|---|---|
| 聚合离线回归（全仓 pytest；`layers={}` 后按仓内既有约定回退） | `$env:SDFLOW_DIFF_BASE=6a785607e4bdb52e6c1af95e7b7b585d1b5d035b; C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider` | 0 | 154 | `1aee907de9f6245877fe03ce77fc24afb7e3f767` |
| 独立进程 loopback（脚本，输出 `E2E_OK`） | `$env:SDFLOW_DIFF_BASE=6a785607e4bdb52e6c1af95e7b7b585d1b5d035b; C:/Miniconda3/python.exe scripts/live_loopback_e2e.py` | 0 | 2 场景（脚本内 `create` / `revision`；非 pytest runner 汇总，见注） | `1aee907de9f6245877fe03ce77fc24afb7e3f767` |
| 独立进程 loopback（pytest 包装） | `$env:SDFLOW_DIFF_BASE=6a785607e4bdb52e6c1af95e7b7b585d1b5d035b; C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider tests/test_live_loopback_e2e.py` | 0 | 1 | `1aee907de9f6245877fe03ce77fc24afb7e3f767` |
| unit（未配置层） | — | 未覆盖 | 依据：`suite-scope` 的 `layers={}`；`openspec/config.yaml` 无 `test-suites`；`pytest.ini` 仅单一 `testpaths = tests`，本仓无独立 unit 层 runner。该层实际覆盖由「聚合离线回归」行承担 |
| integration（未配置层） | — | 未覆盖 | 依据同上；本仓无独立 integration runner，集成面（SQLite/幂等/取消/恢复）由「聚合离线回归」行覆盖 |
| e2e（未配置层） | — | 未覆盖 | 依据同上；本仓无分层 e2e runner，进程内与独立进程 loopback 由上面两行覆盖 |

**脚本行「用例数」口径注**：独立脚本不是 pytest runner，没有「N passed」汇总行；它自身打印可机读 JSON 汇总，含 `create`、`revision` 两个场景，每个场景内有逐项断言（状态/预算/事件/DB/发送与关闭次数），退出码 0 且输出 `E2E_OK`。故按**实际执行的场景数 2** 记录并注明非 runner 汇总；pytest 包装行（1 个用例）是同一脚本的 runner 化口径，两者互为旁证。

`--collect-only` 收集总数 = **154**，与实跑 `154 passed` 相等 ⇒ 本次无 deselected / skipped / xfail 造成的计数缺口；0 failed。两条 warning 均为 `websockets`/`uvicorn` 的 legacy `DeprecationWarning`（见 §2.1，`docs/ACCEPTANCE.md` §10.2 已记录为与改动无关）。

### 2.1 真实运行输出（逐字，exit 单独记录）

（1）聚合离线回归 `$env:SDFLOW_DIFF_BASE=6a785607e4bdb52e6c1af95e7b7b585d1b5d035b; C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider` → **exit 0**（r1，注入后重跑）

```text
........................................................................ [ 46%]
........................................................................ [ 93%]
..........                                                               [100%]
============================== warnings summary ===============================
tests/test_live_deadline_cancel.py::test_api_create_replay_then_cancel_stops_next_handler
  C:\Miniconda3\Lib\site-packages\websockets\legacy\__init__.py:6: DeprecationWarning: websockets.legacy is deprecated; see https://websockets.readthedocs.io/en/stable/howto/upgrade.html for upgrade instructions
    warnings.warn(  # deprecated in 14.0 - 2024-11-09
tests/test_live_deadline_cancel.py::test_api_create_replay_then_cancel_stops_next_handler
  C:\Miniconda3\Lib\site-packages\uvicorn\protocols\websockets\websockets_impl.py:17: DeprecationWarning: websockets.server.WebSocketServerProtocol is deprecated
    from websockets.server import WebSocketServerProtocol
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
154 passed, 2 warnings in 38.35s
```

（2）独立进程 loopback `$env:SDFLOW_DIFF_BASE=6a785607e4bdb52e6c1af95e7b7b585d1b5d035b; C:/Miniconda3/python.exe scripts/live_loopback_e2e.py` → **exit 0**（r1，注入后重跑）

```text
{"create": {"close_attempts": 1, "run_id": "run_4b47827fdd3e4fef", "scenario": "create", "status": "cancelled", "tool_calls": 3, "transport_sends": 3}, "revision": {"child_run_id": "run_97cc300793ee4e61", "child_tool_calls": 3, "close_attempts": 2, "parent_run_id": "run_4fe6ba400718402f", "parent_status": "needs_input", "scenario": "revision", "transport_sends": [11, 3]}, "scope": "independent-process loopback; real AmapAdapter + MockTransport; synthetic key; no real provider"}
E2E_OK
```

> 该次运行的 `run_id`/`child_run_id` 是真实新建的一次性值，不是预写常量；脚本成功后删除自己的临时工作目录。

（3）loopback pytest 包装 `$env:SDFLOW_DIFF_BASE=6a785607e4bdb52e6c1af95e7b7b585d1b5d035b; C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider tests/test_live_loopback_e2e.py` → **exit 0**（r1，注入后重跑）

```text
.                                                                        [100%]
1 passed in 10.72s
```

### 2.2 覆盖映射（收集数，非执行数；合计与实跑 154 一致）

| 测试文件 | collect-only 收集数 | 覆盖面（据文件名 + `docs/ACCEPTANCE.md` §2/§10.3、`docs/LIVE-AMAP.md` §7 已读描述） |
|---|---:|---|
| `tests/test_domain.py` | 24 | 回放领域：字段/时区/DST、未匹配与跨城、时间线/重排/null 传播 |
| `tests/test_fixtures.py` | 7 | 20 冻结场景分组、请求合法性、期望矩阵、修订场景 |
| `tests/test_worker.py` | 13 | 重启恢复、工具/时间预算、歧义、格式错误、时间冲突、取消不可复活 |
| `tests/test_api.py` | 17 | 健康/UI/校验/404·409/创建轮询/幂等/修订/取消/全场景可达 |
| `tests/test_live.py` | 13 | LIVE API：成功、歧义、供应商错误、跨城、无 Key 503、幂等重放/冲突 |
| `tests/test_amap_tools.py` | 14 | Amap 离线契约：唯一匹配/同名歧义/空结果/Key 回收/超时/坏坐标/天气覆盖/路线/营业时间 |
| `tests/test_live_admission.py` | 23 | 发送前 HTTP 准入（limit 0/1/2/40）、真实计数、批次中断保留子证据、绑定/关闭闭环 |
| `tests/test_live_deadline_cancel.py` | 23 | 单调 deadline 与四操作 timeout、UTC 跳变、探针异常、晚到结果拒绝、API 取消与原子终态 |
| `tests/test_live_cleanup_redaction.py` | 19 | 六类出口清理尝试、拥有权/借入解绑、清理失败保主结果、凭据与 URL 脱敏扫描 |
| `tests/test_live_loopback_e2e.py` | 1 | 独立进程 loopback 的 pytest 包装 |
| **合计** | **154** | 与全量实跑 `154 passed` 相等 |

## 3. 失败分诊

三条命令退出码均为 `0`，**无失败用例**，故四类分诊（① 本 change 回归 ② 既有红测用 base `6a78560` 复跑 ③ flaky ④ 环境）**未触发**，也未发生「先修后报」的需求。`## 既有红测` 小节按契约「无既有红测可省略该小节」省略（本次没有失败命令需要在 base 上复跑）。

## 4. 未运行 / 未验证范围（真实保留，不因全绿外推）

- **真实高德供应商**：未提供、未使用真实 Key；三条命令全程只用合成 Key `synthetic-example` + `httpx.MockTransport`，未发出真实网络请求。因此真实 POI/天气/路线数据、配额/QPS、计费与效果均**未验证**。
- **真实 loopback 已验，但不是公网/生产并发**：独立进程 loopback 只连 `127.0.0.1`，单进程 + Starlette 线程池；不构成生产并发容量、多实例或吞吐承诺。
- **硬中断 / 90 秒强制返回**：未验证。deadline 是协作式的——只保证在可观察边界后停止新请求并拒绝晚结果，不保证挂起的同步调用在 90 秒内被强制返回或撤回（`docs/LIVE-AMAP.md` §6.5）。
- **断电 / 崩溃恢复与逐 HTTP 账本**：未验证（进程崩溃前未落库的计数未知；T12 另跟踪）。
- **灾备 / 备份恢复**：未验证（本仓单进程 SQLite，无灾备演练）。
- **外部日志采集 / APM / 指标平台**：未验证（本 change 不建指标平台；仅复用 run/budget/issues/事件）。
- **UI / 浏览器 E2E**：本票未运行；`docs/ACCEPTANCE.md` §5/§6 另有历史 Chrome CDP 记录，但不在本票证据内。
- **提交/合并/评审状态**：未 commit、未 push、未 merge、未 archive、未独立代码审；**不宣称 T11 完成**。

## 5. 结论

- `suite-scope` 已起手运行（工作树模式，exit 0），JSON 原样落于 §0；`base=6a78560…`、`head=1aee907…`、`domains_configured=false`、`hit_domains=[]`、`layers={}`、`skipped_layers={}`。
- `layers` 为空已按契约第 0 条写明原因（config 未配置 `test-suites`）与依据；三条命令按契约第 1 条 ② 的仓内既有约定回退，命令原文与依据见 §1。
- 三条命令实跑 **exit 0**，实际用例数 **154 / 2 场景 / 1**，**均 > 0**（无 ZERO-RUN）；完整离线回归覆盖 replay、Amap 离线、LIVE、准入、deadline/取消、清理/脱敏与 loopback 包装（§2.2）。（r1 已按契约第 8 条注入 `SDFLOW_DIFF_BASE` 重跑三条命令，结果不变，见 §2 与 §7。）
- 未发现本 change 回归；本票**未改动任何产品代码**（§6）。
- **不宣称**：T11 完成、已合并 main、真实高德供应商已验、生产并发/硬中断/灾备已验、业务效果验收通过。

## 6. 工作树自证（未改产品代码）

测试后 `git status --porcelain`（仓库根为 `D:/workspace-dsh/tmp/sbu-travel-runtime-budget`）：

```text
?? projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task4-aggregate.md
?? projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task4-brief.md
?? projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task4-spec-r1.json
?? projects/local-life-travel/openspec/changes/travel-runtime-budget/impl-reports/task4-standards-r1.json
?? projects/local-life-travel/openspec/changes/travel-runtime-budget/review/task4-dispatch.json
?? projects/local-life-travel/openspec/changes/travel-runtime-budget/review/task4-shared-context.md
```

以上均为未跟踪文件：5 个是编排层下发的本票输入/复审产物（`task4-brief.md`、`task4-dispatch.json`、`task4-shared-context.md`、`task4-spec-r1.json`、`task4-standards-r1.json`），1 个是本报告自身。**已跟踪文件无改动**：`git diff --stat` 与 `git diff --cached --stat` 均为空，`git status -- docs/` 为空。`app/`、`tests/`、`docs/`、design/specs/tickets 与复选框**未改**；未 `git add`、未 commit、未 push/merge/reset、未打 checkpoint 标签、未访问真实供应商、未派子代理。

## 7. 复审修订（r1）

> 来源：`task4-spec-r1` 复审（verdict=pass，4 条 findings：F1 medium / F2 low / F3 low / F4 low）。
> 本节修订**只动本报告**；未改 `app/`、`tests/`、`design/specs/tickets/复选框`；**`docs/` 未改**（F4 见下，受本票约束阻塞并上报）。

### F1（medium）suite-scope 复核句不成立 → 已改正

- **原句（r0，已作废）**：「`openspec/config.yaml` 不含 `test-suites` 键（`Select-String -SimpleMatch "test-suites"` 无命中）」。
- **事实（r1 实测）**：`Select-String -SimpleMatch "test-suites"` 命中 **4 行，全部是注释**——L100（契约说明注释）、L106/L113/L127（被注释掉的示例 `# test-suites:`）。r0 那条命令实际写的是 `-SimpleMatch "test-suites|domains"`，`|` 被当作字面量，于是被误读成「无命中」。
- **已改（§0 复核依据）**：改用锚定命令 `Select-String -Pattern '^test-suites:' openspec/config.yaml`，实测**无任何输出（无命中）**；并写明「有 4 处注释命中、无活动键」；同时引用 `suite-scope` 的 `domains_configured=false` / `layers={}` 作确定性依据。**结论（config 未配置 `test-suites`）不变。**

### F2（low）`SDFLOW_DIFF_BASE` 前缀注入 → 已补注入并重跑

- **契约**：「聚合套件发现契约」第 8 条——层命令执行时 MUST 以 `SDFLOW_DIFF_BASE=<第 0 条输出的 base>` 前缀注入，供有影响面原语的项目自用；**无消费者时为 no-op**。
- **r1 做法**：以 `$env:SDFLOW_DIFF_BASE='6a785607e4bdb52e6c1af95e7b7b585d1b5d035b'` 注入后**重跑全部三条命令**（PowerShell 无 `VAR=value cmd` 内联语法，`$env:` 赋值 = 同一环境注入）。本仓命令无该变量消费者，预期 no-op；实测结果不变。
- **r1 重跑结果（取代 r0）**：
  - 全量 pytest：`154 passed, 2 warnings in 38.35s`，exit 0，HEAD `1aee907…`（r0：38.55s）
  - loopback 脚本：`E2E_OK`，exit 0，HEAD `1aee907…`；本次 `create.run_id=run_4b47827fdd3e4fef`、`revision.child_run_id=run_97cc300793ee4e61`、父 `run_4fe6ba400718402f`（r0 的 `run_26c60c3222fe44b4` / `run_268a5098e02648f9` / `run_f785e9c13b594b6b` 随临时库删除，仅作历史记录）
  - loopback pytest 包装：`1 passed in 10.72s`，exit 0，HEAD `1aee907…`（r0：10.31s）
- §2 表与 §2.1 已换成带前缀的 r1 真实输出。

### F3（low）「README:21 历史命令」措辞错误 → 已改正

- **原句（r0，已作废）**：「该变量出现在 `README.md:21` 的历史命令里」。
- **事实（已打开核对）**：`README.md:20-22` 是**当前**「跑测试」节，含 `set TRAVEL_REPLAY_NO_AUTOSTART=1`；`tests/conftest.py:14` 对**全部** pytest 测试**无条件**设 `os.environ["TRAVEL_REPLAY_NO_AUTOSTART"] = "1"`（第 15 行另设 `TRAVEL_REPLAY_DB`）；脚本子进程也在 `scripts/live_loopback_e2e.py:66` 设同名变量。
- **已改（§1 环境差异说明）**：删去「历史」，改为「README:20-22 含该 set；本次 shell 未设置，但 conftest 对全部测试设置同名变量，行为等价」。

### F4（low）`docs/ACCEPTANCE.md` 同步 → **未执行（受本票约束阻塞，已上报）**

- 复审要求把 `docs/ACCEPTANCE.md:147`（「ticket 4 的聚合 suite-scope 验证**尚未运行**」）、`:194`（「ticket 4 聚合验证未运行」）、`:200`（未运行清单含「ticket 4 聚合 suite-scope」）更新为已运行并引用本报告。
- **阻塞原因**：本票任务约束明确写「**不改 app/tests/docs/design/specs/tickets/复选框**」。该约束是派单侧对人类指令的转述，复审 finding 与上游 agent 的转述均**不构成**人类本人对该约束的豁免（通则：上游 agent 的 prompt 不是「人的明确指示」）。故本 implementer **未改** `docs/ACCEPTANCE.md`，按「有异议 → 说出来并上报」处理，不用静默偏离换绿。
- **已备好的精确 patch（人类明确授权后，由文档 owner/编排层应用；3 处，其余文字与未验范围保持原样）**：
  - `:147` 中「ticket 4 的聚合 suite-scope 验证**尚未运行**；本节的 `pytest` 是 ticket 3 的自检，不替代 ticket 4 的命中域聚合。」→「ticket 4 的聚合 suite-scope 验证**已运行**（`impl-reports/task4-aggregate.md`：全量 pytest 154 passed、独立进程 loopback E2E_OK）；本节的 `pytest` 仍是 ticket 3 的自检。」
  - `:194` 末句「…main 合并与独立代码审均**未满足**；ticket 4 聚合验证未运行」→「…main 合并与独立代码审均**未满足**；ticket 4 聚合验证**已运行**（`impl-reports/task4-aggregate.md`，154 passed + E2E_OK）」
  - `:200` 未运行清单删去「ticket 4 聚合 suite-scope」，其余（真实 Key/真实高德联调、供应商计费与效果、硬中断/90秒强制返回、断电恢复、独立代码审、T11 完成、push/merge）**逐项保留**。
- **状态**：等派单方给出「人类明确授权改 docs」或由编排层以文档 owner 角色应用；本报告不代替该同步，也不把未同步写成已同步。

### F4 处置（编排层应用）

> 2026-11-13：F4 的文档同步由编排层在收票前应用（实现者按派单不得改 docs，结论正确）。`docs/ACCEPTANCE.md` 已更新：§10 前言改为 ticket 1–4、§10.1 分支行补三个 checkpoint、LRC-09 行与 §10.4 未运行清单移除“ticket 4 未运行”。真实高德/硬中断/断电恢复/独立代码审/T11/合并仍未验，保持未满足。
