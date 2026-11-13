# LIVE运行预算与资源边界设计

状态：2026-11-10冷审修订候选，待增量复核/真人门，未实现。动机与可量化目标见[proposal.md](proposal.md)。本文的`app/runtime.py`与方法名均为拟新增接口；现有实现引用明确带原文件行号。

## Context

- 现有`app/live.py:100–106`在方法返回后按client.calls差额记账，`:73–80`超限直接抛异常，导致已发送超限批次没有入账。
- 现有集中发送点为`app/amap_tools.py:56–60`。POI、adcode/weather、hours detail、matrix腿循环均经过此方法；无需修改HTTPX私有API。
- `app/main.py:153–161`默认factory先分配client；`app/live.py:290–306`依赖adapter.close但当前adapter没有。注入factory只在本项目测试中消费，脚本自行持有并关闭client。
- `app/store.py:178–230`有条件取消和保存时cancelled保护，但LIVE本身没有逐发送取消探针。run和LIVE_FINISHED事件分次提交仍是已知边界。
- 原始复现见[evidence/baseline-overshoot.json](evidence/baseline-overshoot.json)：limit=2、handler=3、持久化=2。本次不是测试工具状态，而是校验真正发送点。

## Goals / Non-Goals

目标是单次LIVE的准入与收尾契约，不引入跨run共享的全局配额：HTTP尝试≤max；没有HTTP不消费；时限/取消控制新工作和结果接受；自有资源在所有出口有清理尝试；预算与主结果在正常SQLite条件下保存。

设计边界及可证伪前提：

| 边界 | 前提与失效时动作 |
|---|---|
| 沿用同步LIVE，不改后台编排 | 目标为协作式deadline，不是严格90秒内返回；若必须硬截止，本设计不能冒充满足，需改执行模型并重评 |
| 不改SQLite表与replay引擎 | 现有budget/state JSON可表示新信息；若需要逐请求崩溃不丢账，则须另做持久账本而非隐瞒 |
| T12/T13/H11/P17和有向路线另跟踪 | 不影响当前发送/关闭契约；若评审发现必需耦合，按change-decomposition标准裁定，不机械推走相关缺陷 |
| 不做供应商费用/准确率验收 | MockTransport足以证明本进程准入边界；不能证明供应商收到次数、扣费或真实效果 |

## Decisions

本change的决策全文、候选取舍与三镜代价见[decision-memo.md](decision-memo.md)；D1–D5为主助手按已授权目标提出的设计，真人设计门仍待执行。

## Components and Contracts

| 组件 | 职责和拟变动 | 不拥有的职责 |
|---|---|---|
| `app/runtime.py`（新增） | `LiveRuntime`持有budget、单调时钟、取消探针及规范化子证据回调；`check()`检查时限/取消；`reserve_http(base_timeout)`检查预占并返回timeout；截止前已成功的子证据即时交编排记录 | 不发HTTP、不持有DB长事务、不做重试 |
| `AmapClient` | `get()`在进入httpx前调用runtime准入；calls只在准入成功后+1；返回/异常后再次check；支持绑定/解绑runtime | 不把工具方法次数当HTTP；不隐藏预算异常 |
| `AmapAdapter` | `bind_runtime(runtime)`把guard绑定client；显式owns_client；close解绑并按拥有权关闭 | 不擅自关闭借入client；不让两个active runtime共享同client |
| LIVE编排 | 新run建立runtime、绑定adapter，阶段/结果检查，分类异常，finally清理/计时/保存并读回canonical run | 不执行replay恢复或自动重试 |
| Store | 复用创建幂等；LIVE取消确认及拟新增finalize_live_run在各自短事务中归一整个run快照，返回已提交canonical数据；保留事件接口 | 不增加列、outbox或逐HTTP崩溃账本；不改replay六阶段事务 |

内部注入协议：factory仍接city/transport并返回adapter，构造过程不得外呼；返回对象必须有`bind_runtime`和`close`，绑定失败不得调用任何工具。测试fake必须显式模拟逐HTTP准入。缺少协议失败为STAGE_EXECUTION_ERROR并保存；这是已声明的内部破坏性变更，不提供会静默绕过guard的fallback。

