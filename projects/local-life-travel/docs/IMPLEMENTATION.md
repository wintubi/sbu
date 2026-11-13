# Implementation: 单日「行程判官」本地回放切片

> **REPLAY ONLY.** 本实现不连接真实地图、天气、LLM 或支付服务。所有 POI / 路线 / 天气来自 `fixtures/scenarios.json`，`provider` 恒为 `replay-fixture`，**不表示地点已核验**。详见 `docs/change-single-day-replay/proposal.md` 的窄化与局限表。

## 1. 目录结构

```
local-life-travel/
├── app/
│   ├── __init__.py
│   ├── domain.py        # Pydantic 契约、IANA 时区校验、纯确定性 evaluate_timeline、贪心重排
│   ├── store.py         # SQLite：runs / events / idempotency，RLock，WAL
│   ├── replay_tools.py  # fixture 加载/合并、ReplayAdapter（七态 ToolResult）
│   ├── engine.py        # 六阶段状态机、预算、issue、result、build_run / derive_revision
│   ├── worker.py        # tick/drain/后台线程；异常落库并终止，不无限重试
│   └── main.py          # FastAPI：7 个端点、统一错误体、lifespan、单文件 UI
├── fixtures/scenarios.json   # 20 个冻结回放场景（6/4/3/2/3/2）
├── web/index.html       # 原生 JS 单页，无构建链
├── tests/               # conftest + 4 个测试文件（60 个用例）
├── docs/
│   ├── IMPLEMENTATION.md     # 本文件
│   ├── ACCEPTANCE.md         # 精确测试/验收证据
│   └── change-single-day-replay/  # proposal/design/specs/tasks/decision-memo/design-review/code-review
├── tasks/plan.md, tasks/todo.md
├── run.py               # uvicorn 启动入口
├── pytest.ini           # 仅项目内：-p no:cacheprovider（沙箱无法写 .pytest_cache）
└── README.md
```

## 2. 运行

```bash
# 在项目目录内（Python 3.12，无需安装任何新依赖）
python run.py
# 打开 http://127.0.0.1:8765
```

环境变量（均可选）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `TRAVEL_REPLAY_HOST` | `127.0.0.1` | 绑定地址 |
| `TRAVEL_REPLAY_PORT` | `8765` | 端口 |
| `TRAVEL_REPLAY_DB` | `<项目>/data/replay.sqlite3` | SQLite 文件；首次运行自动建目录 |
| `TRAVEL_REPLAY_NO_AUTOSTART` | 未设置 | 设为 `1` 时后台 worker 不自启动（测试用显式 `drain()`） |

页面顶部固定 REPLAY 横幅；`/fixtures` 下拉可一键载入 20 个场景；提交后轮询运行状态，展示状态徽标、质量徽标、POI 匹配、时间线、路线依据、问题清单、调整说明、工具结果与事件日志。

## 3. 六阶段流水线（每阶段完成即落盘）

| 阶段 | 职责 | 对应 T |
|---|---|---|
| `validate` | 复核持久化后的请求；**不调用任何工具/模型** | T-01 |
| `resolve_poi` | 逐候选调用 `poi_lookup`，产出 POIRecord；歧义→`needs_input`，未匹配→无坐标，跨城→`failed` | T-02 |
| `fetch_facts` | 天气 / 营业时段 / 路线矩阵，全部包装成显式 `ToolStatus`；人工补充时段标 `source_type=manual_input` | T-03 |
| `check_constraints` | 纯函数 `evaluate_timeline`：时间窗、停留、路线秒数、开放/预约时段；未知→null+部分核验 | T-04 |
| `adjust` | 仅当 `infeasible` 时做一轮贪心顺序重排（非全局最优），记录 `changes` 并**重新执行全部约束检查**；不自动删除地点 | T-04 |
| `finalize` | 置 `completed`（仅表示处理结束），写 FINALIZED 事件 | T-05 |

`runs.state` 为唯一事实来源；`runs` 表其余列是派生。`completed_stages` + `events` 保证重启后每阶段只执行一次。

