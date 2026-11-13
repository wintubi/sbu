---
ship-gate:
  design_approved: true
  reviewed_sha: 1599aa286ab35a26dda880db737e1cce04c85dc6b62e4ff8d96d32d64ed81898
  reviewed_manifest: MTAwNjQ0IGJsb2IgYWU1YWViOGFjMzQxM2FiNDVkYTY1NjlkZmJlZTc5N2FkNDdmMTc3MglvcGVuc3BlYy9jaGFuZ2VzL3RyYXZlbC1ydW50aW1lLWJ1ZGdldC9kZXNpZ24ubWQAMTAwNjQ0IGJsb2IgYjljZWJkZmIwYWQzOTE2Yjk0Mjg3OGM2ZDQ5ZWIwY2M5OTM4MmQzMwlvcGVuc3BlYy9jaGFuZ2VzL3RyYXZlbC1ydW50aW1lLWJ1ZGdldC9wcm9wb3NhbC5tZAAxMDA2NDQgYmxvYiBjMTdmNmQ4Yjk4OWZiNjEwZGFhYzMyMTRlNTRjMGUyY2UwNmVhMDcxCW9wZW5zcGVjL2NoYW5nZXMvdHJhdmVsLXJ1bnRpbWUtYnVkZ2V0L3NwZWNzL2xpdmUtcnVudGltZS1jb250cm9sL3NwZWMubWQ=
---
# T11 LIVE运行控制设计评审

状态：冷审、增量及最后定点复核完成，发现已在规格层关闭；真人已批准推荐组合，产品待实现。日期2026-11-10（Asia/Shanghai）。

## 评审执行与可信边界

- 受审基线b4a08e4735ac09c7d38886901fbd1132915f52a7；原[冷审结果](review/cold-findings.json)完整保留，包含27处原文引文和两项行为决策。当前四件套是[派发记录](review-dispatch.json)列出内容hash的修订候选，不混称原盘面已批准。
- 用户11月10日明确要求不继承聊天上下文的子代理审设计。实际使用DSH fresh child、magpie-responses/codex/gpt-6.1-sol、请求high；没有fork主会话，没有作者总结，只给目标和文件路径。实际effort/费用未采集。后续窄复核仅继承该评审者自己的冷审历史。
- resolver按清脏/执行/退出码/eval校验真实返回HOST=unknown。native sdflow多镜fanout和design-voice/hr-tg跨模型均未执行；本报告不冒充完整native多镜或跨模型报告。unknown路径主助手做范围/工程补核，用户另行要求的DSH单一独立综合冷审作为补充；此能力局限在风险门明确呈现。
- 四条原始finding以evidence_pack交给权威findings_ref_check时为uncheckable（该脚本的正常定义），未擅称直接pass；再将主引用/证据逐行展开，27条均pass，见[引用核验](review/citation-check.json)。M1的单引用也pass。引文真实性不机械保证语义正确。
- 主助手独立用SQLite :memory:/MockTransport亲验取消混合态与合成Key持久化，[主审复现](review/main-verification.json)。无真实Key/供应商、无落地数据库、未跑全量pytest；这是旧行为核证，不是修复验收。
- config metrics.enabled=false，不落lens-metric、不编造token/费用。主助手的[补充M1](review/main-findings.json)属于作者补核，不是第二个独立镜。

<!-- sdflow:step1-broad-review v1 mode="main-session" -->
<!-- sdflow:hr-tg v1 hit="TG-06,TG-07,TG-08,TG-09,TG-16,TG-17,TG-26" declared="TG-01,TG-05,TG-06,TG-07,TG-08,TG-09,TG-10,TG-12,TG-14,TG-15,TG-16,TG-17,TG-18,TG-19,TG-20,TG-21,TG-22,TG-23,TG-24,TG-26,TG-28" evidence="LIVE预算JSON与API错误合约、外部HTTP/取消/拥有权共享状态；无DB表迁移" -->
<!-- sdflow:declared-sites v1 declared="design-voice,hr-tg" -->
<!-- sdflow:outside-voice v1 site="design-voice" host="unknown" runner="none" reason_code="host-unknown" findings="0" truncated="false" -->
<!-- sdflow:outside-voice v1 site="hr-tg" host="unknown" runner="none" reason_code="host-unknown" findings="0" truncated="false" -->

