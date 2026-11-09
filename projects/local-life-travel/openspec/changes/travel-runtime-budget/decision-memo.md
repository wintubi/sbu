---
schema_version: 1
change: travel-runtime-budget
branch: feat/travel-runtime-budget
generated_at: 2026-11-09T23:13:52+08:00
decision_hash: 37be910452bf
---

# 决策纪要 · travel-runtime-budget

状态：B-finalized，十条承重约束已核证，主助手实现选择已收敛；正式设计审查/真人设计门待执行，产品未实现。

## 目标态

让单次LIVE运行的HTTP尝试次数在真正发送前受预算控制、后续工作受运行deadline/取消控制，并在成功与异常路径可靠关闭自有客户端，结果与持久化计数保持可解释。

## 承重约束

- **C1 现有预算不能阻止超发** — 验证方式：真实AmapAdapter/AmapClient接MockTransport，max=2；观察到发送3次而持久化2次。证据锚：[复现JSON](evidence/baseline-overshoot.json)、[脚本](evidence/reproduce_budget.py)；`app/live.py:100–106`先执行后_record，`app/amap_tools.py:56–60`为集中发送点。此为本轮已运行的离线复现，不是推断。
- **C2 批内请求也必须受控** — 已读`app/amap_tools.py:238–256`天气可先查adcode再天气，`:280–300`hours逐POI detail，`:331–348`matrix逐腿；仅在工具方法前检查一次不够。所有这些请求最终经过AmapClient.get；guard应位于这里并同时在业务阶段边界检查时间/取消。
- **C3 默认预算已有来源** — `app/live.py:29,51–52`默认40实际HTTP计数字段，`app/domain.py:38–48`默认90秒及elapsed_seconds；沿用数值，修执行语义，不新增用户收费配置或成本承诺。
- **C4 生命周期责任当前不完整** — `app/live.py:290–306`只在adapter存在且有close时关闭；`app/amap_tools.py:36–54,130–145`client有close但adapter没有，且默认factory先创建client再构造adapter（`app/main.py:153–161`）。构造/关闭异常须一并处理；脚本调用者当前自己持有client，借入资源不能被无条件关闭。