AmapClient在非LIVE独立脚本中允许未绑定runtime，仍保留原操作timeout；不能把脚本宣传为受本run的40/90约束。LIVE调用路径必须绑定，且生产factory返回独立client；共享/重入绑定应失败而非覆盖另一个运行的guard。

[spec-review-amendment COLD-004] client短锁原子维护runtime身份和open/closing/closed。自有资源清理先在锁内标closing并释放本run绑定，再在锁外物理close；bind拒绝active、closing、closed。关闭失败仍不可重用；借用资源只按身份解绑并可顺序复用。绑定失败清理不得改变/关闭另一个active run的client；HTTP/物理close不在短锁内。测试同时覆盖bind-v-bind和bind-v-close，不靠GIL假设。

## Runtime Data and Lifecycle

| 数据 | 旧→新语义 | 生命周期/持久性 |
|---|---|---|
| max_tool_calls | LIVE默认40不变 | 只读run限制；replay默认10不改 |
| tool_calls | 每工具后max(1,差额)→本run准入的HTTP尝试数 | 仅reserve成功时+1；最终保存，进程崩溃前未保存部分仍未知 |
| max_total_seconds | 原字段90→新run执行前建立单调deadline | 不按每工具重置；不拿UTC时间跳变计运行耗时 |
| elapsed_seconds | 当前LIVE未维护→真实单调时钟差 | 最终采样含收尾；可能超过90，不能据此声称硬中断 |
| status | ok/running/failed/exhausted等 | 耗尽/取消单独分类；最早主失败不被清理失败覆盖 |
| exhaustion_reason（新增JSON键） | 新耗尽LIVE必填call_limit或deadline；历史可缺失 | 取消胜出时删除耗尽分类键，原失败诊断保留在issues；不迁移历史或SQL列 |
| runtime指针/clock/取消函数 | 无→进程内对象 | 不序列化到request/state，不记凭据；close解绑，禁止跨run复用active绑定 |

[spec-review-amendment COLD-001] 批内已成功的leg/营业详情在完成规范化且仍在deadline内时，通过绑定的子证据回调即时交编排，保留source_ref、fetched_at和最小规范化payload。后续reserve抛错不能丢先前子证据；回调不递增HTTP计数，不把部分批次当完整成功。晚到子结果不进入有效事实；不存原始HTTP URL/凭据。单独脚本无回调时仍按原聚合返回，LIVE必须绑定该交付机制。

`tool_calls`这里指HTTP尝试，和replay工具次数分别解释。准入成功后连接失败仍计一次；不是供应商计费凭证。纯本地缓存、解析或返回空矩阵不预占HTTP。

## Admission and Deadline

1. 幂等创建命中旧run时，直接返回旧结果；不创建runtime/factory、不调用工具、不改旧计数。
2. 新run成功创建后、factory之前取monotonic开始值；`check()`先观察取消，再检查`elapsed >= max_total_seconds`。存储探针异常或run缺失也失败，不允许绕过检查继续发送。
3. factory和绑定后再check；`invoke`前后check仅处理时间/取消，不用它消费HTTP次数。
4. 每个AmapClient.get在实际发送前调用reserve：check→若attempts已等于max则抛call_limit→预占+1并将client.calls+1→计算timeout=min(当前配置操作timeout,剩余时间)→调用httpx。
5. 所有四种HTTPX操作timeout均为正且不超过上述值，默认配置5秒；不能把用户/测试配置的更短timeout放大。没有重试、自动重定向或隐式绕过guard的附加发送。
6. get返回或网络异常后再次check；若总deadline已到，运行级耗尽优先于把迟到响应当正常工具结果；若仍有时间，保持原timeout/provider/format状态分类，但文本按允许列表脱敏：HTTPError与顶层异常仅固定类别/异常类型，provider.info不原样回显，infocode仅保留校验后的数字代码；禁止str(exc)、带query URL或私人请求进入ToolResult/issues/事件。
7. 评估前、评估后、接受completed/needs_input终态前检查；finally仍尝试清理。若主路径尚未失败，收尾后最后check防止过期终态被接受；已有主失败不被后续清理/时间检查覆盖。

