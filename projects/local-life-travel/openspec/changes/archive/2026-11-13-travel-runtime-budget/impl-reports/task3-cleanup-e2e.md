<!-- prefix-version: principles-b9a054bafa9c -->
DONE — 票3（六类出口清理、解绑/关闭异常与主结果保留、允许列表脱敏、独立进程 loopback、最终材料互链）已交付；全量 `154 passed`（exit 0），loopback 脚本 `E2E_OK`（exit 0）；改动未提交、未打 checkpoint、未勾票；真实供应商未联调、未独立代码审（Known concerns 见 §10）。

# Task 3 实现报告：异常资源收尾、脱敏与独立进程 loopback 验收

## 0. 回执与身份

前缀文件：`openspec/changes/travel-runtime-budget/.outside-voice/20261110T182434Z-impl-N2Sw5e/prefix-principles.md`

```text
<!-- prefix-version: principles-b9a054bafa9c -->
```

- run_id：`20261110T182434Z-impl-N2Sw5e`
- task_id：`task3-implementer`
- role：fresh implementer；**未派子代理**，未使用 `subagent` / `subagent_fork` / `workflow`
- native HOST：unknown（未伪造宿主；按真人已批准的设计与 DSH 运行适配执行，未重问批准）
- 本票 R-ID：LRC-01..09（票1/2 已交付部分引用真实测试，不重复实现）
- 起点：`03cb0d4`（`checkpoint(travel-runtime-budget:task2-deadline-cancel)`，票1/2 已验收）
- 未触碰：design.md / specs / tasks.md / tickets.md / 票复选框 / 真人门记录 / `docs/interview-v0.1.md`；未 push / merge / reset；未打 `checkpoint(travel-runtime-budget:task3-...)`；未 `git add -A`；未访问真实供应商
- 权限边界：delegated subagent，无法扩权；未请求 sandbox 升级

## 1. 起点与范围

工作树起点 `03cb0d4`，tracked 干净（仅编排器派发的 `task3-brief.md`、`review/task3-*` 未跟踪文件）。先跑起点全量：

```text
C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider
→ 134 passed, 2 warnings in 19.44s   (exit 0)
```

范围按票3原文：3.1 六类出口与清理可观察、3.2 清理异常/主结果保留/脱敏、3.4 独立进程 loopback、3.5 最终材料与 LRC 证据。**3.3 全量聚合回归按计划留给唯一票4**；本报告的全量 pytest 只是本票完成自检，不冒充票4的 suite-scope 聚合，也不以票4命令替代本票测试。

## 2. 改动文件

| 文件 | 改动 |
|---|---|
| `app/amap_tools.py`（改） | `AmapClient.get` 改为允许列表脱敏：`httpx.HTTPError` 只留固定类别 + 异常类型名（不再 `str(exc)`，不再带 query URL）；provider 分支不回显 `info`，只保留通过 `[0-9]{1,8}` 校验的 `infocode`；`AmapClient.release` 抽出可注入的 `_detach_locked` 短锁步骤，解绑抛错时仍对**本 run 仍持有**的自有 client 独立尝试物理 close，身份不符则绝不关闭另一个 active run 的 client |
| `app/live.py`（改） | `RESOURCE_CLEANUP_FAILED` warning 文案固定为“资源清理尝试失败（<安全异常类型>）；资源是否释放未知”，不宣称已释放 |
| `tests/test_live_cleanup_redaction.py`（新增，19 项） | 六类出口清理、构造校验失败与 close 幂等、factory 未交出资源、借入 close 0 + 顺序复用、解绑失败仍物理 close、cleanup 失败保留主类别/准确预算/证据、close 敏感文本 + 清理期间 deadline 的 Review Focus、无更早主失败时清理后仍拒绝过期终态、HTTPError/provider info/顶层异常/探针/cleanup 的合成 Key/query/私人标记扫描（API、state、events、SQLite 行） |
| `scripts/live_loopback_e2e.py`（新增） | 独立子进程 uvicorn（127.0.0.1:0，端口 stdout 握手）、真实 `AmapAdapter` + `MockTransport` 合成供应商、显式合成 Key；创建与 LIVE 修订两场景的并发 POST/同键重放/真实 cancel API/GET；核对 HTTP、send/close 日志与 SQLite；只停止自己启动的子进程 |
| `tests/test_live_loopback_e2e.py`（新增，1 项） | 以子进程运行上述脚本，断言 `E2E_OK`、exit 0、无 Traceback、汇总含真实计数 |
| `docs/LIVE-AMAP.md`（改） | 状态行；新增 6.7 异常收尾/脱敏契约、6.8 独立进程 loopback；测试命令/真实计数；互链验收记录与实施记录；明确分支≠main |
| `docs/ACCEPTANCE.md`（改） | 历史计数标注；新增第 10 节：实际命令/exit/计数、LRC-01..09 逐条证据/未满足项、失败/跳过/未运行、分支与 T11 状态 |
| `docs/IMPLEMENTATION.md`、`docs/TECH-STACK.md`、`README.md`（改） | LIVE API 行/5.1/预算口径更新；测试命令不再写历史 88；README 索引加入 3 份实施报告与 LRC 验收记录；互链 LIVE-AMAP/ACCEPTANCE |