- **C5 HTTPX timeout不是总墙钟** — 已核对[HTTPX官方超时说明](https://www.python-httpx.org/advanced/timeouts/)：connect/read/write/pool分别超时，read按数据块等待。目标应为单调时钟deadline、逐调用/阶段/终态检查及剩余时间传入HTTPX，不承诺强杀同步Python或撤回请求。若要求严格90秒返回，需可取消执行器/进程隔离另行决策，不能把当前方案冒充满足。
- **C6 幂等重放不能再外呼** — `app/live.py:279–287`已存在run在factory前返回；`tests/test_live.py:150–180,261–284`覆盖修订/重放。新guard只能在新创建的run建立，不重执行历史run、不重写已完成预算；旧SQLite列不迁移。
- **C7 取消来自持久状态** — `app/store.py:178–209`queued/running可取消，读取受短锁保护；`:211–230`保存仅保护cancelled状态。guard可通过短查询观察取消，在每个发送/阶段边界退出；不在DB事务内做HTTP，不保证取消与发送之间不存在检查后竞争，不扩展为撤销在途请求。
- **C8 注入适配器存在测试消费面** — 全项目grep已核对main.py、scripts/amap_probe.py、tests/test_amap_tools.py及test_live.py。FakeAdapter没有HTTP client，CountingAdapter只事后加数；内部工厂注入须更新为显式bind_runtime协议，不能悄悄按工具调用数冒充HTTP次数。未提供guard绑定的LIVE适配器在任何工具调用前失败，协议是内部开发契约变化，需要在文档和测试中说明。
- **C9 资源所有权须显式** — 生产工厂创建的client由运行拥有并关闭；独立脚本/测试注入client默认借用，adapter解绑guard但不擅自关闭。拥有权转移后构造失败同样由构造方清理；factory内部未交出的资源由factory负责，不承诺顶层能关闭从未返回的对象。
- **C10 交付范围内聚** — 只修单次LIVE执行的成本/时间/清理；T12阶段事件原子化、T13/H11健康语义、P17访问日志是独立可验收结果，原任务保留。运行guard和关闭是同一资源边界的开始/结束，不能只实现一个半闭环。依据：已读change-decomposition-standard与scope-cohesion-check，无混拼；不新增全局ADR（可逆且局部），项目没有CONTEXT.md，术语在本纪要内解释。

## 拍板决策

以下为用户已授权T11目标下的主助手实现选择，待正式设计审查和真人设计门；不冒充真人已逐项签批，也不据此实现产品。

- **D1 统一运行guard，位于AmapClient.get真正发送前** — 一个runtime对象绑定run预算、单调时钟、取消探针；reserve仅在允许发送时预占一次，失败也计数；_record只记ToolResult，不再max(1, HTTP差额)。砍掉仅在invoke前检查：hours/weather/matrix内部仍会超发；砍掉改httpx私有发送方法：无必要耦合实现内部。
- **D2 沿用40/90/5，定义协作式deadline** — 40为HTTP尝试上限；90秒从新运行开始执行（factory前）用单调时钟计时；单次HTTPX四种操作timeout为min(5秒,剩余时间)。调用返回后、阶段间、接收终态前再检查。达到时间上限不得将晚结果算completed；清理仍要进行，实际elapsed可以超过90，不宣称严格墙钟硬中断。砍掉每工具重置90秒；砍掉依赖系统UTC差值计运行时长。
- **D3 结果与计数可解释，复用现有HTTP入口** — 预算/总deadline耗尽为failed+budget.status=exhausted+issue BUDGET_EXHAUSTED，并增可选budget.exhaustion_reason=call_limit/deadline；elapsed_seconds记录实际处理时间。失败前工具证据保留，未完成/过期结果不标verified。普通HTTPX超时仍是工具timeout，可按原业务部分验证；同键重放只读旧结果。默认HTTP202不在本change改成异步调度。
- **D4 显式拥有权与幂等清理** — AmapAdapter提供bind_runtime和close；生产factory移交自有client，借用client默认不close；同一client不得同时绑定两次运行。构造失败清理已移交资源，close重复调用安全；关闭异常以脱敏RESOURCE_CLEANUP_FAILED警告留痕，仍保存主结果，不覆盖更早业务失败；完成前最后一次deadline/取消检查按原始主失败优先处理。
- **D5 离线验收必须到真实传输层** — 新增MockTransport计数和伪时钟测试：第N+1次不进handler、批内耗尽、失败计数、零HTTP工具不虚增、迟到响应、取消探针、解绑/close、关闭失败持久化和同键不再外呼；保留现有replay/离线工具/业务假适配器测试。砍掉只检查最终status的伪验收；不为本改动申请Key或压测供应商。

## 接受的边角

- 协作式deadline无法中断不返回的同步调用、连续分块响应或不可控close；根因是同步库和进程执行边界。生产高时效场景影响高，需要独立执行边界；本地切片先兑现“停止新请求/拒绝晚结果”，明确不叫强制总时限。不是因当前未出现就否定目标；若目标必须硬截止，则本方案应被设计门否决并改执行模型。
- guard检查取消后到HTTP发送有微小竞争窗口；不承诺撤销已提交发送，下一次边界看到取消即停止。需要严格线性化的发送/取消需另做协议，而非长期占SQLite锁覆盖网络。
- 计数表示准入的发送尝试，连接建立失败也消耗一次；不是供应商收费凭证。模型token、费用与真实供应商成功率均未知。
- 中断仅保证上次保存以来的纪要内容可能丢失，不声称零损失；阶段事件与最终run仍分次提交（T12），不冒充事务性outbox。

## 三镜代价

- 系统：新建一个小runtime模块并绑定client，不改DB表或replay编排；增加短取消读与每次发送前检查，避免全局共享预算；借用client生命周期更明确。
- 用户：超限/超时会更早停止且不会多发N+1次；迟到结果不再伪装正常完成。仍是本地同步LIVE，真实供应商效果未验证。
- 开发循环：假适配器需显式接入guard，新增测试学习成本；使用现有httpx/pytest，无新平台。3个垂直切片建议为HTTP准入、deadline/取消/持久化、资源关闭与端到端收尾，后两者依赖第一片。
- 主次：以请求准入和可核对结果为主，避免为演示引入进程调度平台；严格硬时限作为明确未满足能力等待设计门裁定。