HTTPX是connect/read/write/pool各自计时，read按数据块等待，见[官方说明](https://www.python-httpx.org/advanced/timeouts/)。同一get跨多个阶段或持续有数据时仍可能超过剩余时间；本设计保证可观察边界后停止新请求和拒绝晚结果，不保证挂起同步调用90秒强制返回。

## Ownership and Finalization

- factory创建的生产client以owns_client=True明确移交，默认独立调用者提供client为借用；不靠“有close就都关闭”推断拥有权。
- 生产构造验证和绑定异常时，已移交的client由创建/构造路径清理；若自定义factory在返回对象前抛错，其未返回资源由该factory负责，顶层只能关闭实际取得的对象。
- [spec-review-amendment COLD-004] adapter.close的自有路径先短锁占closing并按身份解除本run绑定，再锁外尝试关闭；借用路径只解绑。重复清理不重复物理关闭；解绑失败仍尝试其余清理，closing/closed拒绝新绑定。不能让新run在旧owner解绑与关闭间取得client。
- 关闭抛错保留脱敏RESOURCE_CLEANUP_FAILED警告；关闭“尝试”不等于已释放成功，不用日志宣称资源一定释放。
- budget耗尽/总deadline异常：failed、budget.status=exhausted、reason、BUDGET_EXHAUSTED；清空未完成/迟到result，quality保持unverified，已有工具证据和准确尝试数保留。
- [spec-review-amendment COLD-002] LIVE取消确认在其现有短事务内同时归一status=cancelled、budget.status=cancelled、quality_status=unverified、result=null并删除exhaustion_reason；最终保存以单一短事务重新判断取消是否已提交，取消胜出则对包含实际计数/elapsed/证据的快照做同样归一，再一次提交返回canonical数据。已提交的业务失败先于取消则取消API仍按terminal拒绝；取消在最终提交前胜出，原内存失败仅保留为issues诊断，不能混入budget主分类。禁止先提交cancelled+verified/ok后再修补；GET/同键重放也不得看到混合终态。
- 取消确认到发送之间有检查后竞争，不能保证在途请求撤回；下一次边界观察即停止。短探针只持DB锁读状态，HTTP和close均不在DB锁内。
- 普通供应商失败沿用现有语义；清理异常不改写原失败，SQLite正常可写时仍保存run与LIVE_FINISHED。事件理由取canonical状态；两次提交非原子，T12另处理。

## Design Diagrams

```text
API/new revision -> create_live_run -> Store: 幂等创建
                         |
                         +-> LiveRuntime(budget, monotonic, cancel_probe)
                         |
                         +-> factory -> AmapAdapter -> AmapClient -> httpx
                         |                 |             |
                         |                 +-- bind -----+
                         |                               |
                         +---------------------- reserve/check
                         +-> ownership-aware cleanup -> elapsed -> atomic LIVE snapshot/canonical
```

```text
编排                 Adapter/Client             Runtime                 Transport
 |-- invoke ---------->|                          |                        |
 |                     |-- reserve_http -------->|                        |
 |                     |                         |check取消/time/count     |
 |                     |<-- timeout+预占 ----------|                        |
 |                     |-- HTTP一次 ------------------------------------->|
 |                     |<-- response/exception ---------------------------|
 |                     |-- check deadline ------>|                        |
 |<-- ToolResult或运行级异常 -----------------------|                        |
 |-- finally close --->|自有先标closing再物理close  |                        |
 |-- 最终check/保存并canonical读回 Store            |                        |
```

```text
queued -> running -> completed / needs_input
             |          ^ 接受前必须仍在deadline内、未取消
             +-> failed [call_limit/deadline/provider/bind/error]
             +-> cancelled [持久状态观察]
所有已取得adapter的出口 -> cleanup attempted -> elapsed/save/canonical
cleanup failure -> warning，保持主结果；已有主失败优先，不伪装已释放
```

```text
发送请求?
  check取消/time失败 -> 停止；不预占、不进Transport
  已到次数上限? 是 -> call_limit；不进Transport
  否 -> 预占一次 -> bounded HTTP -> 再check
       -> 总deadline到? 是: deadline失败 / 否: 原工具错误映射或有效数据
```

## Public Contract Examples

公共POST路径与结构沿用。以下请求示例发至`POST /api/v1/travel/live-runs`，Key只在服务进程环境中配置，不在请求体；测试由MockTransport接管。

```json
{"mode":"live","city":"北京","date":"2026-11-09","timezone":"Asia/Shanghai",
 "origin":"合成出发地","transport":"walking",
 "time_window":{"start":"2026-11-09T09:00:00+08:00","end":"2026-11-09T18:00:00+08:00"},
 "candidates":[{"name":"合成甲","stay_seconds":600},{"name":"合成乙","stay_seconds":600},
               {"name":"合成丙","stay_seconds":600}]}
```

以下为响应片段而非完整API响应。HTTP202仍可能返回failed，不能当异步worker证明。

```json
{"mode":"live","status":"failed","quality_status":"unverified","result":null,
 "budget":{"max_tool_calls":40,"tool_calls":40,"max_total_seconds":90,
           "elapsed_seconds":2.5,"status":"exhausted","exhaustion_reason":"call_limit"},
 "issues":[{"code":"BUDGET_EXHAUSTED","severity":"blocker","message":"live HTTP attempt limit exhausted"}]}
```

```json
{"mode":"live","status":"failed","result":null,
 "budget":{"max_tool_calls":40,"tool_calls":4,"max_total_seconds":90,
           "elapsed_seconds":90.2,"status":"exhausted","exhaustion_reason":"deadline"},
 "issues":[{"code":"BUDGET_EXHAUSTED","severity":"blocker","message":"live runtime deadline exhausted"}]}
```

数字只为示例，不是已测生产延迟。新耗尽LIVE必填exhaustion_reason，非耗尽与历史记录可缺失，取消胜出删除该键；旧run按原JSON返回。同键同请求不调用factory；同键改请求仍409；缺Key仍503且不创建假成功。

[spec-review-amendment AMEND-002] 取消响应和CANCELLED事件按实际run.mode描述：LIVE返回mode=live，不携带REPLAY_NOTICE，不声称没有远端调用或已经撤回在途请求；只说明取消已记录、将尽力停止后续工作，已发送尝试可能仍完成。replay保留原回放说明；创建/修订真实取消烟测均断言模式与文案。

## Failure Modes and Observability

| 触发 | 状态/可见证据 | 资源与后续 |
|---|---|---|
| 第N+1次准入 | failed/exhausted/call_limit；tool_calls=N | 第N+1次handler命中0；清理保存 |
| HTTPX单操作超时但未过总deadline | 原ToolResult timeout | 已准入计数不退还；按原业务规则处理 |
| 返回/评估/收尾已过deadline | failed/exhausted/deadline；不接受晚结果 | 没有后续HTTP；仍清理 |
| 观察到取消 | cancelled，未完成result为空 | 不再启动新工作；已发送不能撤销 |
| 缺绑定协议/重复active绑定 | STAGE_EXECUTION_ERROR，工具调用0 | 清理已取得对象，保留独立预算 |
| 拥有权转移后构造失败 | 原执行错误 | 创建方清理自有client；无未跟踪资源丢给顶层 |
| close/unbind抛错 | RESOURCE_CLEANUP_FAILED警告，仅异常类型 | 仍尝试其余清理并保存主结果；释放情况未知 |
| Store写入失败 | 原存储异常可见 | 不宣称业务已持久化/可恢复；不自动重发供应商 |

观测复用run_id、budget、issues、ToolResult与LIVE_FINISHED。此change不建立指标平台；可从保存结果定位call_limit/deadline/cleanup类别，日志不得包含Key、带query的供应商URL或完整私人请求。取消DB探针异常只报固定分类/异常类型，不拷原始异常串。模型token、费用未采集。

## Nonfunctional and Security Requirements

- 发送上限：默认≤40；所有内部循环同一guard；测试limit=0/1/2/40边界，不用elapsed换算QPS。
- 时间：默认90秒准入deadline，HTTPX四操作各≤min(配置timeout,剩余时间)；clock可注入，UTC跳变不影响；无真实sleep等90秒测试。
- [spec-review-amendment DQ-002 推荐候选] 隔离：每run独立runtime，禁止覆盖active/closing/closed绑定。创建和LIVE修订在async入口完成解析后用已安装Starlette run_in_threadpool执行同步核心，释放事件循环；原请求仍等待终态，不改成worker/提前返回。调用者持有Idempotency-Key及原载荷，可在等待期间同键重放拿到已创建run_id，再调用原cancel API。短事务/网络分离；用真实loopback并发POST/重放/cancel/GET验证，不能只测旁路DB。线程池有容量边界，不据此宣称生产并发能力或硬中断；若无幂等键，原同步创建完成前仍无run_id保证。
- Key只在环境/HTTPX请求query；测试用synthetic-example，MockTransport不出网；错误/证据不回显真实Key。外部POI文本只作数据，不执行指令。无新身份/数据公开许可结论。

## Migration Plan

1. 独立worktree以6a78560为基线，先设计审查与真人门；本地checkpoint不等于部署。
2. 实现guard及协议后更新内部fake；运行传输层边界测试、现有88项回归和无Key503测试。新增测试总数以实际输出为准，不先写通过。
3. 用独立SQLite副本跑API幂等/取消/关闭异常；保存每项命令、结果、发送计数和限制。
4. 更新LIVE-AMAP/README/API说明，保留真实未联调、协作式deadline局限；仅在合并发布事实成立后更新私人面试稿的“当前版本”，不拿分支实现倒填main。
5. 回退为代码回退：无SQL列迁移，新字段只是budget JSON附加项，旧代码可忽略；历史已失败运行不自动重执行。任何新PR推送/合并仍需明确授权。

## Risks / Trade-offs

- 同步I/O可能超过deadline才返回 → 明确非硬中断，返回后拒绝晚结果；硬SLA需求须改变执行边界。
- 同时使用一个client可能串预算 → active绑定检测失败；避免全局client单例，借用资源解绑后才能复用。
- 取消与发送存在竞争 → 边界检查+Store保护，承认在途窗口，不用SQLite锁包网络。
- 关闭失败导致资源未完全释放 → 明确warning且主结果可读，不能把一次close尝试证明为无泄漏。
- JSON持久化与事件分次提交 → 不宣传exactly-once/崩溃账本，T12后续处理。

## Review Amendment Decisions

[spec-review-amendment] COLD-001/002/003/004和M1均采纳，原始引文/核验与取舍见spec-review-report.md。两项真人行为判断是协作式deadline、以及上述真实API取消候选；推荐后者的线程执行+已有幂等重放路径，不增加查Key端点，不默认为提前202后台调度。已对读本机Starlette concurrency.py:35–37，helper通过anyio线程执行；已读LIVE同键返回在factory前的现有代码。这里没有声称该方案已实现或已获批准。

## Slicing Advice

建议3张垂直切片：HTTP发送准入与真实计数（独立MockTransport闭环）；deadline/取消/终态保存（依赖准入）；拥有权/关闭异常/默认factory与全回归收尾（依赖准入，统一与第二票验证）。不按新模块拆水平票，不用增加脚手架票凑数量。任务追溯和测试路径映射见tasks.md。

## Compliance

已逐条核项目AGENTS、config与canonical workflow：D-1源码已grep/阅读；D-3各排除附可证伪前提；D-4声明HTTP操作timeout与Store写失败/回退边界；D-5见proposal量化三指标；D-6不改跨项目模型/原本体/原始数据，LIVE预算JSON语义对外明确；无SQL列迁移，D-2不适用。TG触发见proposal，backend/devex需审，非新系统无需C4部署平台图。

既有架构为本地单进程、确定性domain与双执行路径；本设计不以新runtime混入replay。没有需要新ADR的不可逆全局决策，也不新建CONTEXT文件；完整取舍只在纪要。旧设计门、本change设计门、真实供应商和本人演练分别记录，CLI valid不作为实现或设计批准证据。
