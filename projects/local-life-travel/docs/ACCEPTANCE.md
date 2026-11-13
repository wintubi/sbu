# Acceptance Evidence: 单日「行程判官」回放切片

> 状态：**软件门槛已通过（本地回放范围内）**；**不宣称**原 `SPEC-DRAFT.md` 全规格通过，也**不宣称**业务/领域效果验收完成。
> 记录日期：2026-11-07（Asia/Shanghai）。记录者：delegated 实现代理（自测；父代理将独立评审与验证）。

## 1. 环境（实测，未安装任何新依赖）

| 项 | 值 |
|---|---|
| OS | Windows |
| Python | 3.12.9 (`C:\Miniconda3\python.exe`) |
| fastapi | 0.115.12 |
| pydantic | 2.11.2 |
| starlette | 0.46.1 |
| uvicorn | 0.34.0 |
| httpx | 0.28.1 |
| pytest | 9.0.3 |
| anyio | 4.9.0 |
| 标准库 | `sqlite3`、`zoneinfo`（`tzdata` 已随环境安装，实测 `ZoneInfo("Asia/Shanghai")` 可用） |

**未安装**任何新包；未安装 sdflow/OpenSpec CLI。

## 2. 精确测试命令与结果

```
cd <project>
set TRAVEL_REPLAY_NO_AUTOSTART=1
python -m pytest -q
```

最终输出（逐字）：

```
............................................................              [100%]
60 passed in 8.60s
```

退出码：`0`。**60 passed，0 failed，0 skipped，0 xfail。**（墙钟时间每次运行略有差异，实测 8.51s–8.60s；通过数稳定为 60。）

按文件：

| 文件 | 用例数 | 覆盖 |
|---|---:|---|
| `tests/test_domain.py` | 24 | T-01 字段/时区/DST、T-02 未匹配与跨城、T-04 纯时间线/重排/null 传播 |
| `tests/test_fixtures.py` | 7 | 20 场景分组、请求合法性、期望矩阵、修订场景、provider 声明 |
| `tests/test_worker.py` | 13 | 重启恢复、预算（工具次数/总时限）、歧义、格式错误、未知约束、时间冲突、天气覆盖、修订、取消不可复活、worker 异常 |
| `tests/test_api.py` | 16 | 健康、UI、非法 JSON、422/400/404/409、创建轮询、幂等、修订、取消、全场景 API 可达 |
| **合计** | **60** | |

### 中途失败与修复（如实记录）

首次运行：`2 failed, 57 passed in 8.32s`。两处均为**实现缺陷**，非测试过严：

1. `test_t01_iana_offset_and_dst_validation` — `validate_local_datetime` 先判歧义再判 DST 间隙，把「不存在的本地时间」误判为「歧义」。修复：调整检测顺序，先做 UTC 往返判间隙，再比较 fold 偏移判歧义；测试改为断言正确的异常消息。
2. `test_t04_unknown_duration_uses_null_not_zero` — 前序路线未知后 `current=None`，后续已知路线仍执行 `None + timedelta` 抛 `TypeError`。修复：`if not leg_ok or current is None` 统一走 null 分支并写 `ROUTE_UNKNOWN`。

修复后重跑：`59 passed in 8.53s`。这两个 bug 是测试实际发现的，不是事先预置。随后补齐 `max_total_seconds` 总时限强制（原先只声明未执行）并新增 `test_budget_total_time_limit_is_enforced`，最终全量：`60 passed`（多次复跑均为 60 passed）。

## 3. 真实 HTTP / 服务启动验证

用 `python run.py`（uvicorn 0.34.0，端口 8765）启动真实服务，日志显示 `Application startup complete`：

