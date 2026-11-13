# LIVE运行预算与资源边界

状态：2026-11-10冷审修订候选，待增量复核/真人设计门；产品未实现。来源：统一任务T11及用户要求继续开发，不冒充已批准上线。

## Why

LIVE目前在工具返回后才统计内部HTTP，批内已经发生的超发无法阻止，且超限批次未完整入账。本轮离线复现将上限设2，实际传输3次、持久化2次；同时没有运行deadline，adapter也未提供顶层期待的close。需要把单次运行的请求准入、时间和资源收尾作为一个完整契约。

证据：[baseline-overshoot.json](evidence/baseline-overshoot.json)、[decision-memo.md](decision-memo.md)。

## What Changes

- 在每次实际HTTP尝试前检查并预占预算，包含weather/hours/matrix内部循环；失败尝试计数、无HTTP的工具不虚增。
- 沿用40次/90秒/单操作5秒默认值，以单调时钟deadline控制新请求与结果接受；把剩余时间传给HTTPX，并观察取消。
- [spec-review-amendment COLD-001/002/003/004] 保留截止前已成功的批内子证据；LIVE取消确认及最终快照同事务归一；所有失败诊断脱敏；自有client进入closing后拒绝重绑定。
- 持久化实际消耗与耗尽原因；拒绝晚到结果，同键重放不再次外呼。取消推荐方案为线程执行同步核心，原POST仍等待完成；并发同键同请求重放取得已有run_id后使用原取消API，不引入提前202后台平台。
- 明确adapter/client拥有权、构造失败清理、解绑和幂等close；关闭异常不能阻止主结果落库。
- **BREAKING（内部注入协议）**：LIVE注入适配器必须显式绑定运行guard，缺少协议时在调用工具前失败；更新本项目假适配器，不以事后计数兼容掩盖未受控外呼。
- 使用MockTransport、假时钟和关闭计数验证，不需要真实Key或额外平台。

## Capabilities

### New Capabilities

- `live-runtime-control`：单次LIVE执行的HTTP准入、协作式deadline、取消观察、计数持久化与资源拥有权。

### Modified Capabilities

无。已运行`openspec list --specs`，本项目新初始化的spec目录为空；不把旧Markdown实现说明假装已有权威spec。

## Success Metrics

1. 超发与计数一致性 — 已复现limit2/发送3/持久化2 → 发送最多2且持久化尝试数等于发送准入数；默认40同理 — MockTransport handler计数、client计数和保存run三方对账，包含批内第N+1次。
2. 过期结果接受 — 当前源码无运行deadline → 假时钟在deadline及之后接受completed结果数为0，后续HTTP发送数为0 — 发送前、返回后、阶段间与终态接受检查；不是90秒强制返回SLA。
3. 清理与结果保存 — 当前adapter无close且清理异常可跳过save → 7类拥有资源路径均有清理尝试，借用client关闭数0，重复close不重复关闭，关闭抛错仍可读主结果 — success/provider_error/budget/deadline/cancel/constructor_failure/cleanup_failure故障注入。

## Non-Goals

- 不将同步LIVE改为后台worker或进程隔离；假设此次要求为发送/结果准入deadline而非严格墙钟返回SLA，若不成立必须重新定执行模型后再实现。
- 不改replay六阶段事务/恢复、不做readiness/统一日志/有向路线/模型接入；假设这些不影响单次LIVE准入和关闭的可验收性，必要耦合缺陷在评审中再裁定，原T12/T13/H11/P17保留。
- 不做真实高德联调、供应商容量或费用结论；假设可用离线传输层证明客户端不超发，供应商计费与实际效果另验。

## Impact

Python/FastAPI后端；现有httpx、SQLite。影响`app/live.py`、`app/amap_tools.py`、`app/main.py`、`app/store.py`及新runtime模块，更新离线/假适配器测试与LIVE文档。公共路径、请求体和HTTP202入口保持；预算对新耗尽LIVE增加必填原因（旧记录可缺失），默认值有现有代码来源；无SQLite列迁移。

```text
POST /live-runs / revisions -> live编排 -> runtime准入/时钟/取消
                                    |          |
                                    v          v
                               AmapAdapter -> AmapClient -> httpx
                                    |              |
                                    +---- close ---+
                              最终预算/结果 -> Store
```

## Priorities

| 优先级 | 必交付结果 |
|---|---|
| P0 | 逐HTTP预占与计数对账；deadline/取消边界；晚结果不当成功 |
| P1 | 明确拥有权与所有出口清理、清理错误仍保存结果；回归和说明同步 |

优先级只用于实现顺序，以上均属本change，不因P1就省略。

## Stakeholders and Dependencies

用户/面试候选人关心可解释的真实工程行为；主助手负责核证/实现建议，真人保留设计和新PR合并决定。外部高德是潜在计费依赖，此轮所有请求均由MockTransport拦截；不读历史Key，不注册账户。

## Assumptions and Open Questions

- 默认每run独立adapter/client；若共享client，必须拒绝同时绑定多个active run，不能共享预算。
- SQLite正常可写时主结果能落盘；磁盘坏/事务失败不在此冒充容灾，原有分次run/event提交边界仍披露。
- 设计门待确认：协作式deadline（推荐，代价是不能强制打断挂起同步I/O）是否满足本次目标；若必须严格90秒返回，采用独立可终止执行边界重新设计。负责人：主助手整理证据、真人拍板；截止：实现前。

- [spec-review-amendment DQ-002] 推荐在真实单进程API中可发起取消：创建/修订移出事件循环执行，调用者用同一幂等键重放读取已创建run_id再取消；不要求原创建请求提前返回。备选为仅旁路持久状态观察（用户无法在同进程API及时取消）。此行为取舍与协作式deadline一起在真人门判断，未批准前只是设计候选。

## External Service Cost

本轮新增真实供应商请求0；发送尝试数是保守预算，不是收费凭证。生产单价/账号配额未核对，不能报告真实费用或节省率；没有费用额度授权，不调用收费渠道。

## Compliance

按已调用的sdflow-spec和项目AGENTS推进，纪要hash已冻结；已核D-1/D-3/D-4/D-5/D-6，无DB schema迁移故不触发D-2。触发TG-01/05/06/07/08/09/10/12/14/15/16/17/18/19/20/21/22/23/24/26/28，设计审应覆盖backend、devex及对抗/接地。没有产品LLM消费，不触发TG-27；前端与新架构平台不在此次改动。
