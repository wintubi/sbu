# Tasks

状态：A/B/C 后端与页面资源已实施，`python -m pytest` 47 passed，真实 HTTP 合成链路、Chrome/CDP 完整页面流程与来源许可门禁测试已跑通；独立专业设计门仍未通过。Requirement来源：[证据目录规格](specs/evidence-catalog/spec.md)与[审核发布规格](specs/reviewed-publication/spec.md)。切片和边界见[设计](design.md)。已实现部分按测试证据勾选，未验证项保持未勾。

## 0. 历史复用基线（实施前）

- [ ] 0.1 依据 `planning/HERITAGE-REUSE-MAP.md` 确认复用边界：`schema_m3`/`printmaking_vocab`/`validation.pipeline`/`neo4j_writer` 中哪些直接复用、哪些只借语义、哪些不改；记录论文23/19、本地27/31、远端15/19的版本差异；验证：复用清单经设计评审确认，不把历史论文数字当当前代码事实，不复制私人扫描页或`.env`。（EC-04、RP-04）

## 1. A：来源与候选证据可查看（Blocked-by: 设计门）

- [x] 1.1 固定Python/API/Pillow运行与测试依赖，提供本地启动和临时库入口，初始化设计中的完整表/约束；验证：新库启动、未知库版本拒绝、ready/live和退出清理测试；同步安装说明。（EC-01、RP-07、RP-08）— 已完成：`tests/test_atomicity.py`、README/ACCEPTANCE。
- [x] 1.2 实现有限请求体、严格base64与PNG/JPEG完整解码，哈希去重/元数据冲突及原图读取；验证：有效/截断/格式错/字节像素超限/同内容冲突/无任意路径访问，原件和哈希一致；补来源接口示例。（EC-01、EC-02、EC-06）— 已完成：`tests/test_sources.py`。
- [x] 1.3 实现候选导入、冻结字面量Schema、像素归一化、局部ID和证据校验，保留invalid候选及原输入；验证：精确坐标例、缺引用、未知谓词、客户端伪造approved/resolved、unsupported实体、区域与断言重复ID/超限、原始导入快照保留，初始知识为空；补旧候选到v1的显式适配和JSON例。[spec-review-amendment F01/F05/F06]（EC-03、EC-04、EC-05、RP-03）— 已完成：`tests/test_works.py`、`tools/prepare_legacy_candidate.py`；旧候选工具14项测试见上轮。
- [x] 1.4 提供来源上传、候选导入、原页/区域/原文/问题/三状态预览的页面；验证：实际浏览器载入合成资料、证据回查和恶意文字安全显示；无法启动浏览器时标未运行，不能据DOM适配测试打勾。（EC-06、RP-06、RP-08）— 已完成：Chrome/CDP 完整流程 + `ui_security_cdp.py`。

## 2. B：审核、版本与审计（Blocked-by: A）

- [x] 2.1 实现approve/reject/revise及人工问题处置，结构问题由重校验控制；验证：批准有效supported、混合改值批准拒绝、改后回unreviewed、无效断言reject不伪造修复，初始版本可读；补审核示例。（EC-05、RP-01、RP-04）— 已完成：`tests/test_reviews.py`。
- [x] 2.2 原子保存审核事件/不可变版本/当前版本，加入预期版本校验；验证：两个独立连接同版本竞争一成一冲突，注入中途写失败全回滚，旧记录不覆盖；补事务边界说明。（RP-02、RP-07）— 已完成：`tests/test_concurrency.py`、`tests/test_atomicity.py`。
- [x] 2.3 完成导入/审核/发布的作用域幂等机制和错误契约；验证：同键同载荷重试、同键异载荷409、跨资源作用域分离、审核后再更新仍可重放原结果、对象键重排和JSON空白不改变幂等哈希、缺键422，并逐项核对响应DTO；补重试说明。[spec-review-amendment F02/F03]（RP-03、RP-02）— 已完成：`tests/test_works.py`、`tests/test_reviews.py`、`tests/test_publications.py`、`tests/test_atomicity.py`。
- [x] 2.4 页面支持修改/驳回/批准、理由、版本历史和冲突后重新载入；验证：实际浏览器演示修订后再批准、页面驳回后当前知识清空、旧版本内容与事件仍可查；同步截图与可复现步骤。（RP-01、RP-06、EC-06）— 已完成：`ui_full_e2e_cdp.py`（含 ui_reject）。

## 3. C：发布、当前知识与完整演示（Blocked-by: B）