`git diff --stat`（tracked）：7 files changed, 166 insertions(+), 34 deletions(-)；另有 4 个新增未跟踪文件（2 tests、1 script、本报告）。

## 3. 3.1 拥有权覆盖所有出口

### 3.1.1 六类出口各有一次清理尝试

全部用**真实 `AmapAdapter` + `httpx.MockTransport`** 经 `TestClient` 走同一 `create_live_run` 路径；观测点是 transport 的物理 `close_attempts`，不是日志文字：

| 出口 | 测试 | 实测断言 |
|---|---|---|
| success | `test_success_exit_closes_owned_client_once` | `completed`；`tool_calls == sent == 15`；`close_attempts == 1`；`client._state == "closed"` |
| provider_error | `test_provider_error_exit_closes_owned_client_once` | `failed`；`budget.status=failed`；`tool_calls=1`；`TOOL_PROVIDER_ERROR`；`close_attempts=1` |
| call_limit | `test_call_limit_exit_closes_owned_client_once` | `failed/exhausted/call_limit`；`tool_calls == sent == 1`；`close_attempts=1` |
| deadline | `test_deadline_exit_closes_owned_client_once` | 首次发送后时钟 +91；`failed/exhausted/deadline`；`tool_calls=1`；`close_attempts=1` |
| cancel | `test_cancel_exit_closes_owned_client_once` | 首次发送后持久状态取消；`cancelled/cancelled/unverified/null`；`tool_calls=1`；`close_attempts=1` |
| constructor_failure | `test_constructor_validation_failure_closes_owned_client_and_is_idempotent` | 非法 transport 的 `AmapAdapter` 在返回前关闭自有 client；`STAGE_EXECUTION_ERROR`、`tool_calls=0`、`sent=[]`、`close_attempts=1`；再次 `client.close()` 仍为 1（幂等） |

### 3.1.2 factory 返回前失败 / 借入资源

- `test_factory_failure_before_return_owns_its_unreturned_resources`：factory 创建 client 后、返回 adapter 前抛错，由 factory 自己在 `finally` 关闭；顶层只看到执行错误，`tool_calls=0`、`sent=[]`、物理关闭恰好 1 次（顶层没有二次关闭未知对象），异常原文（含合成 Key/query/私人标记）不入 API。
- `test_borrowed_client_is_not_closed_and_reused_sequentially`：同一借入 client 顺序跑两个 run 均 `completed`，`close_attempts=0`、client 仍 `open`、`client.calls=30`；原拥有者再关闭时 `close_attempts=1`。票1的 adapter 级借用证书见 `tests/test_live_admission.py::test_borrowed_client_unbinds_for_sequential_runs_without_close`。
- 绑定失败不清理原 owner（票1已验收，仍绿）：`test_reentrant_factory_object_failure_does_not_clean_active_owner`、`test_two_failed_binds_then_cleanups_leave_owner_client_open`。

## 4. 3.2 清理异常、主结果保留与脱敏

### 4.1 解绑失败仍独立尝试物理 close

实现：`AmapClient.release` 在短锁内调用 `_detach_locked`（身份核对 + 解绑 + closing 转换）；若该步骤抛错且 client 仍是本 run 的 open 绑定，则仍置 `closing`、在锁外**独立尝试** `self._client.close()`，最后重新抛出解绑错误。身份不符时不做该转换/关闭，保持 COLD-004“不关闭另一个 active run 的 client”。

