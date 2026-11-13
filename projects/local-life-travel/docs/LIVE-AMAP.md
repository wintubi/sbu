# 高德真实数据适配器（LIVE / 未联调）

状态：适配器、`POST /api/v1/travel/live-runs` 路径、发送前HTTP预算准入、单调deadline（默认90秒）、可达的API取消与原子终态已实现并离线验证（见 6.1–6.6）；真实 Key 未提供，异常资源矩阵与真实loopback独立进程验收属票3。**没有用真实 Key 成功调用过**，因此不能声称真实数据/真实行程验收通过。默认运行仍是 replay。

## 1. 为什么先做适配器而不是直接接页面

现有 `ReplayAdapter` 已经把 POI/天气/营业/路线统一成 `ToolResult(status, source_ref, payload, error_code)`。真实供应商的风险不在“能不能发 HTTP”，而在：空结果、限流、超时、字段缺失、日期不覆盖、营业时间没有返回。先把这些映射做实，再用一个 Key 做小样本探测，才能避免把供应商错误伪装成成功行程。

## 2. Key 的现状（实测证据）

- 原 chapter13 前端 `Result.vue` 里有一个历史硬编码 Key（注释写“Web 服务 API Key”）。
- 2026-11-08 用该 Key 调用高德 Web 服务 `geocode/geo` 与 `place/text`，两次均返回 HTTP 200、`status=0`、`info=USER_KEY_RECYCLED`、`infocode=10013`。
- 结论：该 Key 已被回收，不能继续使用。代码里不应保留硬编码 Key；新 Key 只放环境变量。
- 仓库内的 `backend/.env.example`、`frontend/.env.example` 只有占位符，没有可用 Key。

## 3. 官方申请流程（已核对高德官方“创建应用和 Key”页）

1. 打开高德开放平台控制台，登录或注册开发者账号：<https://console.amap.com/>。
2. 进入【应用管理】→【创建新应用】，填写应用名称与类型。
3. 在应用下【添加 Key】，服务平台选择【Web 服务】。
4. 创建成功后复制 Key，配置到本机环境变量 `AMAP_API_KEY`（不要提交到 Git）。

账号注册/实名要求以控制台实际页面为准。个人开发者通常需要手机号验证，部分能力还涉及实名认证；我没有代替你完成手机短信、实名或验证码，也不会伪造身份。若注册页面要求邮箱验证码，可以使用你已有的邮箱；自动注册新邮箱并不是可靠路径（主流邮箱同样要手机号/人机验证，且代注册涉及服务条款与账号归属问题）。

## 4. 使用

```powershell
$env:AMAP_API_KEY = "<你的 Web 服务 Key>"
python scripts/amap_probe.py --city 北京
```

探测只做少量真实请求：3 次 POI 搜索、1 次天气、两两 POI 之间的路线（3 个点最多 3 条）。脚本只打印状态、匹配结果、质量状态和 issue code，不打印 Key。若 Key 无效/被回收，会输出 `provider_error`/`10013`，不会继续生成行程。该脚本自行持有 `AmapClient`、不绑定单次run的runtime，因此**不受run的40次/90秒约束**（见 6.3）。

预期输出示例（真实成功时）：

```text
poi 故宫博物院: status=valid match=matched
weather 2026-11-09: status=valid
hours: status=valid windows=1
leg 故宫博物院 -> 景山公园: status=valid
quality_status=verified_feasible
issue_codes=
```

若天气日期不在预报窗口、营业时间缺失、路线超时，会分别出现 `WEATHER_DATE_NOT_COVERED`、`HOURS_UNKNOWN`、`TOOL_TIMEOUT` 等 issue，质量会降为 `partially_verified`，而不是硬说可行。

## 5. 适配器边界

| 能力 | 实现 | 限制 |
|---|---|---|
| POI 搜索 | `/v3/place/text`，`citylimit=true` | 同名多结果返回 ambiguous，不静默选第一个 |
| POI 详情 | `/v3/place/detail` | 用户选定候选后使用 |
| 天气 | `/v3/weather/weatherInfo`，按日期匹配 | 高德没有“按日期查询”的参数；目标日不在预报窗口就标 unavailable，不用当前天气代替 |
| 营业时间 | POI `biz_ext.open_time` | 很多 POI 不返回；缺失就保持 unknown，不编造 |
| 路线 | 步行 `/v3/direction/walking`、驾车 `/v3/direction/driving` | 公交/骑行未接入，返回 unsupported；每条腿一次请求，受预算限制 |
| 路线矩阵 | `matrix(pairs)` 显式传腿 | 不使用 `leg_key` 的对称假设做真实双向路线；当前矩阵按无向 key 存，真实单向道路是已知局限 |
| 错误 | 超时/HTTP/JSON/业务错误 | 分别映射 timeout/provider_error/format_error，不吞成空成功 |

