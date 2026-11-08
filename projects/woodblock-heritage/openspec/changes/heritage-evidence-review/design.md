# Design

## Context

动机和范围见[提案](proposal.md)。本变更的合成切片已实现于 `app/`、`web/`、`tests/`；以下 API、表和模块为已实现/已校验的契约，真实抽取与 Neo4j 仍不在公开子集内。

[spec-review-amendment H0] 历史工程在私有工作区已有本体、词表、抽取、自动校验和 Neo4j 写入代码；本变更不重写这些能力，而是在其产物之上补人工审核、版本与本地发布。公开子集不包含历史原始数据或本机路径。论文写 23 类实体/19 关系、当前代码 27/31、远端固定提交 15/19，三者为不同版本，不能混用。真实原件许可未核，公开演示只使用合成页。Python/FastAPI/Pydantic/SQLite 延续已验证环境。

## Goals / Non-Goals

目标：来源→候选→结构校验→人工裁决→本地快照的可操作、可恢复闭环。原输入不可变；修改生成新版本，不能覆盖历史。限制和重新进入条件见[提案](proposal.md)的Non-Goals；本设计不把本地快照称为Neo4j或在线知识服务。

## Decisions

决策、被否候选和证据全文见[决策纪要](decision-memo.md)。

### 切片建议

A：来源登记/候选/页面证据预览；B：版本审核、并发与审计，依赖A；C：发布/当前查询/历史展示/完整演示，依赖B。每票同时包含接口、页面可观察结果和验证，不按前后端分票。

## Architecture and Data Flow

Context：可信本地编目者→本地审核应用；资料提供者只提供文件/候选。当前无外部模型/图谱调用。

Container/Component：

```text
[本地浏览器:来源/审核/发布页面]
                | 同源HTTP JSON/图片
[FastAPI:契约/大小限制/错误响应]
    |              |               |
[来源与候选] --> [审核事务服务] --> [发布与当前查询]
    \______________|_______________/
                   |
[SQLite:原件BLOB/不可变版本/事件/快照/幂等响应]
```

数据流：原件字节→格式/尺寸验证→内容哈希来源→像素/归一化Region→候选+校验问题→审核新版本→合格断言快照。候选说明文本只作为数据，不执行、不作为指令。

状态与决策：

```text
候选v1(unreviewed/insufficient; valid或invalid)
   --revise--> 新版本(unreviewed;重新校验)
   --approve(valid+supported+非空值)--> 新版本(approved)
   --reject--> 新版本(rejected)
   --版本过期/输入无效--> 409/422，无新事件或版本
当前版本全部已裁决 + 阻断问题resolved + 至少一条合格approved
   ? 是: 原子创建/复用本地快照
   : 否: 409 PUBLICATION_BLOCKED，无快照
后续审核推进版本: 旧快照保留，当前查询暂不展示旧版
```

审核/并发时序：

```text
浏览器A/B -> API -> 审核服务 -> SQLite BEGIN IMMEDIATE
A:查幂等键->核v=1->写事件+v2+当前v2+幂等响应->COMMIT->200
B:等A提交 ->查幂等键->核预期v1 !=当前v2 ->ROLLBACK->409
A重试同键同载荷:查到原响应->返回原v2，不创建v3
```

## Data Model and Lifecycle

来源只新增不覆盖；来源下的页面元数据不可静默修改。作品v1保存原候选，后续版本保存完整快照。所有管理ID由服务生成；导入Region/Claim局部ID仅在该作品内唯一。删除和来源元数据修订暂不提供：假设演示规模较小，若资料归属更正或保留策略成为需求，新增显式版本流程。

Region={id,source_id,kind:text|image,bbox:[x0,y0,x1,y1],coordinate_system:normalized|pixels,text?,text_kind:exact|summary?}。上传像素按实际来源width/height归一化；永久保存输入坐标和转换元数据，禁止零面积、NaN/Infinity、越界和不支持坐标系。

Claim={id,predicate,object:{kind:literal,value:string|null},evidence_refs[],support_status:supported|disputed|insufficient,validation_status:valid|invalid,review_status:unreviewed|approved|rejected}。导入时无论客户端声称什么，都由服务将support/review置insufficient/unreviewed，并重算validation。source_*表示原文记载，不推断图中人物身份或实物年代。