## 4. 数据契约（SPEC §5 落地）

请求：`mode, scenario_id, city, date, timezone, origin, time_window{start,end}, transport, candidates[{name|poi_id,stay_seconds,optional_time_window?}], preferences, manual_facts[], selected_poi_ids{}`。

状态：`queued|running|needs_input|completed|failed|cancelled`；质量：`verified_feasible|infeasible|partially_verified|unverified`；工具：`valid|empty|timeout|provider_error|format_error|unsupported|unavailable`；匹配：`matched|ambiguous|unmatched`。

记录字段：`POIRecord(internal_id, provider, provider_poi_id, name, city, coordinates, fetched_at, evidence_refs, match_status)`、`Fact(fact_id, subject_id, field, value|null, source_type, source_ref, fetched_at, valid_for?, provider_status)`、`RouteLeg(from_poi_id, to_poi_id, transport, duration_seconds, distance_meters, source_ref, fetched_at)`、`ItineraryResult(run_id, revision, quality_status, visits, legs, issues, changes, evidence_refs)`。

时间用 RFC3339 带偏移，另存 IANA `timezone`；用标准库 `zoneinfo.ZoneInfo` 校验显式偏移与该本地日期的区域规则，拒绝 DST 重叠/间隙的本地时间（`tzdata` 已随环境安装）。距离米、时长秒、经纬度做范围检查。缺失事实用 `null`，不用 0/空串/猜测值。

## 5. API

| 方法 / 路径 | 成功 | 说明 |
|---|---|---|
| `POST /api/v1/travel/runs` | 202 | 回放 `TravelRequest`；`Idempotency-Key` 可选（同键同请求返回同一 run，同键异请求 409） |
| `POST /api/v1/travel/live-runs` | 202 | LIVE `LiveTravelRequest`；发送前逐HTTP准入（默认40）、单调deadline（默认90秒）、可取消、异常资源收尾；无 `AMAP_API_KEY` 时 503，不创建假成功 run。契约见 [LIVE-AMAP](LIVE-AMAP.md) |
| `GET /api/v1/travel/runs/{run_id}` | 200 | 完整 RunView；404 `RUN_NOT_FOUND` |
| `POST /api/v1/travel/runs/{run_id}/revisions` | 202 | `selected_poi_ids` / `remove_candidates` / `time_window` / `transport` / `manual_facts`；新 run 带 `parent_run_id`，旧结果不变 |
| `POST /api/v1/travel/runs/{run_id}/cancel` | 200 | 原子条件取消；终态 409 |
| `GET /health/live` | 200 | 进程存活，无外部请求 |
| `GET /health/ready` | 200 | database/worker/mode/fixtures；非测试模式下 worker 停止即 `degraded` |
| `GET /fixtures` | 200 | 20 个场景索引（供 UI 载入） |
| `GET /` | 200 | 单文件 HTML |

统一错误体 `{code, message, retryable, run_id?, field_errors?}`；非法 JSON 也是 422 `VALIDATION_ERROR`，**不会 500**。

## 5.1 LIVE 路径（未真实联调）