## 6. Live API

`POST /api/v1/travel/live-runs` 接收与 replay 相同的城市/日期/时间窗/3–6 候选，但走 `app.live`：同步调用适配器、规范化 ToolResult、用同一 `evaluate_timeline` 判定质量并落库。测试用可注入假适配器覆盖：成功、歧义 needs_input、供应商错误 failed、跨城 blocker、无 Key 503、幂等重放与冲突；歧义运行可通过 `POST /api/v1/travel/runs/{run_id}/revisions` 选点生成新的 live run，旧运行保留。真实 Key 未提供，所以这条路径仍是“代码可运行、真实未联调”。缺 `AMAP_API_KEY` 时端点返回 503 `LIVE_NOT_CONFIGURED`，不创建假成功运行；同键改载荷仍 409。

### 6.1 预算是“发送前的HTTP尝试数”，默认40

- 每次 `AmapClient.get` 在真正调用 httpx 之前，先向本run的 `LiveRuntime` 预占一次。预占成功才发送，`budget.tool_calls` 才 +1；第 N+1 次（上限 N）在预占处失败，**不进入传输层**，transport handler 命中 0。默认上限 40（`LIVE_MAX_TOOL_CALLS`）。
- 计数口径是HTTP尝试，不是工具方法次数，也**不是供应商计费凭证**：连接失败、超时、供应商错误、响应格式错误的**已准入**尝试各计 1，不退还；纯本地缓存、解析、空矩阵不预占。
- matrix 逐腿、hours 逐 POI detail、adcode/weather 都在同一 guard 内：origin 1 次、每个 POI 搜索/详情 1 次、天气（含首次 adcode）最多 2 次、营业详情每个 POI 1 次、每条腿 1 次。
- 恰好用满上限不额外拒绝：只要不再需要新的发送，运行可在时间和业务规则满足时正常完成；`limit=0` 且需要HTTP则发送 0 次并耗尽。
- 次数耗尽：`failed` + `budget.status=exhausted` + `exhaustion_reason=call_limit` + `BUDGET_EXHAUSTED`，`result=null`、`quality_status=unverified`；已成功的子证据（营业详情、单条腿）保留来源、抓取时间和最小payload，但**部分批次不算完整成功**。
- 工具、子证据交付、评估都不消费预算；不存在“按工具方法数补 1”的事后记账（该旧逻辑已移除）。

### 6.2 内部绑定协议（本次破坏性内部变更）

- 注入的 factory 仍接收 `(city, transport)` 并返回 adapter，构造过程不得外呼；返回对象**必须有** `bind_runtime(runtime)` 和 `close()`。缺任一协议或绑定失败 → `failed` + `STAGE_EXECUTION_ERROR`，工具调用与HTTP发送均为 0。缺协议时，已取得且可清理的对象仍会尝试 `close()` 一次；绑定失败时该对象仍归原 owner，本次run**不调用**它的 `close()`。没有会静默绕过 guard 的 fallback。
- 每个新run创建独立 `LiveRuntime`（自己的预算计数）；同一 client 同时只能绑定一个 active run，第二个绑定被拒绝，不覆盖前者的控制，原run仍可执行且预算独立。
- 拥有权：默认 factory 用 `AmapAdapter(AmapClient(), owns_client=True)` 显式拥有独立 client；借入 client 只解绑、物理关闭次数为 0；自有 client 的 `close()` 先在同一短锁内置 `closing` 并按身份解绑，再在锁外物理关闭一次，重复清理不增加关闭次数；关闭失败也不恢复“可借用”状态。
- 绑定失败的清理不得解绑/关闭另一个 active run 的 client；借入 client 解绑后可按顺序给下一个run复用。
- 测试fake必须显式模拟逐HTTP准入：每个模拟发送前调用 `runtime.reserve_http(timeout)`，而不是事后按工具计 1。

### 6.3 独立脚本不拥有run预算

`scripts/amap_probe.py` 自行持有并关闭 `AmapClient`，不绑定 runtime：它仍受自己的单操作 timeout 约束，但**不受本run的40次/90秒约束**，也不能声称受run guard 保护。

### 6.4 离线复现：修前/修后

隔离的临时 SQLite + `httpx.MockTransport`（无真实网络、无真实 Key），命令：