证据：`UnbindFailingClient._detach_locked` 抛含合成 Key/query/私人标记的 `RuntimeError`；`test_unbind_failure_still_attempts_physical_close_and_keeps_result` 断言 `unbind_failures=1`、`close_attempts=1`、主结果仍 `completed`、一条 `RESOURCE_CLEANUP_FAILED` warning（含 `RuntimeError`、不含敏感文本），DB 重读仍有该 warning。

### 4.2 cleanup 失败保留原主类别/准确预算/证据，不跳过保存

| 场景 | 测试 | 断言 |
|---|---|---|
| provider_error + close 抛错 | `test_cleanup_failure_preserves_primary_provider_failure_and_budget` | `failed` + `budget.status=failed`、无 `exhaustion_reason`、`tool_calls=1`、`TOOL_PROVIDER_ERROR` 与 `RESOURCE_CLEANUP_FAILED` 并存；warning 仅含 `OSError`/“未知”，不含“已释放”；DB 重读一致；`LIVE_FINISHED` 事件含 `status=failed` |
| call_limit + close 抛错 | `test_cleanup_failure_preserves_call_limit_category_and_exact_count` | `failed/exhausted/call_limit`、`tool_calls == sent == 1`、`BUDGET_EXHAUSTED` + cleanup warning，`close_attempts=1` |
| 直接 `create_live_run`（不经 HTTP） | `test_direct_create_live_run_saves_after_cleanup_failure` | close 抛错后仍 `completed` 落盘、15 次发送对账、cleanup warning 存在、DB 无敏感文本 |
| 无更早主失败 + 清理越过 deadline | `test_cleanup_past_deadline_still_rejects_stale_success_terminal` | 业务已成功但 close 把时钟推过 90 秒：最终仍 `failed/exhausted/deadline`、`result=null`、`unverified`、实际计数/证据保留，`close_attempts=1` |

### 4.3 [Review Focus] close 含敏感文本 + 总 deadline 在清理期间到达

`test_close_error_with_deadline_during_cleanup_keeps_earlier_failure`：先 provider_error，随后 close 抛 `OSError("... /v3/geocode/geo?key=SECRET-KEY-7f3a&private=PRIVATE-PARAM")` 并把时钟推过 90。断言：`failed` + `budget.status=failed`（原主失败保留）、无 `exhaustion_reason`、`tool_calls=1`、`elapsed_seconds>=90`、issues 同时含 `TOOL_PROVIDER_ERROR` 与 `RESOURCE_CLEANUP_FAILED` 且**不含** `BUDGET_EXHAUSTED`；warning 以“资源是否释放未知”结尾；API/DB/事件均不含合成 Key/query/私人标记；`LIVE_FINISHED` 为 `status=failed`；`close_attempts=1`——不把一次 close 尝试写成“已释放”。

### 4.4 允许列表脱敏（改实现，不是只改测试）

- HTTPError：`AmapClient.get` 返回 `Amap transport error (<ExcType>)`，不拼 `str(exc)`；httpx 异常原文常含完整请求 URL（query 里有 Key）。
- provider：只回显 `provider error (infocode <数字>)`；`info` 永不出现；非纯数字 infocode（如 `10013-PRIVATE...`）被丢弃，消息退化为 `provider error`。既有 `tests/test_amap_tools.py::test_recycled_key_is_provider_error` 仍断言 `10013` 在消息中（数字码保留）。
- 顶层执行异常：沿用票2的 `type(exc).__name__`；取消探针：固定分类 + 安全异常类型。
- cleanup：只保留 `type(exc).__name__` 与“未知”声明。

注入与扫描（`_assert_no_secrets` 同时扫 API 响应 JSON、DB 重读 JSON、`runs`/`events` 原始 SQLite 行，标记含 `SECRET-KEY-7f3a`、`/v3/geocode/geo?key=...&private=...`、`PRIVATE-MARKER-9c1d`）：