- [x] 3.1 实现发布门禁、不可变快照、作品版本唯一性；验证：未审核/无效/未支持/阻断未决/全驳回均不能发布，reject坏断言+approve好断言只发布好断言；重复发布不新增。（RP-04、RP-05）— 已完成：`tests/test_publications.py`、`scripts/demo_e2e.py`。
- [x] 3.2 实现当前知识查询、指定历史快照与过期过滤；验证：审核推进后当前视图隐藏旧快照、旧发布新请求409、历史ID仍可读；补语义说明。（RP-05、RP-03）— 已完成：`tests/test_publications.py`。
- [ ] 3.3 页面贯通发布/查询/历史和证据回查；验证：合成正常闭环、阻断提示、双页面旧版本冲突、重放后重取当前状态及更新后重发，覆盖加载/空/错误/结果未知提示，记录真实浏览器证据与未运行项。[spec-review-amendment F03]（RP-06、EC-06）
- [x] 3.4 完成局部Host/Origin检查、CSP/文本转义、资源限额与可定位日志；验证：跨源写拒绝、恶意候选不执行、日志无base64原件；不把reviewer自述当认证。（RP-08、EC-01、EC-06）— 已完成：`logging_utils.py`、`test_logging_and_limits.py`、`ui_security_cdp.py`。
- [ ] 3.5 独立复跑单元/集成、真实HTTP合成流程、两连接竞争、故障回滚和重启持久性；浏览器/真实服务/领域效果分开报告；补启动、演示、限制、本人讲解练习与贡献边界。（EC-01至EC-06、RP-01至RP-08）
- [x] 3.6 用本机 Chrome/CDP 跑通完整页面流程：上传→导入→批准→旧版本409重载→修订→处置→发布→当前知识→历史只读；并验证 canvas 命中、恶意文本不执行、双标签页冲突；验证：`ui_full_e2e_cdp.py`、`ui_security_cdp.py`、`ui_multitab_cdp.py`，截图/记录在 `docs/evidence/`；明确未覆盖 canvas 拖拽、不用 Playwright 冒充。（RP-06、EC-06）
- [x] 3.7 来源 `access_policy` 固定枚举与发布白名单：未知值422；`local-unverified-no-publication` 即使断言全批准也409 PUBLICATION_POLICY_BLOCKED，不生成快照；验证：`tests/test_publication_policy.py`、`tests/test_sources.py`。（RP-04）

## 测试覆盖图

```text
来源/坐标/Schema -> 单元 + API契约
SQLite事务/幂等/版本 -> 两连接集成 + 故障注入 + 重启
发布门禁/当前与历史 -> API集成 + 原始DB计数
页面上传/审核/冲突/发布 -> 真实浏览器E2E
外部OCR/VLM/Neo4j/领域准确性 -> 本变更未运行，后续真实渠道及金标准验证
```

| Requirement | 任务 | 主要验证 |
|---|---|---|
| EC-01 | 1.1/1.2/3.4/3.5 | 文件/请求/像素边界与实际解码 |
| EC-02 | 1.2/3.5 | 内容幂等与元数据冲突 |
| EC-03 | 1.3/3.5 | 坐标换算/非有限/重复/来源边界 |
| EC-04 | 1.3/3.5 | 导入不能伪造审批/实体不支持 |
| EC-05 | 1.3/2.1/3.5 | 引用合法不等于支持；invalid不能批准 |
| EC-06 | 1.2/1.4/2.4/3.3/3.4/3.5 | 证据访问/显示/恶意数据不执行 |
| RP-01 | 2.1/2.4/3.5 | 裁决/改值/理由/历史 |
| RP-02 | 2.2/2.3/3.5 | CAS竞争与事务回滚 |
| RP-03 | 1.3/2.3/3.2/3.5 | 幂等作用域/旧响应重放 |
| RP-04 | 2.1/3.1/3.7/3.5 | 阻断/驳回保留/来源许可与发布筛选 |
| RP-05 | 3.1/3.2/3.5 | 当前版本/历史快照/唯一性 |
| RP-06 | 1.4/2.4/3.3/3.5 | 真实浏览器及提示 |
| RP-07 | 1.1/2.2/3.5 | 健康/锁忙/重启与审计持久 |
| RP-08 | 1.1/1.4/3.4/3.5 | 本地边界及如实验证报告 |

## Workflow follow-up

- 先完成正式设计评审与设计门；当前规格生成/CLI校验不代表设计通过。
- 通过后由sdflow-ship按既定票据管线规划/执行，完整代码评审与verify后再归档；任务checkbox仅在实际证据存在时更新。
- 不将本地软件切片描述为全部原产品完成，不预写领域准确率、创新提升率或本人独立完成的历史贡献。