```powershell
python openspec/changes/travel-runtime-budget/evidence/reproduce_budget.py
```

| 观察项 | 修前（基线 `6a78560`，2026-11-09 记录） | 本分支修后（2026-11-13 实测） |
|---|---|---|
| limit | 2 | 2 |
| 传输层实际 attempts | 3 | 2 |
| `client.calls` | 3 | 2 |
| 持久化 `budget.tool_calls` | 2 | 2 |
| `budget.exhaustion_reason` | 缺失（该键本次新增，历史run可缺） | `call_limit` |
| `oversent` | true | false |
| 终态 | failed / exhausted | failed / exhausted |

修后一列可由该命令输出的 `limit` / `transport_attempts` / `client_calls` / `persisted_count` / `exhaustion_reason` / `run_status`+`budget_status` / `oversent` 逐项复现。修前按工具方法返回后的差额记账，超限的第3次已经发出、只是没入账；现在第3次在预占处被拒，传输层只有 2 次，持久化计数与实际准入一致。

### 6.5 运行deadline：默认90秒、单调elapsed、晚到拒绝（票2）

- 每个新run在落盘后、adapter factory之前取一次单调开始值（默认 `time.monotonic`，可注入）；`elapsed_seconds` 只用单调差，UTC墙钟跳变不改变预算。最终采样在收尾之后，**可能超过90秒**，不能据此声称发生过硬中断。
- `LiveRuntime.check()` 顺序固定：先做一次单行DB短读观察持久取消状态，再判 `elapsed >= max_total_seconds`。检查点覆盖：factory前、绑定后、每次发送前（`reserve_http` 内）、`invoke` 返回后、阶段间、评估前后、接受 `completed/needs_input` 前，以及 `close` 之后的最后检查。run缺失或探针读取异常 → 运行以执行错误停止（只报固定类别/安全异常类型），不因读不到状态而绕过准入继续外呼。
- `reserve_http(base_timeout)` 返回 `min(配置操作timeout, 剩余时间)` 且保证为正：默认操作配置5秒，不会把更短的配置放大，也不会关闭超时；HTTPX 的 connect/read/write/pool 四个操作都使用该值。已准入的尝试计数不退还。
- 晚到分类：已准入的响应、评估或收尾在总deadline到达后返回，且没有更早主失败 → `failed` + `budget.status=exhausted` + `exhaustion_reason=deadline` + `BUDGET_EXHAUSTED`，`result=null`、`quality_status=unverified`，保留实际 `elapsed_seconds` 与已有证据；**不接受** `completed/needs_input/verified` 晚结果。普通单操作timeout但总deadline未到 → 仍保持原 timeout/provider/format 分类。已有主失败不被后续清理或时间检查覆盖（清理越过deadline也不改写原失败）。
- 新耗尽LIVE必填 `exhaustion_reason`（`call_limit` 或 `deadline`）；历史run可缺该键，读取时按原JSON返回、不补造。取消胜出时删除该键。
- 本契约不保证挂起的同步调用在90秒内强制返回；只保证在可观察边界后停止新请求并拒绝晚结果。清理（close/解绑）本身也可能越过deadline，此时过期终态同样被拒绝。

```json
{"mode":"live","status":"failed","quality_status":"unverified","result":null,
 "budget":{"max_tool_calls":40,"tool_calls":4,"max_total_seconds":90,
           "elapsed_seconds":90.2,"status":"exhausted","exhaustion_reason":"deadline"},
 "issues":[{"code":"BUDGET_EXHAUSTED","severity":"blocker","message":"live runtime deadline exhausted"}]}
```

数字仅为示例，不是已测生产延迟；完整响应还含 `run_id/request/state/events` 等字段。

### 6.6 LIVE取消契约、原子终态与检查后竞争（票2）