| 注入点 | 测试 | 状态分类保持 |
|---|---|---|
| 普通 HTTPError | `test_httpx_error_text_is_reduced_to_safe_category_and_type` | `failed`，issue `TOOL_PROVIDER_ERROR`，消息含 `ConnectError`，计数 1 |
| provider info/带 query | `test_provider_info_is_not_echoed_but_numeric_infocode_is_kept` | `TOOL_PROVIDER_ERROR`；合法 `10013` 保留，非法码不保留 |
| 顶层执行异常 | `test_top_level_execution_exception_text_is_not_persisted` | `STAGE_EXECUTION_ERROR`、`tool_calls=0`、close 1 |
| 取消探针异常 | `test_cancel_probe_failure_does_not_leak_raw_exception` | `STAGE_EXECUTION_ERROR`，消息含 `CANCEL_PROBE_READ_FAILED`/`RuntimeError`，factory 0 次 |
| cleanup 异常 | `test_cleanup_exception_text_is_not_persisted` | 主结果 `completed` + cleanup warning，消息仅 `OSError`/未知 |

## 5. 3.4 独立进程 loopback

`scripts/live_loopback_e2e.py`：

- 父进程 `subprocess.Popen([sys.executable, __file__, "--serve", ...])` 启动**独立应用进程**；子进程 uvicorn 绑定 `127.0.0.1:0`，从 stdout 打印实际端口，父进程握手读取（不假设端口空闲、不扫描端口）。
- 子进程 `create_app(live_adapter_factory=factory)`，factory 构造真实 `AmapAdapter(AmapClient(key="synthetic-example", transport=SyntheticProvider()), owns_client=True)`；`SyntheticProvider` 是 `httpx.MockTransport`，断言每个请求的 `key=="synthetic-example"`，不访问真实渠道。子进程启动时显式把 `AMAP_API_KEY` 设为合成值；即使父环境有真实 Key，也不会被使用。pytest 包装测试还故意在环境里放 `AMAP_API_KEY="real-key-must-not-be-used"` 哨兵，脚本仍 `E2E_OK` 且输出不含哨兵。
- 并发与取消：原 POST 在传输层被文件门闩阻塞 → 父进程用同键同载荷重放取得 run_id、用**真实 HTTP cancel 入口**取消、多次 GET → 释放门闩 → 原 POST 返回 canonical 取消态。修订场景先让父 run `needs_input`，再对修订 POST 做同样流程。取消不直接写 DB。
- 核对：HTTP 响应与 SQLite 的 run 状态、`budget.tool_calls`、`tool_results`、`CANCELLED`/`LIVE_FINISHED` 事件一致；子进程 JSONL 的 factory/send/close 次数与响应、DB 对账；取消后下一次 handler 不命中；LIVE 取消文案准确。
- 收尾：只向自己启动的子进程写 shutdown 并 join；超时才 kill 该 PID。成功时删除临时目录，失败保留并打印路径。
- 本机 `NO_PROXY` 含 `[::1]` 会让默认 `AmapClient()`（无 transport、`trust_env` 默认）在代理解析时 `InvalidURL: Invalid port ':1]'`；脚本用 127.0.0.1 + `trust_env=False` + MockTransport 规避，**未改全局环境**，也不把此规避说成生产修复。

实测输出（2026-11-13，exit 0）：

```text
{"create": {"close_attempts": 1, "run_id": "run_e8324d12ccc349c7", "scenario": "create",
            "status": "cancelled", "tool_calls": 3, "transport_sends": 3},
 "revision": {"child_run_id": "run_cf23b20bbdb04a51", "child_tool_calls": 3,
              "close_attempts": 2, "parent_run_id": "run_1384d45dd0774a44",
              "parent_status": "needs_input", "scenario": "revision",
              "transport_sends": [11, 3]},
 "scope": "independent-process loopback; real AmapAdapter + MockTransport; synthetic key; no real provider"}
E2E_OK
```

`tests/test_live_loopback_e2e.py` 以子进程包装该脚本，断言 exit 0 / `E2E_OK` / 无 Traceback，纳入全量回归。

## 6. 3.5 最终材料

- `docs/ACCEPTANCE.md` 新增第 10 节：分支/状态（`feat/travel-runtime-budget` ≠ main、未独立代码审、未标 T11、私人面试稿未改）、实际命令与计数、**LRC-01..09 逐条证据/未满足项表**、失败/跳过/未运行分列。
- `docs/LIVE-AMAP.md` 新增 6.7/6.8，更新状态行与测试计数，互链验收记录、实施报告、规格/设计；明确真实 Key 未联调、协作式 deadline、无硬中断。
- `README.md` 更新测试命令与真实计数、LIVE 现状段落、文档索引（3 份实施报告 + 验收记录）。
- `docs/IMPLEMENTATION.md` 更新 LIVE API 行、5.1、LIVE 40/90/5 口径；`docs/TECH-STACK.md` 去掉历史 88 的“期望”并互链验收记录。
- `docs/interview-v0.1.md` **未改**；没有把分支结果倒填 main 现状。

