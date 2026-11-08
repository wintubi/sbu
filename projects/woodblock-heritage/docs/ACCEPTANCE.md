# 验收记录（本地切片）

日期：2026-11-08。环境：Windows、Python 3.12.9、FastAPI 0.115.12、Pydantic 2.11.2、Pillow 11.0.0、httpx 0.28.1、pytest 9.0.3。所有数据为合成图/合成候选，不代表年画领域效果。

## 1. 离线测试

```powershell
cd woodblock-heritage
python -m pytest
```

结果：**47 passed in 2.17s**。覆盖：

- 生命周期：应用退出后自有 Store 连接关闭；未知数据库 schema 版本拒绝启动；live/ready 可读。
- 限额：原件字节上限与像素上限分别返回 413；单作品超过 200 条断言在写库前返回 422。
- 来源：有效 PNG、内容哈希去重、同内容元数据冲突 409、坏 base64 422、截断图片 415、图片字节与 nosniff。
- 候选：客户端伪造 approved/supported 被重置；重复区域/断言 ID 422；未知谓词与缺失证据保留为 invalid；实体对象 422；像素坐标归一化；未知 schema/来源 422；缺幂等键 422。
- 审核：批准生成不可变 v2 与事件；旧版本仍可读；同键同载荷重放；同键异载荷 409；过期版本 409；无效断言不能批准；revise 回到 unreviewed；补证据可修复；结构问题不能只靠理由关闭。
- 原子性：审核中途注入事件写入异常，整个事务回滚，版本/事件/幂等行都不留下。
- 重放：先审核 v2、再推进 v3，之后用旧幂等键重放 v1 请求，仍返回原 v2 响应而不是误报冲突。
- 幂等：JSON 对象键重排与空白变化不改变幂等哈希。
- 并发：两个独立 SQLite 连接、同一 expected_version、同时提交 approve/reject；**一个成功、一个 409 VERSION_CONFLICT**，仅一个事件。
- 许可策略：`access_policy` 只接受 `synthetic-only` / `local-unverified-no-publication` / `cleared-for-publication`；未知值 422。`local-unverified-no-publication` 即使断言已批准，发布仍 409 `PUBLICATION_POLICY_BLOCKED`，不生成快照。
- 发布：未审核 409；两人批准后发布 201；同版本重复发布返回原快照；审核推进后当前知识隐藏旧快照、历史快照仍可读且 `historical=true`；驳回坏断言不阻断好断言；发布幂等冲突 409。
- 重启：关闭服务后新进程读取同一库，版本/事件/原件仍在。
- 访问边界：每个响应有 `X-Request-ID`；`heritage.access` 记录 method/path/status/耗时，不含请求体或图片 base64；非本地 Host 403。
- 分页：`/works` 与 `/knowledge` 支持 limit/offset，返回 count/total/has_more；limit=0 返回 422。
- 页面：历史版本下拉可切到 v2，显示“历史·只读”，审核/发布、断言裁决、问题复选框禁用，切回当前版本恢复；发布历史列出该作品的当前/历史快照。
- 金标准结构：`validate_gold.py` 拒绝缺字段、非法枚举、approve 空证据/空值、重复 gold_id、坏 JSON；不判断内容真假。
- 页面资源：`/` 带 CSP（`default-src 'none'`、`script-src 'self'`），无内联 `<script>`/`style=`；`/static/app.js`、`style.css` 可加载。

## 2. 真实 HTTP 冒烟

启动：

```powershell
$env:HERITAGE_DB = "data/demo.sqlite3"
$env:HERITAGE_PORT = "8770"
python run.py
```

另开进程：

```powershell
python scripts/demo_e2e.py http://127.0.0.1:8770
```

实际输出：

```text
ready=ready source=src_ee2c8ce071d64dac work=work_21050f93f89a4376
publication=pub_45566d85fbd24ea1 version=2 claims=2
knowledge_count=1 title=合成门神示例
```

脚本断言了 `/health/ready`、`/` CSP、来源 201、作品 201、审核 200 且 current_version=2、发布 201、当前知识 count=1。没有请求真实高德/模型/OCR/Neo4j。