| 请求 | 结果 |
|---|---|
| `GET /health/live` | 200，`{"status":"ok","mode":"replay"}` |
| `GET /health/ready` | 200，`status=ready`、`worker=running`、`worker_healthy=true`、`fixtures=20`、`live_mode_enabled=false` |
| `GET /fixtures` | 200，20 个场景，10212 bytes |
| `GET /` | 200，14686 bytes，含 REPLAY 横幅 |
| `POST /api/v1/travel/runs` (F01) | 202，`status=queued`，`mode=replay` |
| 轮询 `GET /runs/{id}` | `completed` / `verified_feasible` / 3 visits / 6 个 completed_stages |
| 关闭 lifespan 后 | `worker.is_alive == False`（worker 已停止） |

另用 `TestClient` 对模块级 `app`（autostart=True）验证：ready 报 `worker=running`、端到端完成、shutdown 后 worker 停止。

> 注：一次 PowerShell `Invoke-WebRequest` 读取控制台缓冲区报 Win32 5，是工具输出捕获问题；同一批请求在 uvicorn 访问日志中均为 200，随后用 Python `urllib` 重新取得全部正确 JSON 负载。

## 4. 20 个冻结场景期望矩阵

`tests/test_fixtures.py::test_all_20_scenarios_match_frozen_expectations` 对 20 个场景逐一断言 `status / quality_status / 必须出现的 issue code / visit_count / has_changes`，**全部通过**。分组（由 `test_scenario_groups_frozen_at_20` 冻结）：

| 类别 | 数量 | 代表结果 |
|---|---:|---|
| feasible | 6 | `completed / verified_feasible`；F06 经贪心重排后可行且有 `changes` |
| time_conflict | 4 | `completed / infeasible`，含 `TIME_WINDOW_EXCEEDED` 或 `OPENING_WINDOW_VIOLATION` |
| ambiguity | 3 | `needs_input`，`candidates_for_input` 非空，`result=None` |
| weather_coverage | 2 | `completed / partially_verified`，`WEATHER_DATE_NOT_COVERED`，`Fact.value=null` |
| tool_error | 3 | F16 `failed/TOOL_FORMAT_ERROR`；F17/F18 `completed/partially_verified` |
| condition_modification | 2 | F19/F20 的父运行与修订运行期望均命中，父结果保持不变 |

## 5. 对 SPEC §9 测试层的覆盖与缺口

| 层 | 本轮状态 |
|---|---|
| 单元/性质 | **已运行**：时间计算、窗口检查、排序后约束、非法输入、null 传播、IANA/DST |
| 契约 | **已运行**：回放工具返回 → POI/Fact/RouteLeg；空/错/超时/unsupported/unavailable 分别传播 |
| 集成 | **已运行**：SQLite 恢复、幂等、取消、条件修改、预算停止、原子取消/幂等事务 |
| API端到端与浏览器 | **API链路已运行**。**Chrome/CDP 真实浏览器已完成**：F01 可行、F07 冲突、F11 歧义、F16 工具错误；F16 页面显示 failed/unverified/TOOL_FORMAT_ERROR，不伪造成功。Playwright 仍因临时目录 EPERM 未用，不能把 Chrome CDP 称为 Playwright。证据：`docs/evidence/ui-travel.png`、`ui-travel.txt`。 |
| 回放固定集 | **已运行**：20 个冻结场景期望矩阵 |
| 真实服务 | **未真实联调**（live API 与假适配器已测；无新 Key、无付费调用授权） |
| 模型对照 | **未运行**（本轮不调用模型） |
| 效果门槛 | **未设定**：POI 匹配、有效完成率、p95、成本阈值均未在真实样本上测量 |
| 前端标准构建 | **未运行**：本轮单文件 HTML 无构建链；不修改第 13 章前端 |

**软件门槛结论**：确定性回归全通过；无占位结果伪成功；`needs_input/failed/partially_verified/infeasible/completed` 可区分；重启恢复与幂等通过；服务与页面可启动。**这些只在本机回放范围内成立。**

## 6. 失败 / 跳过 / 未运行（分开记录）

