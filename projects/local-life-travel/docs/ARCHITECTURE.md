# 整体架构（旅行助手 / local-life-travel）

> **状态基线**：已提交 `111f274`（2026-11-13；实现完成、代码审修复已合入，未合并 main）。第 1–6 节描述**当前已实现**的 replay/LIVE 切片；第 7 节是**目标态**（Python Agent — Java — Vue），**尚未实现**，不得当作现状引用。
> T11（LIVE 发送前准入、预算、时限、取消与异常清理）票 1–4 已双轴通过（checkpoint `3bed847`/`03cb0d4`/`1aee907`/`111f274`）；**未做独立代码审、T11 未完成**；改动在本分支 `feat/travel-runtime-budget`、未合并 main。

## 1. 分层总览（当前）

```text
┌─────────────────────────────────────────────────────────────┐
│ 浏览器：web/index.html（原生 HTML+JS，轮询）                  │
└───────────────────────────┬─────────────────────────────────┘
                            │ JSON over HTTP
┌───────────────────────────▼─────────────────────────────────┐
│ 接口层 app/main.py：FastAPI 路由、统一错误体、lifespan        │
│   POST /runs  POST /live-runs  GET /runs/{id}                │
│   POST /runs/{id}/revisions  POST /runs/{id}/cancel          │
│   GET /health/live  /health/ready  /fixtures  /              │
└───────────────┬───────────────────────────┬─────────────────┘
                │ replay 创建                │ LIVE 同步
┌───────────────▼──────────────┐  ┌─────────▼──────────────────┐
│ 编排层 app/engine.py          │  │ app/live.py                │
│ 六阶段状态机 + 预算           │  │ build_live_run →           │
│ app/worker.py 单线程推进      │  │ execute_live → evaluate    │
└───────┬───────────────┬──────┘  └─────────┬──────────────────┘
        │               │                   │
┌───────▼──────┐ ┌──────▼──────────┐ ┌──────▼──────────────────┐
│ domain.py    │ │ replay_tools.py │ │ amap_tools.py           │
│ 纯函数：     │ │ 固定 fixture    │ │ httpx.Client → 高德     │
│ 时间线/约束/ │ │ ReplayAdapter   │ │ AmapAdapter/AmapClient  │
│ 质量/重排    │ │                 │ │ （未真实联调）           │
└──────────────┘ └─────────────────┘ └─────────────────────────┘
        │
┌───────▼─────────────────────────────────────────────────────┐
│ 存储层 app/store.py：SQLite WAL                                  │
│ runs（state 为唯一事实源）+ events（追加）+ idempotency（键/哈希/响应）│
└─────────────────────────────────────────────────────────────┘
```

**依赖方向**：接口层 → 编排层 → 领域/适配器 → 存储；`domain.py` 不依赖 FastAPI、SQLite、httpx，可单独测试。这是“核心可复算”的结构保证。

## 2. 两条执行路径

| 维度 | replay（默认） | LIVE（可选） |
|---|---|---|
| 入口 | `POST /api/v1/travel/runs` | `POST /api/v1/travel/live-runs` |
| 调度 | 202 后由单线程 worker 推进 | 请求内同步执行 |
| 恢复 | `completed_stages` + `events`，重启跳过已完成阶段 | 无恢复调度 |
| 数据来源 | `fixtures/scenarios.json` | 高德适配器（假适配器测试） |
| 失败表达 | 阶段失败落库，run 置 failed | 异常映射为 ToolResult/issue 后落库 |
| 用途 | 可重复验证、可演示 | 契约验证 + 未来真实接入 |

两条路径共用 `ToolResult`、`evaluate_timeline`、`RunView` 等契约，但**不共用执行器**：LIVE 不走 replay 的 worker，避免把“回放恢复”误当成“真实调用恢复”。

## 3. 模块职责