- 取消入口仍是 `POST /api/v1/travel/runs/{run_id}/cancel`，运行中的LIVE run可取消。创建与LIVE修订的同步核心通过已安装 Starlette 的 `run_in_threadpool` 执行：原POST继续等待终态，但同一进程同一事件循环仍能受理**同键同载荷重放**（取得已创建 `run_id`）、取消与 GET；重放不新建 factory、不发HTTP、不新增完成事件。
- 取消确认在**一个短事务**内同时归一 `status=cancelled`、`budget.status=cancelled`、`quality_status=unverified`、`result=null`，并删除 `exhaustion_reason`；保留已持久化的 `tool_calls`、`elapsed`、证据与原有 issues 诊断（不重置、不伪造）。最终保存用**另一个短事务**重新读取持久状态：若取消已在竞争中提交，则对含实际计数/elapsed/证据的快照做同样归一后一次提交，并返回 canonical 数据；GET 与同键重放不会看到 `cancelled` 与 `verified/ok` 混合的中间态，也不存在“先提交再修补”。取消确认时若本次run的最新计数尚未落盘，读出的是当时已持久化的值；本次run的实际计数/elapsed/证据由原等待POST的最终保存写入。
- 已提交的业务失败先于取消时，取消API仍按 terminal 返回 409 `RUN_NOT_CANCELLABLE`。
- LIVE 取消响应与 `CANCELLED` 事件按实际 `mode=live` 描述，不携带 `REPLAY_NOTICE`，不声称没有远端调用或已撤回在途请求；只说明取消已记录、将尽力停止后续发送、已发送尝试可能仍完成。响应片段示例（还含 `run_id/replay_notice/executed_stages/events`）：

```json
{"mode":"live","status":"cancelled",
 "budget":{"max_tool_calls":40,"tool_calls":0,"max_total_seconds":90,
           "elapsed_seconds":0.0,"status":"cancelled"},
 "quality_status":"unverified","result":null,
 "message":"已记录取消：将尽力停止后续发送；已发送的尝试可能仍完成或返回，不声称撤回在途请求，也不保证立即返回。"}
```

（片段；示例中的计数是取消确认时已持久化的值，最终快照以实际计数/elapsed/证据为准。）

- 检查后竞争：取消确认与发送之间存在窗口，已提交的在途请求可能仍返回；系统只保证下一次边界检查停止新发送、最终终态一致，不承诺严格线性化或强制撤回。取消探针只持有单行DB短读，HTTP 与 `close` 都不在DB锁内。
- replay 取消行为保持原样：`mode=replay` + `REPLAY_NOTICE` + 原回放说明与文案。


## 7. 测试

```powershell
$env:TRAVEL_REPLAY_NO_AUTOSTART='1'
python -m pytest -q -p no:cacheprovider tests/test_amap_tools.py tests/test_live.py tests/test_live_admission.py tests/test_live_deadline_cancel.py
# 73 passed（高德离线 14 + live API 13 + 发送前准入/资源闭环 23 + deadline/取消/loopback 23）
python -m pytest -q -p no:cacheprovider
# 134 passed（回放 61 + 高德离线 14 + live API 13 + 发送前准入/资源闭环 23 + deadline/取消/loopback 23）
```

每个测试用 pytest fixture 在 `data/pytest/` 下建一次性 SQLite（或在进程内用 `httpx.MockTransport`），不共享库、不出网。离线测试覆盖：唯一匹配、同名歧义、空结果、Key 回收、超时、坏坐标、天气日期覆盖/不覆盖、路线时长距离、营业时间有/无；发送前准入（limit=0/1/2/40、第N+1次不命中handler、失败尝试计数、本地0消耗）、批次中断保留子证据、同键重放不重执行、自有/借入client清理、bind-v-bind / bind-v-close 并发，以及同一对象连续两次失败 bind 后两次清理均不触碰原 owner（client 仍 open、物理关闭 0 次、原 run 仍可发送）。deadline/取消新增：假时钟0/90边界与取消优先、剩余1秒与0.25秒配置下四类操作timeout、UTC墙钟跳变、探针缺失/异常不发送且不泄露原始异常串、factory前0预算、晚到响应/评估/收尾拒绝、普通timeout保持原分类、主失败不被时间检查覆盖、幂等重放不建runtime、已提交失败取消409；以及进程内真实loopback（127.0.0.1）并发创建与修订：等待期间同键重放取 run_id（factory/HTTP/完成事件增量0）、原cancel入口可达、检查后竞争下独立连接GET与重放始终读到归一快照、下一handler不命中，且取消响应/事件标LIVE。**没有真实网络请求**，全部用合成凭据 `synthetic-example`，不用真实sleep制造90秒。


## 8. 下一步

1. 你完成高德账号注册并创建 Web 服务 Key（手机/实名校验由你本人完成）。
2. 设置 `AMAP_API_KEY`，运行 `scripts/amap_probe.py`。
3. 把探测结果（成功/错误码/质量状态）写入验收记录；`POST /api/v1/travel/live-runs` 已实现，设置 Key 后可直接调用。4. 无 Key 时端点返回 503 `LIVE_NOT_CONFIGURED`，不会创建假成功运行。
4. 在控制台核对配额与 QPS；不要用循环压测。
