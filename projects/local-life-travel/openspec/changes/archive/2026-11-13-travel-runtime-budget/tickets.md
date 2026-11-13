---
impl-pipeline: tickets
---

## Global Constraints

内部注入协议：factory仍接city/transport并返回adapter，构造过程不得外呼；返回对象必须有`bind_runtime`和`close`，绑定失败不得调用任何工具。测试fake必须显式模拟逐HTTP准入。缺少协议失败为STAGE_EXECUTION_ERROR并保存；这是已声明的内部破坏性变更，不提供会静默绕过guard的fallback。

AmapClient在非LIVE独立脚本中允许未绑定runtime，仍保留原操作timeout；不能把脚本宣传为受本run的40/90约束。LIVE调用路径必须绑定，且生产factory返回独立client；共享/重入绑定应失败而非覆盖另一个运行的guard。

[spec-review-amendment COLD-004] client短锁原子维护runtime身份和open/closing/closed。自有资源清理先在锁内标closing并释放本run绑定，再在锁外物理close；bind拒绝active、closing、closed。关闭失败仍不可重用；借用资源只按身份解绑并可顺序复用。绑定失败清理不得改变/关闭另一个active run的client；HTTP/物理close不在短锁内。测试同时覆盖bind-v-bind和bind-v-close，不靠GIL假设。

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

观测复用run_id、budget、issues、ToolResult与LIVE_FINISHED。此change不建立指标平台；可从保存结果定位call_limit/deadline/cleanup类别，日志不得包含Key、带query的供应商URL或完整私人请求。取消DB探针异常只报固定分类/异常类型，不拷原始异常串。模型token、费用未采集。

## Nonfunctional and Security Requirements

- 发送上限：默认≤40；所有内部循环同一guard；测试limit=0/1/2/40边界，不用elapsed换算QPS。
- 时间：默认90秒准入deadline，HTTPX四操作各≤min(配置timeout,剩余时间)；clock可注入，UTC跳变不影响；无真实sleep等90秒测试。
- [spec-review-amendment DQ-002 推荐候选] 隔离：每run独立runtime，禁止覆盖active/closing/closed绑定。创建和LIVE修订在async入口完成解析后用已安装Starlette run_in_threadpool执行同步核心，释放事件循环；原请求仍等待终态，不改成worker/提前返回。调用者持有Idempotency-Key及原载荷，可在等待期间同键重放拿到已创建run_id，再调用原cancel API。短事务/网络分离；用真实loopback并发POST/重放/cancel/GET验证，不能只测旁路DB。线程池有容量边界，不据此宣称生产并发能力或硬中断；若无幂等键，原同步创建完成前仍无run_id保证。
- Key只在环境/HTTPX请求query；测试用synthetic-example，MockTransport不出网；错误/证据不回显真实Key。外部POI文本只作数据，不执行指令。无新身份/数据公开许可结论。

已逐条核项目AGENTS、config与canonical workflow：D-1源码已grep/阅读；D-3各排除附可证伪前提；D-4声明HTTP操作timeout与Store写失败/回退边界；D-5见proposal量化三指标；D-6不改跨项目模型/原本体/原始数据，LIVE预算JSON语义对外明确；无SQL列迁移，D-2不适用。TG触发见proposal，backend/devex需审，非新系统无需C4部署平台图。

既有架构为本地单进程、确定性domain与双执行路径；本设计不以新runtime混入replay。没有需要新ADR的不可逆全局决策，也不新建CONTEXT文件；完整取舍只在纪要。旧设计门、本change设计门、真实供应商和本人演练分别记录，CLI valid不作为实现或设计批准证据。

### Task 1: HTTP发送前准入、真实计数与正常资源闭环

**Blocked-by:** none
**R-ID:** LRC-01, LRC-04, LRC-05, LRC-06, LRC-07, LRC-09

交付真实适配器通过API创建、查询、耗尽和幂等重放的离线闭环。本票落实HTTP准入、次数耗尽、协议和正常拥有权；deadline/实际API取消在票2交付，异常资源矩阵与最终材料在票3完成，不把本票通过当全部需求完成。对应原实现任务1.1–1.5。

- [x] 每run独立控制，POI、adcode/weather、营业详情和路线内部循环逐HTTP发送前预占；limit=0/1/2/40及恰好用完均在真实MockTransport发送点验证，第N+1次不命中handler；连接、timeout、provider或格式错误的已准入尝试计数，本地缓存/解析/空矩阵计0，移除事后max(1,差额)替代记账。
- [x] 批次中断仍保存此前已规范化的成功leg/营业详情及来源、时间和最小payload；计数与准入对账，部分批次不成为完整成功，不返回未完成可行方案；call_limit耗尽保存failed/exhausted、必填原因、空result与unverified。
- [x] 所有LIVE工具调用前必须有显式绑定/清理协议；缺协议或绑定失败时工具发送0；每client短锁保护active身份及open/closing/closed，借入只按身份解绑且可顺序复用，自有close先标closing再锁外关闭；重复清理物理close最多一次，关闭失败也不允许重新绑定。
- [x] 默认factory显式拥有独立client，内部fake显式逐HTTP准入；测试并发bind至多一赢、失败绑定清理不改变原run、借入close次数0、自有close过程中新bind失败，不靠GIL或真实sleep建立竞争顺序。
- [x] 真实AmapAdapter与MockTransport经API集成覆盖正常/额度耗尽/同键重放；重放同run且新增factory/HTTP/完成事件为0，正常与耗尽已取得自有资源均关闭尝试一次，数据库重读可核对证据和实际计数；保留同键改载荷409与默认缺Key503。
- [x] 同票说明默认40、HTTP尝试非计费、绑定协议变更、独立脚本不自动拥有run预算以及真实供应商未验；给出隔离库复现前后观察，不提前宣称deadline/取消已交付。
- [x] [Review Focus] 第二个adapter绑定同一active client失败后，其cleanup不得解绑或关闭第一个run的client；原run仍能执行且预算独立。