`app/live.py` 是独立于回放状态机的同步路径：`build_live_run` → `execute_live` → `evaluate_timeline`。它复用同一 `ToolResult`/`evaluate_timeline` 契约，但不经过 replay fixture、worker 或六阶段。POI/天气/营业/路线错误分别写 issue；歧义置 `needs_input`；供应商错误/跨城置 `failed`；任何未预期异常落 `STAGE_EXECUTION_ERROR` 并保存 failed run，不留下“看起来成功”的结果。LIVE 运行预算、单调 deadline、API 取消、异常资源收尾与脱敏的契约见 [LIVE-AMAP](LIVE-AMAP.md) 6.1–6.8；逐条验收证据见 [ACCEPTANCE 第 10 节](ACCEPTANCE.md#10-2026-11-13-增量live预算deadline取消异常收尾与独立进程验收)。适配器通过 `create_app(live_adapter_factory=...)` 注入，测试用假适配器/真实适配器+MockTransport；生产路径构造 `AmapAdapter`，无 Key 时端点 503。live 的 `needs_input` 通过同一 `/runs/{id}/revisions` 选点生成新 live run，旧运行保留。

## 6. 预算与并发

默认 `max_tool_calls=10 / max_adjustment_rounds=2 / max_total_seconds=90 / max_model_calls=0`（SPEC §8 候选起点，未实测，不作性能承诺）。超限停止后续调用、保留部分结果、`budget.status=exhausted`、写 `BUDGET_EXHAUSTED` 并置 `failed`。

LIVE 路径另有独立口径：`max_tool_calls=40`（每次准入的HTTP尝试）、`max_total_seconds=90`（单调 deadline）、单操作默认 5 秒且不超过剩余时间；详见 [LIVE-AMAP](LIVE-AMAP.md) 6.1/6.5。replay 的默认值不受影响。

并发处理：SQLite 单连接 + `RLock` + WAL；`create_run_atomic` 用 `BEGIN IMMEDIATE` 把 run、幂等行、intake 事件放在同一事务；`cancel_run` 用条件 `UPDATE ... WHERE status IN ('queued','running')`；`save_run` 的 `CASE WHEN status='cancelled'` 防止在途 worker 把已取消运行写回 running。worker 的未预期异常会写日志、落 `STAGE_EXECUTION_ERROR` 并置 `failed`，避免无限重试。

## 7. 回放 fixture 格式

`fixtures/scenarios.json` 用 `defaults` + 每个 scenario 的 `request_overrides` / `tools_overrides` 组合出完整场景，避免 20 份重复数据：

- `tools.poi`：按 candidate 的条目，支持 `matched / ambiguous(options) / unmatched`，或整体 `{"status":"format_error"}` 模拟工具级失败。
- `tools.weather`：`forecast_date != request.date` 即返回 `unavailable` + `WEATHER_DATE_NOT_COVERED`。
- `tools.hours`：`windows` 为 `{"地点": ["HH:MM","HH:MM"]}`；`status=unsupported` 且无人工补充时保留 unknown。
- `tools.routes`：对称 `matrix`，键 `a|b`（`__origin__` 表示出发位置），值 `[时长秒, 距离米]`。
- `expect` / `revision_expect`：期望 status / quality_status / 必须出现的 issue code / visit_count / has_changes。

新增场景只需追加一个 `scenarios` 条目；`tests/test_fixtures.py::test_all_20_scenarios_match_frozen_expectations` 会自动跑期望矩阵。分组数量由 `test_scenario_groups_frozen_at_20` 冻结。

## 8. 测试

```bash
python -m pytest -q
```

`tests/conftest.py` 为每个测试建独立 SQLite（放在项目 `data/pytest/`，因为本环境 OS 临时目录不可写），关闭后台 worker 自启动并显式 `drain()`。精确结果见 `docs/ACCEPTANCE.md`。

## 9. 明确未运行 / 未实现（不得冒充完成）

- 真实服务联调、真实 POI/天气/路线返回契约、配额、时效；`live` 模式。
- LLM / 模型对照实验、效果阈值（POI 匹配率、有效完成率、p95、成本）与独立验收集。
- 多日规划、灵感发现、活动清单、购票/支付/订单/核销、主动触达。
- 公网多用户、认证、限流、部署、容量测试；Vue/TS 前端标准构建（本轮单文件 HTML，无构建链）。
- LangGraph / HelloAgents 编排迁移、向量库、消息队列、K8s。
- 独立评审与跨模型评审；OpenSpec/sdflow 正式工具链门禁（本机未安装）。

## 10. 交付位置说明

本实现构建于会话工作区镜像 `D:\workspace-dsh\local-life-travel\`（子代理被沙箱拒绝写入 `D:\git\sbu\projects\local-life-travel`，且 escalation 被用户拒绝）。所有路径相对 `__file__`，复制到仓库后原样可运行；复制命令与文件清单见交付消息与 `docs/ACCEPTANCE.md`。
