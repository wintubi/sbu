# Task 3 共享上下文

Global Constraints/代码清单与 task1-shared-context.md 同源（逐字取自批准设计）；票3原文在 impl-reports/task3-brief.md。

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

## Code review checklists

# 通用代码审查规则集（base）

> **定位**：项目无关、语言无关的代码实现审查维度，`sdflow-code-review`（及 `sdflow-implement` Standards 轴必填槽）阶段每次必过；
> 再按命中 TG 叠加 `domains/` 领域 delta。架构见 [README.md](./README.md)。

---

| ID | 规则 | 检查点 |
|----|------|--------|
| CR-01 | **错误处理正确性** | 所有错误返回值被检查（禁忽略，除非注释说明为何安全）；错误带上下文包装、保留调用链；`err != nil` 分支后不得继续使用可能为零值的返回；哨兵错误用「是否同类」判断而非 `==` 直接比 |
| CR-02 | **错误路径完整性（四路径）** | 每个新数据流覆盖：happy path / nil 输入 / 空·零长度输入 / 上游 API 失败；上游失败时传播错误而非继续用无效数据 |
| CR-03 | **nil / null 安全** | 解引用前查 nil；接口/类型断言用安全形式（双值 `v, ok`）；map 读用双值形式；容器（slice/map）作参数时按需查 nil |
| CR-04 | **资源清理** | 打开的资源（文件/连接/游标/锁）都成对释放；early-return 与错误路径都释放；循环内延迟释放陷阱（积累不释放）；锁的释放紧跟获取 |
| CR-05 | **并发与互斥** | 共享状态用锁/原子保护；多锁固定获取顺序防死锁；持锁期间禁阻塞操作（IO/等待）；锁粒度合理（不把整段业务放一个大锁）；所有加锁路径都有解锁（含 early-return/错误） |
| CR-06 | **整数 / 类型转换安全** | 窄化强转考虑溢出（+注释说明有意为之）；有/无符号比较显式转换；隐式整型提升已知晓；位移操作数无符号且移位量不超类型宽度 |
| CR-07 | **日志与可观测** | 日志含上下文字段（request_id/trace_id 等）；敏感信息（密码/token）不入日志；高频路径 debug 日志生产环境关闭；异常/panic 日志含 stack；错误路径也正确计 metrics；格式符与变量类型严格匹配 |
| CR-08 | **常量与魔法数字** | 时间/阈值/协议 magic number 用命名常量，非字面量；数组大小用 `sizeof`/编译期常量，非硬编码 |
| CR-09 | **测试质量（PR 新增测试）** | 新测试覆盖错误路径（非只 happy）；用例有清晰命名/场景；mock 仅隔离真正需要的依赖（过度 mock 掩盖集成问题）；测试确定性（不依赖当前时间/随机/未 mock 外部调用）；并发测试无未同步的共享状态 |
| CR-10 | **命令 / 代码注入** | 外部输入拼进可执行命令或代码前先隔离：拼 shell 命令用参数数组而非字符串插值（禁 `subprocess(..., shell=True)` / `os.system()` / 反引号拼接 直接插值外部输入）；`eval`/`exec` 类动态求值（`eval()` / `exec()` / `new Function()` / `os/exec.Command("sh","-c",...)`）执行的内容若来自模型输出或外部输入，须走沙箱或白名单，不得未经校验直接执行 |
| CR-11 | **枚举 / 取值完备性** | 新增枚举值 / 状态串 / 类型常量后，逐个消费点 trace 是否已处理该新值（**必须读 diff 外代码**——grep 该枚举的兄弟取值找出全部消费点，逐个确认新值有无被同等处理，不能只看本次 diff 改了哪些行）；allowlist / 过滤数组需同步核对新增值是否已收录；`switch`/`case`/`if-else` 链的默认分支不得静默 fall-through 到错误行为（未识别的取值须显式报错或拒绝，而非被当作某个已知分支处理） |
| CR-12 | **测试被削弱（为绿而绿）** | diff 中凡出现以下任一形状，**一律按「高」上报**，finding 须写明被削弱的断言原本守的是什么行为：断言被删除或放宽（精确值改为宽松比较、期望值改成迁就当前输出）；新增 `skip` / `xfail` / 条件跳过；超时或重试次数放大到足以掩盖失败；整个测试被删除。裁为不成立须有依据：需求确实变了（指出对应的 spec / 四件套改动），或是因环境前提缺失而加的条件跳过且带修复提示（如发布快照不含开发仓独有文件、可选依赖未安装）；必需依赖缺失 MUST 报红而非跳过 |

# 代码审查领域：后端服务（通用）

> `extends: base` —— 后端代码审查特有维度（DB / HTTP），语言无关；
> Go 语言习惯见 `backend-go.md`，通用维度见 [`../code-review-base.md`](../code-review-base.md)。

---

| ID | 规则 | 触发条件 | 检查点 |
|----|------|---------|--------|
| CR-BE-01 | **数据库操作安全** | 含 DB 读写 | 参数化查询防注入（禁字符串拼接 SQL）；事务用 defer rollback 保证 panic/early-return 自动回滚；游标/结果集 defer close 防连接泄漏；迭代后检查 rows 错误；无 N+1（循环单查 → 批量 IN）；大结果集流式处理而非全量入内存 |
| CR-BE-02 | **HTTP Handler 安全** | 新增/改 endpoint | 请求体大小限制（防超大 payload 打爆内存）；输入校验在 handler 最前（必填/格式/长度）；响应设正确 Content-Type；不重复写响应头；redirect 目标校验防 open redirect；CORS 收紧（Origin/Method/Header 最小化）；用户可控数据进不安全 HTML 渲染前防 XSS——**仅服务端模板渲染场景**（如 Jinja2 `\|safe` / Django `mark_safe` / Rails `html_safe` / Go `template.HTML`）；客户端框架渲染 XSS 见 `domains/frontend.md` CR-FE-01（本条聚焦服务端模板渲染） |
| CR-BE-03 | **DB 层竞态** | 含并发写路径的 DB 操作 | find-or-create 类操作无唯一索引兜底会在并发下重复插入（先查后插不是原子操作）；check-then-set（先读状态再据其更新）须用带旧值条件的原子 `UPDATE ... WHERE 状态=旧值`，而非读出来判断后再单独写；状态迁移的多步更新非原子会导致中间态可见或非法跳变（双跳）；绕过 ORM/模型层校验直接写 DB（原生 SQL/批量脚本）会漏掉模型内建的约束检查 |

*规则集 v1 · extends base · 项目无关*

领域清单未覆盖：当前code-checklists/domains无devex或Python专属delta；实际采用通用base与backend。不得声称未运行的领域清单已审。