| 模块 | 职责 | 明确不做什么 |
|---|---|---|
| `app/domain.py` | Pydantic 契约、时区校验、纯函数时间线/约束/质量、贪心重排 | 不做 I/O、不写库、不调网络 |
| `app/store.py` | SQLite 表结构、WAL、事务、幂等读写、取消条件更新 | 不做业务判断 |
| `app/replay_tools.py` | fixture 加载/合并、七态 `ToolResult` | 不访问网络 |
| `app/engine.py` | 六阶段、预算、issue、result、`build_run`/`derive_revision` | 不直接发 HTTP |
| `app/worker.py` | tick/drain/后台线程；异常落库并终止，不无限重试 | 不做业务规则 |
| `app/main.py` | FastAPI 路由、错误体、lifespan、单文件页面托管 | 不写业务规则 |
| `app/live.py` | LIVE 同步执行、错误映射、needs_input 处理 | 不复用 replay worker |
| `app/amap_tools.py` | 高德适配器、HTTP 错误分类、POI/天气/营业/路线解析 | 不做时间线判定 |
| `web/index.html` | 表单、轮询、时间线/问题/证据展示 | 不计算业务结论 |

## 4. 关键契约

**工具结果七态**：`valid | empty | timeout | provider_error | format_error | unsupported | unavailable`。未知事实用 `null`，不补 0、不补默认值；`source_ref` + `fetched_at` 让每条事实可追溯。

**执行状态 vs 业务质量**

- `status`：`queued | running | needs_input | completed | failed | cancelled`（生命周期）。
- `quality_status`：`verified_feasible | infeasible | partially_verified | unverified`（约束结论）。

两者正交：`completed + infeasible` 是正常结果；`failed` 也可能保留部分证据。

**幂等与取消**

- 创建：`request_hash = SHA256(规范化请求)`；`BEGIN IMMEDIATE` 内查键、插 run、插幂等行、插入口事件，同一事务。
- 同键同哈希 → 原 run；同键异哈希 → 409；并发同键 → 主键 + 写锁只允许一个成功。
- 取消：条件 `UPDATE ... WHERE status IN ('queued','running')`；`save_run` 用 `CASE WHEN status='cancelled'` 防止在途快照把状态写回 running。
- 边界：本地创建去重，不是外部 exactly-once，也不是远端调用撤销。

**预算**：默认 `max_tool_calls=10`、`max_adjustment_rounds=2`、`max_total_seconds=90`、`max_model_calls=0`（候选起点，未实测）。超限保留部分结果并置 `failed` + `BUDGET_EXHAUSTED`。

## 5. 数据与恢复

| 表 | 关键内容 | 作用 |
|---|---|---|
| `runs` | `id`、`request_json`、`state_json`（唯一事实源）、`budget_json`、`status`、`revision`、`parent_run_id` | 运行快照与派生列 |
| `events` | `run_id`、`seq`、`type`、`payload` | 追加事件，恢复与排障 |
| `idempotency` | `(key)`、`request_hash`、`run_id` | 创建/修订去重 |

恢复语义：`state.completed_stages` 决定 worker 从哪一阶段继续；每阶段完成即提交。**不保证进程崩溃瞬间的原子性**（阶段与事件分次提交），T12 是后续改进项。

## 6. 一次创建的时序（当前）

```text
client → POST /api/v1/travel/runs（可选 Idempotency-Key）
main  → Pydantic 校验 → 规范化 → SHA256
store → BEGIN IMMEDIATE
         ├─ 命中幂等？同哈希 → 返回原 run
         └─ 未命中 → 插 run(queued) + 幂等行 + INTAKE 事件 → COMMIT → 202
worker→ GET run → validate → resolve_poi → fetch_facts → check_constraints
         → adjust（仅硬不可行）→ finalize
      → 每阶段 save：state + event + 派生列
client→ GET /runs/{id} 轮询 → status + quality + timeline + issues
```

## 7. 目标态整体架构（未实现）

用户已定方向：**Python Agent — Java 后端 — Vue**。下面是职责切分与数据流草案，不是已实现模块；具体框架、协议、存储仍待选型与设计评审。