- 失败：最终 0（首次 2 个实现缺陷已修复并复测通过）。
- 跳过：0。
- 未运行：真实服务联调、模型对照、效果阈值评测、独立验收集、前端标准构建、公网/多用户/并发容量、Playwright 全量 E2E、独立与跨模型设计评审、OpenSpec/sdflow 正式门禁。
- 未宣称：真实 POI 核验、业务效果验收、并发容量、多用户安全。

## 7. 已知限制与残留问题

| 项 | 说明 |
|---|---|
| 回放端点只接受 replay | `POST /runs` 的 live 请求 400；独立 `POST /live-runs` 无 Key 时 503；真实供应商契约/配额/时效未验证 |
| 路线时长未按交通方式换算 | fixture 只有一套对称矩阵，`transport` 被记录但不影响耗时 |
| 20 场景是演示级回放 | 不能推断用户满意度/业务转化（SPEC §9 口径） |
| 单进程 SQLite | 无多实例/并发容量承诺 |
| 设计评审是自查 | 非独立/跨模型评审；父代理将独立验证 |
| 目标目录写入受限 | 实现位于 `D:\workspace-dsh\local-life-travel\` 镜像，需父代理复制到仓库 |
| 残留目录 | 本环境 pytest 写 `.pytest_cache` 被拒，留下两个不可访问的 `pytest-cache-files-*` 空目录；复制时应排除（见交付命令） |
| `pytest.ini` | 仅项目内，`-p no:cacheprovider` 规避上述缓存写入；不是仓库根配置 |

## 8. 复现步骤

```bash
# 复制镜像到仓库后
cd D:\git\sbu\projects\local-life-travel
set TRAVEL_REPLAY_NO_AUTOSTART=1
python -m pytest -q -p no:cacheprovider
python run.py                # 打开 http://127.0.0.1:8765
```

> 本文第 2–9 节是 2026-11-07/08 历史记录（当时 `88 passed`）。本分支最新计数、LIVE 逐条证据与命令见第 10 节；不要拿历史计数当当前结果。

## 9. 2026-11-08 增量：高德适配器与 live API

- 新增 `app/amap_tools.py` 与 `tests/test_amap_tools.py`，14 项离线契约测试覆盖唯一匹配、同名歧义、空结果、Key 回收、超时、坏坐标、天气日期覆盖/不覆盖、路线与营业时间解析。
- 全量复跑：**88 passed in 11.01s**（回放 61 + 高德离线 14 + live API 13）。
- 新增 `app/live.py` 与 `POST /api/v1/travel/live-runs`：用可注入适配器测试成功、歧义、供应商错误、跨城、无 Key 503、幂等重放/冲突；**没有用新 Key 真实联调**，因此真实高德数据/真实行程仍未验收。详见 `docs/LIVE-AMAP.md`。
- 无 Key 时 `python scripts/amap_probe.py` 退出 2 且不发网络请求；这是预期失败路径，不是联调成功。

## 10. 2026-11-13 增量：LIVE预算、deadline、取消、异常收尾与独立进程验收

> 范围：OpenSpec change `travel-runtime-budget`（LRC-01..09）的 ticket 1–4 实现与聚合证据。ticket 4 的聚合 suite-scope 已运行（`layers={}`，config 未配置 test-suites；按仓内既有约定回退全量 pytest + 独立进程 loopback），证据见 `openspec/changes/travel-runtime-budget/impl-reports/task4-aggregate.md`：全量 **159 passed**、loopback **E2E_OK**。**真实高德 Key、费用、硬中断、断电恢复均未验证。**

### 10.1 分支与状态

| 项 | 值 |
|---|---|
| 分支 | `feat/travel-runtime-budget`（ticket 1/2/3 已 checkpoint：`3bed847` / `03cb0d4` / `1aee907`；ticket 4 聚合证据已运行，未打标签） |
| 与 main | **不是 main**；未 merge / 未 push / 未归档；不得把本分支结果写成 main 现状 |
| 独立代码审 | **未做**；未独立审前不标 T11 完成 |
| 私人面试稿 | **未更新**（`docs/interview-v0.1.md` 的 main 现状数字保持原样） |
| 真实供应商 | 未提供 Key、未联调；全部测试为 `MockTransport` 合成供应商 + 合成 Key `synthetic-example` |
| 实施记录 | [ticket1](../openspec/changes/travel-runtime-budget/impl-reports/task1-http-admission.md) · [ticket2](../openspec/changes/travel-runtime-budget/impl-reports/task2-deadline-cancel.md) · [ticket3](../openspec/changes/travel-runtime-budget/impl-reports/task3-cleanup-e2e.md) |
| 规范/设计 | [LIVE运行控制规格](../openspec/changes/travel-runtime-budget/specs/live-runtime-control/spec.md) · [设计](../openspec/changes/travel-runtime-budget/design.md) · [LIVE API 契约](LIVE-AMAP.md) |

### 10.2 实测命令与计数（本分支最后一次运行）

```text
C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider
→ 159 passed, 2 warnings in 39.14s        (exit 0)

