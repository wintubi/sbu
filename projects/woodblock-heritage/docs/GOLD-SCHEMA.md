# 年画审核金标准 JSONL Schema v0.1

状态：**契约草案，尚无真实金标准数据**。本文件定义“如果要评测/对照，金标准长什么样”，不声称已有标注集、准确率或 P/R/F1。

## 1. 记录格式

一行一个断言级记录（UTF-8 JSONL）：

```json
{
  "gold_id": "gold_000001",
  "work_ref": "work_xxx",
  "source_manifest_sha256": "<来源图片/候选清单SHA256>",
  "schema_version": "heritage-review-v1",
  "claim_id": "c-title",
  "predicate": "source_title",
  "object": {"kind": "literal", "value": "示例值"},
  "evidence_refs": ["r-title"],
  "support_status": "supported",
  "decision": "approve",
  "reviewer": "reviewer-id",
  "reviewed_at": "RFC3339 with offset",
  "notes": "为什么支持/不支持；争议点"
}
```

字段约束：

- `support_status` ∈ `supported / disputed / insufficient`；`decision` ∈ `approve / reject / revise`。
- `object` 只允许字面量；实体关系不在本切片金标准内。
- `evidence_refs` 必须是非空字符串列表；**引用是否真的存在于来源清单**需要 manifest 对照，当前 `validate_gold.py` 只做结构校验，不查存在性。
- `reviewer` 是自述标识；没有认证，不得写成“官方专家”。
- `source_manifest_sha256` 绑定具体来源页/候选版本，防止拿旧标注评新图。
- 不写自由文本长解释到 `object`；解释放 `notes`。

## 2. 标注协议

1. **先冻结来源清单**：图片 SHA256、页面尺寸、Region 坐标、候选 JSON 的 SHA256；之后不改。
2. **独立标注**：至少一名领域人员逐条判断 support 与 decision；如果有第二名，先独立再合议。
3. **合议记录**：分歧不覆盖；保留两条判断 + 最终裁定 + 理由。只有一人时明确写“single-annotator”，不伪造一致性。
4. **禁止推断**：题名成对不等于单图人物身份；清代版不等于纸本印刷日期；说明中的器物不等于图中可见。
5. **许可**：金标准引用原图路径，但公开数据集只在许可允许时发布；否则只发 hash/描述。

## 3. 评测口径（有数据后才可报）

- **断言级 precision/recall/F1**：以 `decision=approve` 且 support=supported 为正例；reject 为负例；revise 按修订后版本计，不重复计原始。
- **证据定位**：evidence_refs 是否命中金标准区域集合；只算“引用存在”不够，需与支持结论一致。
- **三类状态分开**：结构 valid/invalid、support、review 不得合并成一个分数。
- **软件指标 vs 领域指标**：契约/409/回滚等软件测试不进入 P/R/F1；合成数据不进入领域评测。
- **样本分组**：按作品身份/版本分组，开发/回归/验收不共享同一作品；近重复页不能跨组。
- **报告**：必须写样本数、分母、标注人数、合议方式、未决数；没有这些数字就写“未评测”。

## 4. 最小文件布局（建议）

```text
data/gold/
  manifest.json          # 来源/候选/许可/分组/版本
  claims.jsonl           # 断言级金标准
  assertions/
  review-notes/          # 合议/分歧（可私有）
```

## 5. 与当前切片的关系

- 当前审核切片可以导入/裁决/发布，但**还没有金标准**；不能据此报准确率。
- 真实历史页的审核工作表只在私有工作区保留，不随公开子集发布；它不是金标准。
- 历史工程的 `outputs/ablation*.csv` 全是 0，不能当评测结果；论文 92% 没有分母/日志，不能当金标准指标。
- 接入真实 OCR/VLM 后，先把候选转成 `heritage-review-v1`，再由人按本 schema 标注；模型输出本身不是金标准。

## 6. 结构校验

```powershell
python scripts/validate_gold.py data/gold/claims.jsonl
# {"ok": true, "count": N, ...} → exit 0
```

校验器只做结构检查：必填字段、枚举、RFC3339 时间、64 位小写 hex 来源哈希、approve 必须有非空值/证据、重复 `gold_id`、坏 JSON。**它不判断内容真假，也不把未审数据变成金标准。** 当前没有真实 `claims.jsonl`；不要用合成 fixture 充当领域评测集。

## 7. 变更规则

- Schema 变更走独立变更，不静默改字段含义。
- 旧金标准保留版本；新 schema 不覆盖旧记录。
- 任何新增指标必须写清分母/样本/标注方式，否则只算探索性观察。