## 3. 页面验证（Chrome / CDP）

`scripts/ui_full_e2e_cdp.py` 使用本机 Chrome 的 DevTools Protocol（不使用 Playwright 临时目录），完成完整页面流程：

```text
work=work_032052bf62bb4e78 upload=true revise=true conflict_reload=true publish=true
knowledge=合成门神示例（修订）pub_79b92e98b95347b4 · 作品 v6 · 1 条
```

实际页面动作：真实文件上传 → 生成/导入候选 → 2 条断言批准（v2）→ 用另一个客户端推进到 v3 → 页面仍按 v2 提交，收到 409 后重新载入 v3 → 修订标题 → 批准（v5）→ 勾选并处置配对问题（v6）→ 发布 → 当前知识出现修订后的 1 条断言 → 切到 v2 显示“历史·只读”，审核/发布、断言裁决、问题复选框均禁用，并显示修订前值 → 切回 v6 显示修订后值 → 页面驳回分类断言（v7），当前知识清空，v6 快照仍可历史回查。截图：[完整界面证据](evidence/ui-full-e2e.png)，输出记录：[chrome-cdp-full.txt](evidence/chrome-cdp-full.txt)。

已覆盖：真实浏览器文件上传、页面 JS fetch、候选导入、三状态/问题展示、审核提交、409 冲突后的重载、修订/批准/页面驳回、问题处置、发布、当前知识渲染、发布历史列表、历史版本只读切换、CSP 无内联脚本、canvas 尺寸。

补充的 T3 浏览器检查：

```text
canvas click -> 命中 r-title（text）：合成门神示例
hostile text -> work=work_e12db152098d43b2 injected_elements=0 xss=undefined literal_text=true
two tabs -> work=work_3b8ca37ff8294efc tab_a=v2 tab_b_reloaded_v2 conflict_handled=true
```

即：canvas 点击能命中区域；`<b>`/`<img onerror>` 作为文本显示、没有注入元素或执行；两个真实标签页同版本提交，一个成功、另一个 409 后重载当前版本。记录：[chrome-t3.txt](evidence/chrome-t3.txt)。

未覆盖：canvas 拖拽/缩放、触摸手势；Playwright 仍因临时目录 EPERM 未运行。因此这是“Chrome/CDP 页面流程”，不是覆盖所有交互的完整 E2E。

## 3.1 原始数据边界

公开子集**不包含**历史扫描页、原始候选、历史导入脚本或本地数据库；这些只在私有工作区用于本地核对，图片/数据库不入 Git。这里不提供原始数据、原始页路径或导入结果，避免把未核许可的资料带到公开仓库。

## 4. 首次失败与修正

首次 `python -m pytest`：**22 passed, 1 failed**。失败用例为 `test_rejected_invalid_claim_does_not_block_good_claim`：测试只驳回了坏断言，另一个断言 `c-category` 仍是 unreviewed，发布门禁按设计拒绝。修正的是**测试预期**（同时驳回/裁决所有断言），不是放松门禁。最终 **47 passed**。

真实 HTTP 冒烟第一次失败于 `httpx.InvalidURL: Invalid port: ':1]'`：本机 `NO_PROXY` 含 `[::1]`，httpx 0.28 解析该 token 失败。脚本改为 `trust_env=False`（本地回环不应走系统代理），随后通过。这是测试脚本的环境兼容修正，不改业务逻辑。

## 5. 未运行 / 未证明

- Playwright 完整 E2E、canvas 拖拽/缩放、触摸手势；Chrome CDP 已覆盖上传/导入/冲突重载/修订/处置/发布、canvas 命中、恶意文本、双标签页冲突。
- 真实 OCR/VLM 抽取、Neo4j 发布与对账。
- 真实年画原件的公开发布许可、金标准、领域准确率、论文 92% 口径复核；本地导入不等于可发布。
- 多用户、公网认证、性能/并发容量；当前是本地单用户、单进程 SQLite。
- 大规模数据（200 区域/200 断言上限内）和压力测试。