[spec-review-amendment F01/F05/F06] Region.id和Claim.id分别在作品内唯一；空/重复ID返回422，不生成作品。text存在但未给text_kind时标summary（未确认逐字原文），不能默认为exact。v1的payload.raw_import保存原始已解析请求作不可变导入快照，payload.import_version=1；后续版本只引用该初始快照，不能重用其中未受信任的管理状态作为当前事实。

冻结schema_version=heritage-review-v1，谓词为source_title/source_edition_note/source_category/source_technique_note/source_dimensions_note/source_collection_note/visual_description。未支持实体关系返回明确不支持，不强转字符串。未知谓词/不存在证据引用形成invalid问题，原候选保留；错误对象类型/超限/错误坐标为422且无作品。空值、空证据不能批准。

Issue={id,code,message,evidence_refs[],status:open|resolved,blocking:boolean,affected_claim_id?,reason?}。[spec-review-amendment F05] 导入的人工疑问由服务分配ID并重置open/blocking=true；客户端resolved/non-blocking或理由只保存在raw_import，不能替代审核事件。问题的证据引用如提供必须存在，不存在返回422。导入者可附配对/支持疑问，结构问题由服务产生；审核可带理由解决人工问题，结构问题只有重校验成功才resolved。若相关断言被reject，结构问题仍保留open但成为non-blocking，不要求为已明确排除的断言伪造证据；一旦重修订回unreviewed，问题重新阻断。工作级人工问题必须带理由处置。发布要求全部blocking问题resolved，未决不静默清空。

## Database v_old / v_new

v_old：新库，无业务表。v_new如下；除显式NULL项外全部NOT NULL；除声明DEFAULT外无默认。TEXT时间为带偏移RFC3339，JSON文本由应用Schema验证；不依赖SQLite JSON扩展。

| 表 | 完整列与约束 |
|---|---|
| sources | id TEXT PRIMARY KEY; content_hash TEXT UNIQUE; media_type TEXT; width INTEGER CHECK>0; height INTEGER CHECK>0; content BLOB; metadata_json TEXT; created_at TEXT |
| works | id TEXT PRIMARY KEY; current_version INTEGER DEFAULT 1 CHECK>0; created_at TEXT |
| work_versions | work_id TEXT REFERENCES works(id); version INTEGER CHECK>0; payload_json TEXT; created_at TEXT; PRIMARY KEY(work_id,version) |
| review_events | id TEXT PRIMARY KEY; work_id TEXT REFERENCES works(id); from_version INTEGER; to_version INTEGER; reviewer TEXT; reason TEXT; payload_json TEXT; created_at TEXT; UNIQUE(work_id,to_version) |
| publications | id TEXT PRIMARY KEY; work_id TEXT; version INTEGER; payload_json TEXT; created_at TEXT; UNIQUE(work_id,version); FOREIGN KEY(work_id,version) REFERENCES work_versions(work_id,version) |
| idempotency | scope TEXT; key TEXT; request_hash TEXT; response_json TEXT; PRIMARY KEY(scope,key) |

PRAGMA foreign_keys=ON，每连接单独事务。业务主写者为服务层，不允许页面直接写库。来源去重比较content_hash和规范元数据，metadata_json保存filename/source_note/access_policy/physical_index?/printed_label?，空值保持NULL语义而非伪造页序。相同内容但元数据不一致409，用户必须显式处理归属；不同来源的Work不自动合并。

## API Contract

全部拟新增；错误统一{code,message,retryable,field_errors?}。路径未知404，非法/缺失JSON及契约错误422，资源上限413，不支持图像415，幂等或版本冲突409，SQLite忙503。正常读取200，新建201，幂等重放200。写请求Origin存在时必须为当前允许的本地同源；无Origin允许本地脚本。无CORS放行。