## 决策登记区

### 拍板三问

- Q-scope 范围划界认不认？自答：只做单次LIVE成本/时间/证据/资源契约；原POST等待、无后台平台。推荐把真实API取消纳入，协作式deadline不叫90秒硬返回；见proposal Non-Goals及DQ-001/002。用户已在t11_design_gate批准推荐组合。
- Q-deps 依赖/顺序认不认？自答：tasks的三张建议票：发送准入/正常生命周期 → deadline与真实取消/原子终态 → 异常清理与全回归。15项仍未实现，测试与说明随各票交付；P18/P19为候选，不扩张本T11 PR。用户已在t11_design_gate批准推荐组合。
- Q-risk 风险赌注与对策认不认？自答：上方hr-tg为已声明触发的机械交集；通过真实传输计数、批内子证据、短事务、closing占位和固定错误文本防失真。剩余同步I/O硬中断、在途撤销、崩溃账本/生产容量未承诺；本次仅同模型冷审，未获得native跨模型能力。用户已在t11_design_gate批准推荐组合。

<!-- sdflow:gate-questions v1 q="scope,deps,risk" -->

### 自动采纳的技术修订

| ID/严重度 | 原始问题与触发后果 | 主审裁决及修订 | 验收锚 |
|---|---|---|---|
| COLD-001 high/P1 | hours/matrix内部成功结果存在局部变量；后续guard抛错越过聚合返回点，证据丢失 | 采纳；截止前成功的规范化leg/营业子证据通过回调即时交编排，仍不把部分批次标完整；不存原始URL | tasks1.2/2.2，LRC-04批内中断后重读来源/时间/payload；真实MockTransport首个成功、第二次拒绝 |
| COLD-002 high/P1 | SQL仅护status，先保存后修补可见cancelled+verified+budget.ok，预算主分类不一致 | 采纳；LIVE取消确认和最终保存各自在短事务中归一整个快照；取消先提交胜出，若终态先提交则取消拒绝；原失败留issues，删除耗尽主分类键 | tasks2.4/3.4，取消ack/最终写入间并发GET及同键重放，不只验最终POST；主助手已复现旧缺陷 |
| COLD-003 high/P1 | 普通HTTPError的str(exc)可把Key/query写入ToolResult/issues/state，cleanup-only测试漏掉 | 采纳；保留错误状态分类，全部失败文本为固定类别/安全异常类型，provider.info不原样回显，校验数字infocode；覆盖HTTP/执行/cleanup三路径 | tasks2.2/3.2，扫描API、持久state、事件；主助手已用合成Key复现旧泄漏 |
| COLD-004 medium/P2 | 解绑到物理close期间另一个run可重绑，旧owner再关新run的client | 采纳；短锁先标closing并释放本run绑定，锁外close；新bind拒绝closing/closed，失败close不重新开放，借用只解绑 | tasks1.3/3.1，bind-v-bind和bind-v-close barrier；没有声称在尚未实现接口上已跑测试 |
| M1 low/主助手补核 | 新耗尽reason被写成可选，但场景承诺可区分两种原因 | 采纳；新耗尽LIVE必填，历史记录可缺失且原样返回 | LRC-04正文及tasks2.2；无历史回填 |

这五项是满足已给目标的可逆技术补齐，没有因“现状不支持”砍目标，也不推给T12/P17后再假装T11闭环。所有原始发现保留；本轮没有被静默裁掉的finding。

### 真人已批准的推荐组合

