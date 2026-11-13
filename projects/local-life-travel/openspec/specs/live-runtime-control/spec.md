# live-runtime-control Specification

## Purpose

为单次真实渠道行程运行提供可核对的请求成本、处理时间和资源生命周期边界，让调用者区分已获准的HTTP尝试、预算或deadline耗尽、取消和普通工具失败。此能力用于客户端软件契约验证，不把离线成功包装成供应商成功、计费证明、严格墙钟中断或生产灾备。

## Requirements

### Requirement: LRC-01 每次HTTP尝试在发送前受预算准入

系统 SHALL 对单次LIVE运行的每次HTTP发送尝试预先检查并预占一次预算，默认上限40；工具内部批次同样受限。被拒绝的尝试 MUST NOT 到达发送层。无HTTP的工具不得虚增计数，已准入后失败的尝试不得退还；该计数不是供应商收费凭证。

#### Scenario: 第N加一次被拒绝
- **WHEN** 正常请求已获准N次且上限为N，随后请求下一次发送
- **THEN** 第N+1次不进入传输处理，运行标记预算耗尽，保存尝试数N

#### Scenario: 批次中途耗尽
- **WHEN** 营业详情、天气多步查询或路线批次所需请求数大于剩余次数
- **THEN** 每个内部请求独立准入，恰好用完后停止批次，不先超发再报错

#### Scenario: 失败尝试与无HTTP工具
- **WHEN** 获准请求发生连接/超时/供应商/格式错误，另一个工具完全使用本地数据
- **THEN** 获准尝试计一次，本地工具计零，不用工具方法次数替代HTTP数

#### Scenario: 零额度和恰好用完
- **WHEN** 上限为0且需要HTTP，或上限为40且正好完成40次后无需新HTTP
- **THEN** 前者发送次数0并耗尽；后者允许在时间和业务规则满足时完成，不因恰好等于上限拒绝已获得的正常结果

### Requirement: LRC-02 用运行deadline控制准入与结果接受

系统 SHALL 从新run开始执行、创建适配器之前建立默认90秒的单调时间预算，并在发送、工具返回、阶段切换、终态接受和收尾检查取消/时间。达到或超过deadline MUST NOT 开始新HTTP或接受晚结果为正常完成。操作级超时不得超过配置值与剩余时间较小者；此契约不保证强制中断同步调用或90秒内返回。

#### Scenario: 开始前和批内达到deadline
- **WHEN** 执行前时间预算已为0，或批内下一次准入时已到deadline
- **THEN** 不开始相应factory/下一次发送；已分配的资源仍进入清理，保存deadline耗尽

#### Scenario: 响应或评估迟到
- **WHEN** 已准入的响应、后续评估或收尾返回时已达到总deadline且没有更早主失败
- **THEN** 不接受completed/needs_input或verified结果，保存deadline耗尽与实际耗时，无后续HTTP

#### Scenario: 剩余时间与短配置
- **WHEN** 单操作配置为5秒而剩余1秒，或配置0.25秒而剩余1秒
- **THEN** 四类网络操作timeout分别不超过1秒或0.25秒，不放大较短配置，不关闭超时

#### Scenario: 普通工具timeout和系统时钟跳变
- **WHEN** 网络单操作超时但仍在总deadline内，或系统UTC发生跳变
- **THEN** 前者仍按普通工具timeout规则处理并计尝试；后者不改变单调时间计算，不伪造增加或减少运行预算

### Requirement: LRC-03 观察取消并返回持久状态

系统 SHALL 在LIVE工作边界和每次HTTP发送前观察持久取消状态；一旦观察到取消，不再启动新工作，保存cancelled并清理资源。取消确认和最终提交 SHALL 各自在一个短事务中一致归一status、budget.status=cancelled、quality_status=unverified与result=null，删除耗尽分类键并保留原诊断；返回/GET/重放不可暴露混合终态。推荐候选要求同进程API可接收控制请求，通过同键重放取得运行中run_id，不要求原POST提前返回。检查后已提交的在途请求可能仍返回，系统不承诺撤销或严格线性化取消与发送。