## 7. 每个 seam 能抓住 / 漏掉什么

| Seam | 能抓住 | 漏掉 |
|---|---|---|
| 真实适配器 + MockTransport 的六出口矩阵 | 每条出口是否真的调用一次物理 close、计数/状态是否保持；漏掉某出口 close 会红 | 不覆盖真实 socket/供应商行为；close 是否系统级释放不可由计数证明 |
| `_detach_locked` 注入 | 解绑抛错后是否仍尝试物理 close、是否保留主结果、warning 是否只含安全类型 | 需要测试子类注入；身份不符路径故意不 close，外部无法用它证明“任意解绑失败”都 close |
| close 失败 + 注入时钟 | cleanup 异常是否跳过保存、是否覆盖更早主失败、清理越过 deadline 是否拒绝过期终态 | 用假时钟/直接 setattr 制造越界，不证明真实 close 阻塞多久 |
| API/DB/events 敏感文本扫描 | HTTPError/provider/top-level/probe/cleanup 的合成 Key、query URL、私人标记是否进入响应/state/事件/SQLite | 不覆盖外部日志/APM sink；不覆盖未经这些分支的第三方文本 |
| 独立进程 loopback | 跨进程真实 HTTP、端口握手、threadpool 可达取消、进程内日志与 SQLite 对账、停止自己的服务 | 单 uvicorn 进程/单 loopback；不覆盖多 worker/真实网络/OS 调度压力、线程池容量 |

## 8. 红→绿记录（真实输出）

先备份当前实现，临时把 `get()` 脱敏、`release` 解绑回退、cleanup 文案回退到票2行为，再跑同组测试：

```text
C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider tests/test_live_cleanup_redaction.py -k "httpx_error_text or provider_info_is_not_echoed or cleanup_exception_text or unbind_failure"
→ 4 failed, 15 deselected in 1.02s   (exit 1)
```

红态关键断言：

- HTTPError：`assert 'SECRET-KEY-7f3a' not in ...` 失败，旧消息把 `ConnectError: connect failed PRIVATE-MARKER-9c1d /v3/geocode/geo?key=SECRET-KEY-7f3a&private=PRIVATE-PARAM` 写入 ToolResult/issue。
- provider：旧消息回显 `USER_KEY ... /v3/geocode/geo?key=SECRET-KEY-7f3a... (10013)`，同一扫描失败。
- unbind：旧实现没有 `_detach_locked` 注入点，`client.unbind_failures == 0`（期望 1），说明“解绑失败仍 close”没有可观察实现。
- cleanup 文案：`assert '未知' in '资源清理尝试失败：OSError'` 失败（旧文案没有“是否释放未知”）。

恢复实现后同组：

```text
→ 4 passed, 15 deselected in 0.69s   (exit 0)
```

e2e 是新 harness，无“旧实现”可比较；其价值在跨进程集成，红证由票2的 deadline/取消红记录与本节脱敏红记录承担，不把新脚本首次通过写成红→绿。

## 9. 全量验证（真实命令 / exit / 计数）

```text
C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider
→ 154 passed, 2 warnings in 35.81s   (exit 0；墙钟随机器负载变化，计数稳定)

C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider tests/test_amap_tools.py tests/test_live.py tests/test_live_admission.py tests/test_live_deadline_cancel.py tests/test_live_cleanup_redaction.py tests/test_live_loopback_e2e.py
→ 93 passed, 2 warnings in 27.59s    (exit 0；14+13+23+23+19+1)

C:/Miniconda3/python.exe scripts/live_loopback_e2e.py
→ E2E_OK                              (exit 0)
```

构成：134（起点）+ 19（`test_live_cleanup_redaction.py`）+ 1（`test_live_loopback_e2e.py`）。2 条 warning 为 uvicorn 依赖的 websockets legacy DeprecationWarning，与本票改动无关。无测试被删除/skip/xfail，无断言放宽（provider 消息格式变化由 LRC-08 要求，原 “10013” 断言仍绿）。

## 10. Concerns / 已知边界