```text
┌──────────────────────────────────────────────────────────────┐
│ Vue 前端：聊天、店铺列表、方案卡、订单、券                      │
└───────────────┬──────────────────────────────┬───────────────┘
                │ REST                          │ SSE（通知）
┌───────────────▼──────────────────────────────▼───────────────┐
│ Java 业务后端（唯一权威状态）                                  │
│  · 会话/多轮约束版本（session_version）                        │
│  · 限时草稿（draft，带过期时间）                               │
│  · 确认后身份/价格复核（quote → revalidate）                   │
│  · 订单提交权（事务抢占 claim，幂等业务键）                    │
│  · 不确定结果对账（按稳定提交标识 reconcile）                  │
│  · 券/核销状态机                                              │
└───────────────┬──────────────────────────────────────────────┘
                │ 内部调用（协议待定：HTTP/消息）
┌───────────────▼──────────────────────────────────────────────┐
│ Python Agent 服务（提案者，不是事实源）                        │
│  · 意图解析与槽位填充                                         │
│  · 工具规划（动态 DAG：节点=工具调用，边=依赖）                │
│  · 参数/依赖/环路预校验                                       │
│  · 同层有界并发、超时、重试上限                               │
│  · 约束提案 + 解释；结果交 Java/程序复核                       │
│  · 经验记忆层（候选）：只沉淀规则，不缓存易变事实              │
└───────────────┬──────────────────────────────────────────────┘
                │ 受治理工具调用（schema/权限/超时/预算）
┌───────────────▼──────────────────────────────────────────────┐
│ 渠道适配层：店铺/报价/券/地图（真实协议与授权未确认）           │
└──────────────────────────────────────────────────────────────┘
```

**目标态的关键不变量（设计意图）**

1. **模型只提案，程序定事实**：金额、距离、营业时间、预算是否够，最终由确定性代码判定；模型输出不能直接落订单。
2. **Java 是唯一写者**：会话版本、草稿、提交权、订单状态都在后端事务内变更；Python Agent 不直接写这些表。
3. **草稿会过期**：确认前必须重新拉取身份/价格/可售状态，旧草稿不能直接提交。
4. **提交权先抢占再外呼**：本地事务先落“提交中”claim，再调用外部；超时/未知结果不当作失败，按稳定标识对账。
5. **SSE 只是通知**：断线重连后以快照/订单查询为准，不能靠事件流重建权威状态。
6. **版本分层**：`session_version`、`draft_version`、`quote_version` 各自独立，不能混成一个“版本号”。

**订单状态机（草案，未实现）**

```text
draft → quoted → submitting → submitted → confirmed
                      │            │
                      │            └─ uncertain → reconciling → confirmed/failed
                      └─ rejected/expired
```

**记忆层（候选，未实现）**：参考分层记忆思路——原始执行流水为底账，经验笔记/索引为二次加工，注入上下文只放轻量目录；只记“规则与教训”（如某渠道限流要先退避），**不记价格、库存、营业状态**这类易变事实；离线整理、可校正、可关闭。

## 8. 关键决策记录

| 决策 | 选择 | 被否方案 | 代价 |
|---|---|---|---|
| 未知如何处理 | `null` + `ROUTE_UNKNOWN`，不补 0 | 默认耗时/0 | 前端要处理空值 |
| 状态与质量 | 两个字段正交 | 单一 status | 调用方要读两个字段 |
| replay 与 LIVE | 两条路径，不共用执行器 | 复用 worker | 两套入口与测试 |
| 存储 | SQLite WAL | MySQL/Postgres | 单写者，多实例弱 |
| 重排 | 一次贪心最近邻 | 穷举/求解器 | 不保证全局最优 |
| 目标态分工 | Agent 提案 + Java 权威 + Vue 展示 | Agent 直连数据库/直下单 | 多服务、边界与协议成本 |

## 9. 演进顺序（与统一任务对应）

1. **T11**：LIVE 发送前预算准入、deadline、资源关闭（进行中，未验收）。
2. **T12**：阶段与事件原子保存。
3. **T13/H11**：readiness 语义。
4. **P17**：结构化脱敏日志。
5. **新方向**：Python Agent、Java 后端、Vue 前端、订单/券、SSE、记忆层——按独立规格与设计评审推进。

## 10. 限制

- 没有真实高德联调、没有 LLM、没有 Java/Vue、没有订单/支付/券核销。
- 目标态架构是职责草案，不是已批准实现；真实渠道协议、费用、身份/授权均未确认。
- SQLite 单写者、LIVE 同步阻塞、预算为“返回后核算”（T11 目标改为发送前准入）。
- 相关文档：[技术栈总结](TECH-STACK.md)、[实现说明](IMPLEMENTATION.md)、[验收](ACCEPTANCE.md)。