#### Scenario: 两次发送之间被取消
- **WHEN** 第一HTTP返回后另一连接把运行取消，下一次发送前观察到取消
- **THEN** 不进入下一次传输，状态cancelled，未完成结果不作为verified，已有尝试数保留

#### Scenario: 保存竞争中取消被保护
- **WHEN** 取消在最后边界检查后、结果保存前成功提交
- **THEN** 单次事务提交cancelled/cancelled/unverified/null一致快照，取消后和最终提交后GET/同键重放均无verified/ok混合态；不先提交再修补

#### Scenario: 取消探针读取失败
- **WHEN** 发送前无法读取受控运行状态或运行已不存在
- **THEN** 运行以执行错误停止，不因读取失败绕过准入继续外呼；持久化失败必须如实暴露

#### Scenario: 运行中从实际API取得标识并取消
- **WHEN** 带幂等键的LIVE创建或修订仍在执行，调用者向同一单进程API并发提交相同键/载荷的重放请求
- **THEN** 重放返回同run_id且不再调用factory/供应商；取消入口可被接收，响应与事件正确标示LIVE，不含回放/无远端声明，也不声称撤回在途请求；下一可观察边界停止新发送，原等待请求最终返回已提交取消态

### Requirement: LRC-04 保存预算耗尽的可解释结果

系统 SHALL 在正常可写数据库中保存该run获准的HTTP尝试数与单调实际耗时。次数或总deadline耗尽时，运行为failed、budget.status为exhausted，附BUDGET_EXHAUSTED及新耗尽run必填exhaustion_reason=call_limit或deadline（历史记录可缺失）；未完成结果为空且质量unverified，已有工具证据保留。此保证不扩展为进程崩溃后逐HTTP精确账本。

#### Scenario: 耗尽前已有有效证据
- **WHEN** 部分工具成功后次数或deadline耗尽
- **THEN** 保存已有ToolResult/证据和全部已准入尝试，result为空，不伪造可行结论；读取可区分两种耗尽原因

#### Scenario: 无HTTP及历史run
- **WHEN** 一个新run全部使用本地缓存且时间仍足够，或查询旧预算JSON
- **THEN** 新run可为零HTTP而正常完成；旧run按原记录返回，不补造新消耗或历史耗尽原因

#### Scenario: 批内成功子证据不随中断丢失
- **WHEN** 首条路线或首个营业详情在deadline前成功规范化，下一次内部请求因额度/deadline/取消中断
- **THEN** 重读可定位已成功子证据的来源/时间/payload，准确计数；部分批次不当完整成功，result为空且质量unverified，迟到子结果不被采为有效事实

### Requirement: LRC-05 幂等重放不重执行

系统 SHALL 保留LIVE创建和修订的幂等语义：同键同请求直接返回已保存run，不重新建立执行资源、绑定预算或发送HTTP；同键不同请求返回冲突。新运行的尝试数不能混入另一个run；缺Key的默认LIVE入口仍明确拒绝配置缺失。

#### Scenario: 已成功或耗尽run的同键重放
- **WHEN** 调用者重发一个已有成功或耗尽run的相同请求和键
- **THEN** 返回同run_id/原结果，新增factory、HTTP和业务完成事件均为0，不重算elapsed

#### Scenario: 改请求和缺Key
- **WHEN** 同键载荷改变，或默认渠道未配置可用Key
- **THEN** 分别保留409冲突、503未配置语义，不进行伪成功外呼

### Requirement: LRC-06 LIVE适配器显式受运行控制

系统 SHALL 在任何LIVE工具调用前要求注入适配器显式接受运行控制与清理协议，缺少或绑定失败则停止，不能以事后计数降级。每个active run有独立预算；同client同时绑定第二个active run MUST 被拒绝而不覆盖前者。独立非LIVE调用者不得被误称拥有此运行保证。