1. **真实供应商仍未验**：无真实 Key，所有“完成/取消/关闭”只在本机 `MockTransport` 合成供应商下成立；不能外推真实高德数据、计费、配额或效果。
2. **协作式 deadline**：不保证 close/HTTP 在 90 秒内强制返回；本票证明的是边界检查与过期终态拒绝，不是硬中断。
3. **解绑失败注入是白盒 seam**：`_detach_locked` 为可注入保护方法；身份不符（client 属于另一个 active run）时刻意不关闭，符合 COLD-004，但也意味着“任何解绑异常都物理 close”不是无条件承诺。
4. **单进程 loopback**：独立子进程仍是单 uvicorn worker；不证明生产并发、线程池容量、多 worker 或多实例。
5. **本机环境**：`NO_PROXY` 含 `[::1]` 使无 transport 的默认 `AmapClient()` 在本机构造失败；本票只在 e2e/测试里用 127.0.0.1 + `trust_env=False` 规避，**未改生产默认 client**，因此“设置真实 Key 后直接走默认 factory”在本机仍可能受该环境问题影响（票外）。
6. **两次提交非原子**（票2已知）：取消确认与最终保存各是短事务，本票未改变；进程崩溃窗口仍由 T12 另处理。
7. **计数语义**：`tool_calls` 是获准的 HTTP 尝试数，不是供应商收费凭证；e2e 的 send 计数来自合成 transport 日志。
8. **聚合验证留给票4**：本票未运行 ticket 4 的 suite-scope 聚合；全量 154 只是本票完成自检，不能替代“命中域各层”验收。
9. **未提交/未独立审**：改动留在工作区（普通 diff），未打 checkpoint、未勾票；未独立代码审前不标 T11 完成，分支不是 main。

## 11. 票外发现

1. **默认 `AmapClient()` 在本机仍受 `NO_PROXY=[::1]` 影响**（票2已登记，本票只规避测试路径）。若要让本机默认 LIVE factory 可用，需要显式 `trust_env=False` 或修正宿主 `NO_PROXY` 写法；本票按约束未改全局环境、未改生产默认。
2. **LIVE 非幂等创建仍写 “回放运行创建” intake 事件**（`Store.create_run`，票1遗留文案）；本票未改，避免触碰已验收行为。
3. **`worker.last_error` 保留原始异常串**（`app/worker.py:42`）属 replay worker 路径，不在 LIVE LRC-08 的 API/state/事件面；本票未改。
4. **`_record_issue` 会把用户候选名写入 issue message**（`subject`），这是用户请求数据而非异常文本；本票未将其视为泄漏，但若未来要求“私人请求不入事件”，需单独定义。
5. **测试内取消用 `Store.cancel_run`（单元矩阵）而非 HTTP**：仅六出口矩阵中的 cancel 出口为构造确定性状态；e2e 的取消全部走真实 API，两者在报告中分开标注。

## 12. 交付状态

- 改动**未提交**，位于 `03cb0d4` 之上；无 checkpoint 标签；票复选框未勾；design/specs/tasks/tickets 未改。
- 建议 review 重点：`AmapClient.release/_detach_locked` 的锁边界与“身份不符不关闭”语义、cleanup warning 文案、`get()` 脱敏允许列表、e2e 子进程门闩/停止逻辑与 SQLite 对账。

## 11. 复审记录（票3 r1）

- Standards 轴（task3-standards-r1）：**pass**，无 Critical/Important；5 条 Minor：STD-01 loopback 端口握手无读超时、STD-02 `data/` 不存在时的失败路径、STD-03 哨兵断言接近恒真、STD-04 `docs/TECH-STACK.md` 仍写 88、STD-05 评审包漏 README。
- Spec 轴（task3-spec-r1）：**pass**，13 项检查全通过；1 条 low（F1 与 STD-05 同源：评审包漏 README 的 154 计数与分支声明）。
- 处置：STD-04 已由编排层当场修正为 154（纯文档事实更正，无行为变化）；STD-01/02/03/05 与 F1 按 Minor/low 记账，不阻塞本票——脚本主路径已实跑 E2E_OK，剩余为边界与评审包完整性问题，留到 T12/后续整理处理。
- 全量回归：`154 passed in 33.53s`（exit 0，编排层独立复跑）；loopback `E2E_OK`（exit 0，独立进程）。
- 未做：真实供应商/真实 Key、生产并发、票4聚合 suite-scope。