C:/Miniconda3/python.exe -m pytest -q -p no:cacheprovider tests/test_amap_tools.py tests/test_live.py tests/test_live_admission.py tests/test_live_deadline_cancel.py tests/test_live_cleanup_redaction.py tests/test_live_loopback_e2e.py
→ 93 passed, 2 warnings in 27.59s       (exit 0；14+13+23+23+19+1)

C:/Miniconda3/python.exe scripts/live_loopback_e2e.py
→ {"create": {"close_attempts": 1, "run_id": "...", "scenario": "create",
              "status": "cancelled", "tool_calls": 3, "transport_sends": 3},
   "revision": {"child_run_id": "...", "child_tool_calls": 3, "close_attempts": 2,
                "parent_run_id": "...", "parent_status": "needs_input",
                "scenario": "revision", "transport_sends": [11, 3]},
   "scope": "independent-process loopback; real AmapAdapter + MockTransport; ..."}
→ E2E_OK                                 (exit 0)
```

2 条 warning 是 uvicorn 依赖的 websockets legacy DeprecationWarning，与改动无关。计数构成：134（ticket 1+2 时的全量）+ 19（`tests/test_live_cleanup_redaction.py`）+ 1（`tests/test_live_loopback_e2e.py` 包装）。

### 10.3 LRC-01..09 逐条证据 / 未满足项

| 需求 | 运行证据（真实测试） | 未满足/限制 |
|---|---|---|
| LRC-01 发送前准入 | `test_live_admission.py::test_http_boundaries_at_transport[0/1/2/40]`、`test_http_limit_is_reserved_before_transport`、`test_real_adapter_api_exact_budget_and_replay`；`test_live.py::test_live_budget_counts_internal_http_requests`；e2e create 场景 `tool_calls == transport_sends == 3` | 计数是HTTP尝试，不是供应商计费；进程崩溃前未落库部分未知 |
| LRC-02 deadline 与结果接受 | `test_live_deadline_cancel.py::test_check_boundary_zero_and_ninety_uses_monotonic_clock`、`test_reserve_http_timeout_is_min_of_config_and_remaining`、`test_amap_client_applies_bounded_timeout_to_all_four_operations`、`test_late_tool_result_after_deadline_is_not_completed`、`test_late_needs_input_after_deadline_is_rejected`、`test_cleanup_past_deadline_rejects_completed_terminal`、`test_utc_wall_clock_jump_does_not_change_monotonic_elapsed` | 协作式 deadline，不保证90秒硬中断/撤回挂起同步调用 |
| LRC-03 取消观察与持久状态 | `test_live_deadline_cancel.py::test_api_create_replay_then_cancel_stops_next_handler`、`test_api_revision_replay_then_cancel_stops_child_http`、`test_cancel_after_final_check_normalizes_atomic_terminal`、`test_cancel_wins_over_in_memory_exhaustion_and_drops_reason`；e2e create/revision 两场景经真实 HTTP cancel + GET/同键重放 | 检查后到发送之间的在途请求不承诺撤回；单进程线程池容量不构成生产并发承诺 |
| LRC-04 耗尽可解释结果 | `test_live_admission.py::test_api_interrupted_batch_keeps_normalized_evidence[7/10]`；`test_live_deadline_cancel.py` 的 late/deadline 用例；e2e cancel 后保留实际计数 | 崩溃/断电后逐HTTP账本未做（T12 另跟踪） |
| LRC-05 幂等重放 | `test_real_adapter_api_exact_budget_and_replay`、`test_idempotent_replay_does_not_build_runtime`、`test_live.py::test_live_idempotency_replay`；e2e 等待期间同键重放取 run_id 且事件不增 | 无幂等键时原同步创建完成前仍无 run_id |
| LRC-06 适配器显式受控 | `test_live_admission.py::test_bind_race_serializes_on_client_lock_and_one_winner`、`test_owned_close_rejects_bind_while_physical_close_waits[False/True]`、`test_missing_binding_protocol_invokes_no_tool`、`test_borrowed_client_unbinds_for_sequential_runs_without_close`；`test_live_cleanup_redaction.py::test_constructor_validation_failure_closes_owned_client_and_is_idempotent` | 缺协议为已声明内部破坏性变更，无静默 fallback |
| LRC-07 拥有权覆盖所有出口 | `test_live_cleanup_redaction.py` 的 success/provider_error/call_limit/deadline/cancel/constructor 六项、`test_factory_failure_before_return_owns_its_unreturned_resources`、`test_borrowed_client_is_not_closed_and_reused_sequentially`、`test_unbind_failure_still_attempts_physical_close_and_keeps_result`；`test_live_admission.py` 的 close 幂等/借入用例 | factory 返回前抛错时顶层无法关闭未知对象（由 factory 负责） |
| LRC-08 清理失败不掩盖主结果/脱敏 | `test_live_cleanup_redaction.py::test_cleanup_failure_preserves_primary_provider_failure_and_budget`、`test_cleanup_failure_preserves_call_limit_category_and_exact_count`、`test_close_error_with_deadline_during_cleanup_keeps_earlier_failure`、`test_direct_create_live_run_saves_after_cleanup_failure`、`test_httpx_error_text_is_reduced_to_safe_category_and_type`、`test_provider_info_is_not_echoed_but_numeric_infocode_is_kept`、`test_top_level_execution_exception_text_is_not_persisted`、`test_cancel_probe_failure_does_not_leak_raw_exception`、`test_cleanup_exception_text_is_not_persisted`；`test_live_deadline_cancel.py::test_probe_failure_is_fixed_category_without_raw_exception_text` | 只覆盖本进程路径；外部日志采集/APM 不在本 change |
| LRC-09 真实范围说明 | 本节 + [LIVE-AMAP.md](LIVE-AMAP.md) 6.1–6.8 + 各 ticket 报告；命令/exit/计数均为实跑，失败/未验项单列 | ticket 4 聚合验证已运行（159 passed + loopback E2E_OK，见 task4-aggregate.md）；真实高德、费用、计量、硬中断、断电恢复、main 合并与独立代码审仍**未满足** |

### 10.4 失败 / 跳过 / 未运行（分开记录）

- 失败：最终 0。
- 跳过：0（未新增 skip/xfail；无测试被删除或放宽）。
- 未运行：真实 Key/真实高德联调、供应商计费与效果、硬中断/90秒强制返回、断电恢复、独立代码审、T11 完成、push/merge。
- 验收边界：以上全部为**本机离线软件契约**；`completed` 只表示本进程处理结束，不代表真实行程可行或供应商成功。