| 路径 | 行为 |
|---|---|
| POST /api/v1/heritage/sources | JSON含filename/source_note/access_policy/physical_index?/printed_label?/image_base64；验证原件并创建201；同内容同元数据200，同内容冲突409 |
| GET /api/v1/heritage/sources/{id} | 返回来源元数据和哈希，不返回任意文件路径 |
| GET /api/v1/heritage/sources/{id}/image | 原字节+实际媒体类型+nosniff，不访问用户提供的路径或URL |
| POST /api/v1/heritage/works | Idempotency-Key必填；{schema_version,source_ids,regions,claims,issues}；新建候选v1与校验问题 |
| GET /api/v1/heritage/works | 列出本地候选/审核状态，不混称正式知识 |
| GET /api/v1/heritage/works/{id}?version=N | 当前或指定不可变版本，附校验问题、来源入口与审核事件 |
| POST /api/v1/heritage/works/{id}/reviews | Idempotency-Key必填；{expected_version,reviewer,reason,decisions,issue_resolutions}；返回新版本和事件 |
| POST /api/v1/heritage/publications | Idempotency-Key必填；{work_id,expected_version}，发布门禁通过才新建/复用快照 |
| GET /api/v1/heritage/publications/{id} | 指定历史快照，附historical标记 |
| GET /api/v1/heritage/knowledge | 只列发布版本等于作品当前版本的合格快照，title可选字面包含过滤 |
| GET /health/live, /health/ready | 存活/数据库读写与模式local-review、live_models=false、neo4j=false分别报告 |

### [spec-review-amendment F02/F03] 响应与页面状态

来源写入/读取返回SourceView={source_id,content_hash,media_type,width,height,metadata,created_at}，metadata保留登记字段；图片接口返回原字节。候选导入/作品读取返回WorkView={work_id,version,current_version,historical,payload,events}，payload包含schema_version/source_ids/regions/claims/issues/import_version，raw_import只在v1存在。审核返回{work:WorkView,event:ReviewEvent}；事件含event_id/work_id/from_version/to_version/reviewer/reason/before/after/created_at。发布写入返回{publication_id,work_id,version,claims,created_at}，发布GET另附current_version/historical。列表返回{items:[相应视图],limit,offset,has_more}，limit默认20且1–100，offset默认0且非负；按created_at DESC、ID DESC稳定排序，时间由服务统一输出UTC。知识列表不含候选或旧发布。

错误除code/message/retryable外还返回cause/fix，field_errors可选。例如409为{"code":"VERSION_CONFLICT","message":"审核版本已过期","cause":"当前版本已被另一操作推进","fix":"重新载入当前记录后核对再提交","retryable":false}；503锁忙提示保持同幂等键稍后重试，不生成新键盲重发。消息是数据，页面转义显示。

页面区分加载/空/错误/成功，提交中禁用按钮、同一次操作复用幂等键；失败保留用户编辑并提供重试。所有写入/重放结果仅证明该次操作，不代表当前状态：成功后GET当前作品或当前知识再显示，重放旧结果不能覆盖较新的界面版本。网络等待15秒后提示“结果未知，可用同幂等键重试”，不误称服务端已取消；切换记录前对未提交修改给出提示。

最小候选（来源ID为演示占位，不冒充真实数据）：

```json
{"schema_version":"heritage-review-v1","source_ids":["src_demo"],"regions":[{"id":"r1","source_id":"src_demo","kind":"text","bbox":[0.1,0.1,0.4,0.2],"coordinate_system":"normalized","text":"合成门神示例","text_kind":"exact"}],"claims":[{"id":"c1","predicate":"source_title","object":{"kind":"literal","value":"合成门神示例"},"evidence_refs":["r1"]}],"issues":[]}
```

最小审核：

```json
{"expected_version":1,"reviewer":"local-user","reason":"逐项查看合成页与原文","decisions":[{"claim_id":"c1","action":"approve","support_status":"supported"}],"issue_resolutions":[]}
```

审核action=approve/reject/revise。approve只能裁决已有内容，不能顺便改值；要求valid+非空值/证据+明确supported。revise可改谓词/字面值/证据，重算校验并回到unreviewed，需后续审核。reject保留原内容。不得改来源/Region；原页/坐标需改则从来源创建新候选，不改历史。decisions中Claim不得重复，至少一个decision或issue_resolution；reviewer/reason非空且有长度限制。

## Transactions, Idempotency and Recovery

审核/导入/发布使用BEGIN IMMEDIATE，数据库busy_timeout=5000ms；锁定期间不做图像解码或外部调用。来源先校验解码，事务只保存原件BLOB+元数据。任何异常显式ROLLBACK。幂等scope含操作/资源，request_hash为规范JSON SHA256：[spec-review-amendment F03] 对完整已解析且字段校验通过的请求（包括客户端管理状态，尚未重置）使用UTF-8、sort_keys=true、ensure_ascii=false、separators=(",",":"), allow_nan=false，不改变数组顺序、Unicode内容、缺失字段/null或数值类型；对象键顺序和JSON空白不影响哈希。客户端无需计算哈希；查幂等记录先于版本校验，同键同载荷返回原响应（即使当前已推进），异载荷409。响应JSON与状态在同事务提交。

