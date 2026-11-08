## Purpose

为年画候选提供可追溯的人工裁决与本地知识发布能力：用预期版本、幂等请求和不可变历史保护审核结果，严格区分结构有效、来源支持和人工批准，只向当前知识视图提供合格的当前版本，并保留可回查的历史快照。

## ADDED Requirements

### Requirement: RP-01 Explicit review decisions
系统 SHALL 要求审核者标签、非空理由和预期版本，并支持approve/reject/revise；approve只能裁决已有内容，不能同时修改断言。审核者标签是本地自述信息，不构成认证。

#### Scenario: Approve supported valid claim
- **WHEN** 审核请求明确supported，断言结构有效、值和证据非空
- **THEN** 新版本中该断言变为approved，保存审核者、时间、理由和前后值

#### Scenario: Reject or revise a claim
- **WHEN** 人工驳回断言或修改谓词、值、证据
- **THEN** 驳回保留原内容并标rejected；修改重校验并回到unreviewed，初始候选和旧审核不被覆盖

#### Scenario: Reject invalid approval or mixed edit
- **WHEN** 尝试批准invalid/空值/空证据断言，或approve动作同时改内容
- **THEN** 返回422，整个审核不新增事件或版本

### Requirement: RP-02 Optimistic concurrency with atomic audit
系统 SHALL 在同一提交边界内校验预期版本并创建审核事件、新版本和当前版本；版本过期不得覆盖新结果。

#### Scenario: Two reviewers use the same version
- **WHEN** 两个独立请求用同一个预期版本提交不同审核
- **THEN** 最多一个请求成功，另一个返回409 VERSION_CONFLICT；只有一次版本推进且所有旧版本可读

#### Scenario: Failure during audit persistence
- **WHEN** 创建事件或保存新版本过程中发生存储错误
- **THEN** 整个审核回滚，当前版本和事件数量保持原样，不留下半次修改

### Requirement: RP-03 Idempotent imports reviews and publications
候选导入、审核和发布 SHALL 要求非空Idempotency-Key，按操作/资源作用域保存规范请求哈希及原响应；重放校验先于旧版本检查。

#### Scenario: Retry an already successful review
- **WHEN** 同键同载荷重试已成功请求，即使当前作品已进一步更新
- **THEN** 返回原操作结果，不新增事件、版本或快照，不误报旧版本冲突

#### Scenario: Reuse key with different payload
- **WHEN** 同作用域同幂等键配不同载荷
- **THEN** 返回409 IDEMPOTENCY_CONFLICT且不改状态

#### Scenario: Missing key
- **WHEN** 导入、审核或发布缺少有效幂等键
- **THEN** 返回422并指出字段，不接受无法区分的重复写入

### Requirement: RP-04 Publication eligibility
系统 SHALL 只发布当前版本中approved+supported+valid且值和证据非空的断言；发布前所有断言已裁决，所有仍阻断的问题已解决，并至少有一条合格断言。系统 SHALL 拒绝 access_policy 不属于 `synthetic-only`/`cleared-for-publication` 的来源发布，即使其断言已全部批准。

#### Scenario: Candidate is not ready
- **WHEN** 仍有unreviewed断言、阻断未决项，或没有合格approved断言
- **THEN** 返回409 PUBLICATION_BLOCKED且不创建空快照，不把completed处理状态当作事实已确认

#### Scenario: Rejected invalid claim remains visible but excluded
- **WHEN** 一个缺证据断言已被明确reject，另一个合格断言已approved且无其他阻断
- **THEN** 被驳回项及其未修复问题仍可回查，但该断言的结构问题不再阻断发布，快照只含合格断言

#### Scenario: Structural issue cannot be manually dismissed for approval
- **WHEN** 审核者只提交“已解决”理由而未修复准备批准断言的失效引用
- **THEN** 该断言仍为invalid并阻断批准/发布，不能用理由替代结构校验

#### Scenario: Restricted source policy blocks publication
- **WHEN** 断言已全部批准且无未决阻断问题，但来源 access_policy 为 `local-unverified-no-publication`
- **THEN** 返回409 PUBLICATION_POLICY_BLOCKED，列出受限来源，不创建快照

### Requirement: RP-05 Current and historical publication separation
系统 SHALL 保存按作品/版本唯一的不可变本地快照；当前知识查询仅展示发布版本等于作品当前版本的快照，历史快照明确标记。

#### Scenario: Repeat publication of current reviewed version
- **WHEN** 合格的同一当前版本以新幂等键再次发布
- **THEN** 返回原快照ID，快照数量不增加

#### Scenario: Review advances after publication
- **WHEN** 发布后审核推进到新版本但尚未重发
- **THEN** 当前知识视图不展示旧版本，历史快照仍可按ID读取且标historical

#### Scenario: Stale publication request
- **WHEN** 一个非幂等重放的新发布请求指定旧expected_version
- **THEN** 返回409 VERSION_CONFLICT，不将旧快照冒充当前版本

### Requirement: RP-06 Review and publication user flow
系统 SHALL 提供来源/候选查看、修改、裁决、问题处置、版本冲突提示、发布和历史查看的本地操作入口，保留条件不满足的具体原因。

#### Scenario: Complete synthetic demonstration
- **WHEN** 用户登记合成来源、导入候选、核对证据后批准并发布
- **THEN** 页面可观察版本推进、审核理由和本地发布结果，并能回到初始候选与原件；演示明确合成、无实时模型/Neo4j

#### Scenario: Handle stale review in the page
- **WHEN** 页面提交的版本已过期
- **THEN** 显示冲突与重新载入当前版本的入口，不静默覆盖或假装审核成功

#### Scenario: Replay result does not overwrite current UI state
- **WHEN** 重试返回先前写入的原响应，而作品已推进到更新版本
- **THEN** [spec-review-amendment F03] 页面重新读取当前记录和知识，不将重放的旧响应标为当前状态，也不覆盖当前较新内容

### Requirement: RP-07 Durable local state and truthful readiness
系统 SHALL 在重启后保留已提交原件、版本、事件、幂等结果与快照；存活和就绪检查分开，报告实际能力与错误，不执行收费请求。

#### Scenario: Restart after committed review
- **WHEN** 服务在审核成功后重启
- **THEN** 原来源/审核版本/历史和幂等结果仍可读取，不要求重新抽取

#### Scenario: Storage unavailable
- **WHEN** 数据库不可用或锁等待预算耗尽
- **THEN** 就绪报告degraded，业务给可定位的500或503及retryable说明，不伪报成功、不无限重试

### Requirement: RP-08 Local trust boundary and evidence reporting
系统 SHALL 只作为可信本地审核演示运行，对跨源写入与不允许的Host拒绝处理；软件、浏览器、真实服务和领域效果的证据分开记录。

#### Scenario: Foreign web origin writes
- **WHEN** 写请求携带非允许本地同源Origin
- **THEN** 请求被拒绝，不产生审核/发布事件，不提供宽泛CORS放行

#### Scenario: Unexecuted browser or supplier validation
- **WHEN** 浏览器启动受阻或没有真实OCR/VLM/图谱调用证据
- **THEN** 报告将对应验证标为未运行，API或模拟DOM测试通过不替代这些结论