#### Scenario: 缺少协议
- **WHEN** 注入对象没有运行绑定或清理能力
- **THEN** 工具调用和HTTP发送均为0，记录执行错误并清理已取得且可清理的资源

#### Scenario: 重叠绑定及顺序借用
- **WHEN** 同client仍绑定active run时请求另一绑定，或先前run已解绑后顺序借用
- **THEN** 前者拒绝且不改变原run控制，后者建立独立计数，不串用前次消耗

#### Scenario: 自有client关闭与新绑定竞争
- **WHEN** 旧run已进入自有资源清理但物理关闭尚未完成，另一run请求绑定同client
- **THEN** 因closing/closed拒绝新绑定且工具调用0；关闭失败也不得恢复可借用状态，借用client单纯解绑仍可顺序复用

### Requirement: LRC-07 资源拥有权覆盖所有执行出口

系统 SHALL 区分自有与借入client。拥有权转移后，成功、供应商失败、次数耗尽、deadline、取消及构造失败均须有关闭尝试；重复清理不重复关闭。借用client必须解绑控制而不擅自关闭。factory在返回对象前失败时，factory负责其未交出资源，不虚称顶层可以关闭未知对象。

#### Scenario: 已取得自有资源后的多种终态
- **WHEN** 自有资源路径成功、供应商失败、额度耗尽、deadline或取消
- **THEN** 都调用一次关闭并尝试解绑，重复调用不增加关闭次数

#### Scenario: 构造失败和借入资源
- **WHEN** 拥有权已转移后构造验证失败，或完整运行使用借入client
- **THEN** 前者创建方清理一次；后者只解绑，借入client关闭次数0且仍可由原拥有者决定使用

### Requirement: LRC-08 清理失败不能掩盖主结果

系统 SHALL 在解绑/关闭抛错后继续其余可执行清理，并在数据库正常时保存主结果及脱敏RESOURCE_CLEANUP_FAILED警告。清理失败不能覆盖较早业务失败；关闭尝试不得被描述为释放成功。若没有更早主失败，清理后仍需拒绝过期终态。诊断不得暴露真实凭据、供应商带query的URL或私人请求。

#### Scenario: 原失败与关闭失败同时出现
- **WHEN** 运行已因额度、deadline或供应商失败，随后关闭抛错
- **THEN** 读取仍能看到原失败类别/准确消耗及清理警告，不因finally异常跳过保存；警告仅固定分类/异常类型

#### Scenario: 解绑失败不跳过自有client关闭
- **WHEN** 解绑步骤抛错但自有client仍可尝试关闭
- **THEN** 继续尝试关闭，记录清理不确定性，不吞掉主结果或声称已完全释放

#### Scenario: 普通网络及执行异常中的敏感文本
- **WHEN** deadline内普通HTTPError或顶层执行异常含合成Key、query URL或私人标记
- **THEN** 状态分类保持可识别，API结果/持久state/事件仅固定分类和安全异常类型或校验后的供应商数字码，不含这些敏感文本；并覆盖cleanup异常同一规则

### Requirement: LRC-09 验证和对外说明保持真实范围

系统交付材料 SHALL 清楚区分HTTP尝试与收费、运行deadline与强制墙钟中断、离线契约与真实渠道效果。默认40/90/5来源、内部注入协议变化和新耗尽必填/历史可缺失的原因字段须可查。软件验收必须观察发送点、最终持久状态和资源动作，不能只检查status或提前记录未运行测试为通过。

#### Scenario: 开发者验收材料
- **WHEN** 开发者阅读LIVE文档及本次测试记录
- **THEN** 能找到默认值/计数边界/取消竞争/资源拥有权与局限；MockTransport和假时钟结果标离线，不声称真实高德、费用、硬中断、断电恢复或已合并main