发布先核当前expected_version及发布门禁，再按(work_id,version)唯一复用；不存在合格approved断言不生成空知识。发布门禁还检查来源 `access_policy`：只允许 `synthetic-only`/`cleared-for-publication`，`local-unverified-no-publication` 等受限来源即使断言全部批准也返回409 PUBLICATION_POLICY_BLOCKED，不生成快照；这是软件门禁，不替代权利人确认。后续review不删除历史快照，knowledge以版本相等过滤，直到新版本发布。整个版本内容、事件和快照均在SQLite，无文件双写恢复窗口；重启直接读取已提交数据，不声称模型调用恢复。

## Safety, Limits and Observability

建议默认：解码后原件8MiB、原请求体12MiB、图像20M像素、每作品4来源/200区域/200断言/50问题；review单批200裁决。超过明确错误，不截断。实现以流式读取计数限制请求体；base64严格解码，先从PNG/JPEG文件头读取宽高做像素预检，再Pillow限定PNG/JPEG、verify后重开load，拒截断与解压炸弹；不得因官方Image.open是lazy就省略完整验证。

原名只显示，不作为磁盘路径；不接受URL，不支持SVG/HTML上传。UI用textContent或严格转义，JSON和模型/OCR文字都不是指令；[spec-review-amendment F04] JS/CSS为同源外部文件，不用inline脚本、事件属性或style属性；CSP为default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'，图片响应加nosniff。预览在上传后用同源原件接口，区域覆盖用canvas，避免blob/data URL或inline布局被策略拦截。服务仅绑定127.0.0.1，允许本地Host；本变更没有认证能力，reviewer为自述标签，不能部署公网。数据库文件和扫描页不入Git；演示合成、真实许可人工确认。

记录request_id、action、work/source/event/publication ID、版本、错误码和耗时，不记录base64原件或完整隐私文本；操作者可读校验问题和历史，不靠控制台猜。health不调用收费模型。未做性能测量，不声明SLA或领域准确率。

## Failure Modes

| 失败 | 处理与回滚 |
|---|---|
| JSON/base64/格式/坐标非法或资源超限 | 422/415/413，不创建来源/作品 |
| 引用丢失/未知谓词 | 持久保存原候选+invalid问题；禁止approve/发布，修订后重校验 |
| 来源元数据冲突/审核旧版本/幂等异载荷 | 409，无新事件、版本或快照 |
| busy/磁盘写入错误 | 503可重试或500不可盲重试；ROLLBACK后原版本保持 |
| 审核进程中断 | 只见提交前或提交后完整事务，重试幂等返回原结果 |
| 证据存在但内容不支持 | 人工判insufficient/disputed，不发布；不是结构自动校验可消灭的风险 |

## Risks / Trade-offs

原件BLOB让库变大→限制单图/提供后续备份策略；全版本JSON重复→演示规模接受，扩容另测。人工可误判→理由、原件和版本可追溯。只支持冻结字面量→遇实体关系明确不支持，后续规格补齐。浏览器环境曾因临时目录EPERM失败→独立记录未运行，不能拿API或DOM适配测试冒充通过。

## Migration Plan

新库schema_version=1初始化事务；遇不支持的非空版本启动失败并说明，不静默修改现有库。代码回滚前停服务并保留库备份；不删原件/事件。部署前固定依赖、用临时库跑合成闭环，再运行本地服务。无生产旧库迁移和远程写入。

## Open Questions

真实资料许可、领域金标准及历史个人贡献只影响公开样本/效果表述，进入相应活动前由用户补齐；本次用合成资料，不用其缺失掩盖实现决策。正式评审执行面未恢复，不标设计门已过。

## Compliance

遵循当前config、FF-0及D-1至D-5；新项目无业务代码，全部新增API/表以拟定契约标识。无既有ADR/共享模型，未触发D-6跨产品共享；旅行数据模型不复用。图示覆盖新系统边界、组件、数据流、生命周期、发布决策和竞争时序。TG-27按不可信候选输入处理，未执行外部模型指令。软件验收、浏览器、真实服务和领域效果分开。