**DQ-001 截止语义。推荐协作式90秒。** 系统：复用单调预算与HTTPX剩余操作timeout，无新进程平台；用户：截止后停止新请求/拒绝晚结果，但挂起调用或close可能更久；开发循环：假clock/MockTransport可确定性验收，局限持续可见。备选为严格90秒墙钟返回，需要可终止执行边界及跨边界结果/资源协议，须重设计。主次：本地项目先确保准入与结果诚实，不把它命名为硬SLA。可行性锚：已读Amap集中发送点和HTTPX官方超时说明（纪要C5）。

**DQ-002 取消可发起性。推荐真实同进程API取消。** 系统：创建与LIVE修订在解析后通过已安装Starlette run_in_threadpool执行同步核心；原POST仍等待，不引入worker/提前202。用户：持有Idempotency-Key和原载荷，在等待期间同键重放取得已有run_id，再走原cancel/GET；无幂等键则原请求完成前仍不保证取得ID。开发循环：两入口增加真实loopback并发POST/重放/cancel/GET，保持factory/外呼重放增量0。备选为仅旁路持久状态观察，代价是普通API用户可能根本无法在运行中取消，必须显式接受较窄行为。主次：取消的用户可用性优先，采用已有幂等接口减少新协议。

DQ-002可行性亲验：已读本机Starlette concurrency.py:35–37，helper调用anyio.to_thread.run_sync；已读live.py的同键返回位于factory之前及Store.create_run_atomic的幂等事务。当前路由仍同步阻塞，完整行为未实现/未验收，不能用可行性对读冒充真实loopback通过。原审的事件循环探针顺序见cold-findings。线程池有容量边界，不据此承诺生产并发能力。

### 已裁掉/延后

无裁掉finding。两项行为选择已获真人批准；P17结构化日志、T12 replay阶段事件原子性等独立结果继续原任务，不把本轮LIVE必需原子归一与错误脱敏推走。真实Key、供应商计费/准确率、领域gold、生产容量/灾备和本人掌握仍未验收。

## 修订与窄复核

[spec-review-amendment] 已针对四项COLD与M1修订proposal/design/specs/tasks，并更新config中的11月10日本次PR提交授权。冻结的阶段一纪要及原生成核验保留为各自时点证据，不冒充已重跑实现测试。

[第一轮窄复核](review/amendment-check.json)确认COLD-001/002/003/004全部closed_at_spec_level，新增阻塞0；6个工件hash及25处引用已由主助手独立核验。它补报两项局部P2残差：AMEND-001新耗尽原因的残留可选措辞、AMEND-002 LIVE取消响应/事件仍可能误标replay。两项均采纳并按建议修订，[最后定点复核](review/final-wording-check.json)确认文案/任务残差0、新矛盾0；主助手核验三份hash及六处引用通过，见[最终引用核验](review/final-citation-check.json)。AMEND-001是M1修订后的同一语义残留，合并记录，不算新增独立价值。第三次定点派发漏在发送前登记manifest，现按真实send_message/返回补记并披露，不能称预先完整派发清单；不影响已保留的独立结果，但也是本次非完整native编排的边界。所有“闭合”只指规格，不指产品修复。[派发记录](review-dispatch.json)记录模型、实际上下文、内容hash和返回文件。

## 完成与下一步

真人在t11_design_gate选择“按推荐方案继续（推荐）”，已批准范围/依赖/风险与DQ组合，权威anchor_writeback已写批准及内容锚；按ticket管线实现。实际决定见review/design-decision.json，未倒填历史业务门。用户已经授权完成后提交本次PR，未授权自动合并。GitHub CLI凭据失效属于提交认证问题，不阻塞本地规格/证据准备；没有因此读取或公开其他应用凭据。

收尾使用anchor_lint与openspec strict校验，评审页由官方render-review-page生成；报告及修订随spec-review本地checkpoint保存，提交号以git记录为准。当前没有“产品修复通过/今日PR已创建”的声明。