### Task 2: 单调deadline、可达的API取消与原子终态

**Blocked-by:** 1
**R-ID:** LRC-02, LRC-03, LRC-04, LRC-05, LRC-06, LRC-09

从创建前到最终保存建立运行级时间/取消边界；原创建与修订POST仍等待终态，但同进程可并发重放取标识并取消。取消确认和最终快照分别短事务一致归一，不引入worker、提前202平台或SQL列迁移。对应原任务2.1–2.5。

- [x] 幂等命中不建立runtime；新run在factory前取单调开始时间；发送前后、阶段间、评估前后、终态接受和收尾检查；假clock验证0/90边界、UTC跳变、剩余1秒及更短0.25秒配置，四操作timeout不大于配置与剩余时间较小值，不用真实sleep等90秒。
- [x] 响应、评估或收尾迟到且无更早主失败时保存deadline耗尽与实际elapsed，不接受completed/needs_input/verified晚结果；普通操作timeout但总deadline未到仍保持原工具分类；已有主失败不被后续清理或时间检查覆盖。
- [x] 取消/缺失/读取异常探针不得放行新发送，短探针不包HTTP；创建与LIVE修订的同步核心在线程执行，同一应用同一事件循环在等待期间可并发API同键重放拿到run_id，再调用原cancel入口，原等待请求最终返回已提交取消态。
- [x] API并发集成覆盖创建和修订、原键/原载荷、重放factory/HTTP增量0及下一handler不命中；LIVE取消响应/事件标正确mode与尽力停止提示，不含replay或无远端调用声明，承认in-flight检查后竞争。
- [x] 取消确认与最终保存各自一次短事务重新判定并归一status=cancelled、budget.status=cancelled、quality_status=unverified、result=null、删除耗尽原因；保存实际次数/elapsed/证据与原诊断。barrier竞争中的GET/重放不可看到混合终态，不先提交后修补；已提交主失败先于取消则terminal拒绝。
- [x] 时间/取消说明与JSON示例随票更新，明确默认90/操作5、单调elapsed、新耗尽必填原因/历史可缺、不能强制90秒返回、清理可超时；新增诊断只含固定类别/安全类型，不拷原始异常字符串。
- [x] [Review Focus] 最后一次check之后、最终保存之前取消提交胜出；竞争中的独立连接GET与同键重放须始终读到归一快照，不能只检查最终一次GET。

### Task 3: 异常收尾、脱敏与真实loopback验收

**Blocked-by:** 1,2
**R-ID:** LRC-01, LRC-02, LRC-03, LRC-04, LRC-05, LRC-06, LRC-07, LRC-08, LRC-09

补齐已取得资源的异常出口，确保主结果与安全诊断可读，并通过独立进程的真实本地HTTP组合验证前两票。对应原任务3.1/3.2/3.4/3.5；原3.3完整聚合回归由唯一票4承担，不能把本票自身失败覆盖推迟到票4。

- [x] 自有资源成功/provider_error/call_limit/deadline/cancel/constructor_failure各有一次清理尝试；factory返回前未交资源由factory负责，借用关闭0且解绑后顺序复用；构造校验失败与close幂等有可观察断言。
- [x] 解绑失败仍独立尝试其余清理/物理close；cleanup_failure保存原主类别/准确预算/证据及固定RESOURCE_CLEANUP_FAILED警告，不因finally跳过保存，不宣称释放成功；无更早主失败时清理后仍不能接受过期结果。
- [x] 普通HTTPError、provider文本、顶层执行错误、取消探针与cleanup错误注入合成Key/query/私人标记；API、持久state和事件不含标记/带query URL/raw str(exc)，仅固定类别/安全异常类型或验证后的数字供应商码；原错误状态分类保持正确。
- [x] [e2e] 独立隔离应用进程注入真实适配器与MockTransport合成供应商，经真实loopback HTTP对创建和LIVE修订并发POST/同键重放/cancel/GET；不能旁路写DB代替取消，核对运行/计数/清理动作/事件与SQLite一致；无论环境是否有Key都不得访问真实供应商，结束只停止自己启动的服务并保留可复现命令/退出码。
- [x] LIVE文档、API约定和验收记录最终互链，逐条列9条需求的证据/未满足项，明确分支不等于main、未独立代码审不标T11完成，不更新私人讲义的main现状数字；记录实际命令/计数而非预写原88+新增总数。
- [x] [Review Focus] close异常包含敏感文本且总deadline在清理期间到达：保留更早主失败、仅安全警告、持久化仍尝试，不把close一次尝试写成资源已释放。

### Task 4: 实现验证（聚合收尾）

**Blocked-by:** 1,2,3
**R-ID:** all

按聚合套件发现契约运行本change命中域的全部层。此票唯一且不计入三张功能切片预算；承担原任务3.3，不增加产品范围。

- [x] 起手运行权威suite-scope并将base/head/domains_configured/hit_domains/layers/skipped_layers/mapping的JSON管道直贴报告头，不手工转录、不解析构建文件猜套件。
- [x] 命中域各层证据齐全并通过，或按契约记录未覆盖/不在命中域；记录真实命令、退出码与实际用例数，零用例不算通过，不用票内局部测试代替全部聚合层。
- [x] 完整pytest覆盖既有replay、Amap离线与LIVE场景及新增运行边界；真实loopback聚合流程有可复现证据；未运行/失败/真实供应商与生产未验范围明确保留，不以全绿推出硬中断、灾备或供应商效果。
