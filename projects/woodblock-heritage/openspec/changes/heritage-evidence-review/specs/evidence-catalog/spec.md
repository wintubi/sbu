## Purpose

为年画编目审核提供可靠的页面来源与候选知识登记能力：分开原件、页码、区域、原文和断言，保留来源与结构问题，使后续人工裁决能回查依据，并避免把机器或用户提交的候选直接认定为已审核事实。

## ADDED Requirements

### Requirement: EC-01 Verified source registration
系统 SHALL 从上传字节验证PNG/JPEG并读取实际尺寸，生成内容标识和来源ID；来源元数据、物理页序与印刷页码分开保存。默认解码文件上限8MiB、请求上限12MiB、像素上限20M，可配置且必须对外报告超限。

#### Scenario: Register valid source
- **WHEN** 提交有效图像和来源说明，物理页序未知、印刷页码为040
- **THEN** 返回201、来源ID、内容哈希和实际尺寸，物理页序保持null，印刷页码保持040

#### Scenario: Reject invalid or oversized source
- **WHEN** 文件格式不支持、文件截断/解码失败或超过字节/像素限制
- **THEN** 返回415或422，超限返回413，不创建来源或候选，不执行外部查询

### Requirement: EC-02 Content deduplication without metadata overwrite
系统 SHALL 按图像内容哈希识别重复来源，重复内容不得自动创建作品或覆盖原元数据。

#### Scenario: Same content and metadata
- **WHEN** 再次提交同一原件字节与相同规范来源元数据
- **THEN** 返回200和原来源ID，来源数量不变

#### Scenario: Same content with conflicting provenance
- **WHEN** 同一原件字节携带不同来源说明、文件名或页序信息
- **THEN** 返回409 SOURCE_METADATA_CONFLICT，原元数据不变且不静默合并归属

### Requirement: EC-03 Region coordinate integrity
系统 SHALL 显式接收像素或归一化坐标，以实际来源尺寸转换并保存输入坐标与转换依据。[spec-review-amendment F01] 区域ID和断言ID分别在作品内唯一，空或重复ID返回422，Region必须引用该作品声明的已登记来源。

#### Scenario: Normalize pixel coordinates
- **WHEN** 来源尺寸为100×200，区域像素框为[10,20,50,100]
- **THEN** 存储归一化框[0.1,0.1,0.5,0.5]且保留原坐标系与输入框

#### Scenario: Invalid or ambiguous region
- **WHEN** 存在越界、非有限数、零面积、不支持坐标系、重复区域ID或未声明的来源引用
- **THEN** 返回422且不创建作品，不能截断坐标或猜测来源

### Requirement: EC-04 Untrusted candidate import and frozen schema
系统 SHALL 接受heritage-review-v1的字面量候选，创建不可变初始版本；客户端不能通过导入设置已支持或已批准状态。未知值保持null，不根据题名或通识补人物身份、作者或年代。

#### Scenario: Import client-asserted approval
- **WHEN** 合法候选提交时包含客户端声称的supported/approved或valid状态
- **THEN** 服务重新设置为insufficient/unreviewed并重算结构状态，初始版本不出现在已发布知识中

#### Scenario: Unsupported entity or schema
- **WHEN** 请求使用未知schema_version或本切片不支持的实体对象
- **THEN** 返回422并明确不支持，不将实体关系强转成任意字符串

#### Scenario: Preserve source title scope
- **WHEN** 原文题名包含两个人名而图像只有一个待识别人物
- **THEN** 可以记录source_title与配对疑问，但系统不自动新增人物身份断言

#### Scenario: Import cannot resolve its own issues
- **WHEN** 候选包含客户端自称resolved/non-blocking的人工疑问
- **THEN** [spec-review-amendment F05] 服务将问题设为open且blocking，原始输入保留在不可变导入快照，只有后续带理由的审核事件可以处置

### Requirement: EC-05 Structural issues are distinct from factual support
系统 SHALL 验证谓词、证据引用与非空值，保存原候选和可定位校验问题；引用存在仅证明结构可解析，不能自动判为内容支持或人工批准。

#### Scenario: Missing reference or unknown predicate
- **WHEN** 候选具有合法外层结构，但断言引用不存在的区域或使用未知谓词
- **THEN** 候选被保存为validation_status=invalid并附断言级问题，不能批准或作为正式知识发布

#### Scenario: Existing evidence does not imply support
- **WHEN** 区域存在但其原文不足以支持断言
- **THEN** 结构状态可为valid，support仍为insufficient或disputed，人工批准前不发布

#### Scenario: Summary is not an exact quotation
- **WHEN** 导入的是说明摘要而非逐字原文
- **THEN** [spec-review-amendment F06] text_kind保持summary并在审核展示中区分，未声明text_kind也不能默认变成exact引文

### Requirement: EC-06 Safe evidence access and candidate display
系统 SHALL 提供来源与候选查看入口，显示原件、区域、原文、三类状态、校验问题和版本；来源只按服务生成的ID获取，原文件名与候选文本均不能成为路径、可执行HTML或工具指令。

#### Scenario: View evidence and unresolved pairing
- **WHEN** 打开含图文配对疑问的候选
- **THEN** 页面可查看原件/区域/原文及未决问题，候选与已发布知识明显区分

#### Scenario: Treat hostile input as data
- **WHEN** 原名含路径字符、候选文字包含脚本或要求绕过审核的指令
- **THEN** 不访问该路径、不执行文本，页面安全显示或拒绝非法字段，审核与发布门禁不改变
