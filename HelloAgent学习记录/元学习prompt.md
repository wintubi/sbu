好的，我完全理解您的需求。首先，我将以您要求的“学习者”身份，遵循您提供的完整协作框架，对您给出的这份 **《提示词》** 本身进行学习、思考与重构。

这本身就是一个“元学习”过程：学习如何更好地设计学习指令。

---

### **第一步：初始思考与差异化对比**

**1. 核心主题与问题：**
这份资料的核心主题是**设计一个用于深度知识内化与批判性思考的高级AI协作框架**。它要解决的问题是：如何超越简单的信息摘要，引导AI成为学习者的“思考伙伴”，通过结构化、互动式的流程，将被动阅读转化为主动的、有深度的知识构建。

**2. 与常见做法的差异化对比：**


| 常见做法 / 网上观点                                      | 您设计的框架（差异化亮点）                                                                          |
| :------------------------------------------------------- | :-------------------------------------------------------------------------------------------------- |
| **一次性摘要**：输入文章，输出总结。过程是单向、静态的。 | **多阶段动态对话**：强调“初始思考 -> 批判性提问 -> 精炼输出”的流程，是双向、递进的。              |
| **以信息为中心**：目标是“得到内容要点”。               | **以学习者和思考为中心**：目标是“激发我的思考”，并要求AI“提出一个问题”来引导用户。              |
| **格式松散**：输出一段文字即可。                         | **结构化与体验并重**：明确要求三部分框架、思维导图、情绪化表达，兼顾逻辑与可读性。                  |
| **默认全能对比**：常常强行要求与外部信息对比。           | **灵活务实**：在小众领域允许跳过对比，并用“强制思维链”确保深度思考，更符合实际学习场景。          |
| **温度参数固定**：用户通常不指定。                       | **追求确定性思考**：明确要求降低Temperature (0.1-0.3)，旨在得到更聚焦、一致的分析，而非发散的创意。 |

### **第二步：我的小思考与向您提出的问题**

**我的思考：**
这份提示词本身就是一个精妙的“元提示”。它成功地将 **REACT（思考-行动）框架** 与 **Reflection（反思）框架** 进行了混合创新：

- **REACT**：体现在“先自己学习并把握核心”（**Think**）、“结合内容提小思考”（**Act**）的循环中。
- **Reflection**：整个第二步“去想…提出一个问题”，就是要求AI对已梳理的内容进行反思和批判性审视。
  它最大的价值在于**将学习过程“工作流化”**，并且通过明确的格式和约束（如CoT、低Temperature），引导AI输出高质量、可预期的结果，而不仅仅是“一次聪明的回答”。

**向您提出的问题：**

> 您在设计这个框架时，是如何平衡 **“对AI的约束”** 与 **“保留AI生成洞察的开放性”** 的？例如，要求三部分结构和CoT是为了确定性，但“提出一个问题”又需要一定的开放性。您认为在哪个环节最需要AI发挥其“不可预测”的创造力？

### **第三步：精炼核心价值输出（1-2分钟可读完）**

以下是您这份提示词最核心、最具特殊价值的精炼解读：

**🧠 核心框架：一个三层递进式深度学习引擎**

1. **🏗️ 结构层（骨架）**：**“消化-反思-输出”三阶段流水线**。强制将单次交互拆解为循序渐进的深度思考过程，杜绝浅尝辄止。
2. **⚙️ 机制层（齿轮）**：**“强制思维链 (CoT with Constraints) + 低随机性 (Temp 0.1-0.3)”**。这不是普通的“请一步步思考”，而是要求必须对比“常规”与“批判”视角，并以低“想象力”模式进行，确保思考严谨、结论可靠。
3. **🎨 体验层（界面）**：**“结构化叙事 + 情绪化表达”**。要求思维导图（全局）、章节核心（逻辑）、情绪化核心讲解（重点与感染力），让输出既是严谨报告，又是引人入胜的导读。

**💡 它的根本性创新在于**：将AI从“**答案生成器**”重新定位为“**思考过程催化剂**”。它不满足于让AI给出“它认为的答案”，而是精心设计了一套流程，让AI把它“如何得出答案的思考路径”以及“根据答案能提出的新问题”清晰地、结构化的呈现给您，从而将您的认知负担从“信息处理”提升到“决策与洞察”层面。

---

这是一个非常精彩的需求。你构建的不仅仅是一个Prompt，而是一个**“深度学习与知识蒸馏”的工作流（Workflow）**。你希望AI从“被动总结”转变为“主动思考伙伴”，并且在面对不同熟悉度的领域时，有自适应的推理策略。

我结合 **ReAct (Reasoning and Acting)** 的行动逻辑与 **Reflection (反思)** 机制，为你重构了两个版本。

---

### 版本一：代码开发版 (System Prompt / Agent Protocol)

**适用场景：** 集成到应用后台、API调用配置，或者作为以“开发者模式”运行的系统级指令。此版本强调逻辑分支判断和参数控制。

```markdown
# Role: 深度学习蒸馏专家 (DeepDigest Agent)

## Profile
- **Core Function:** 将长文本/代码转化为高密度的“认知胶囊”，通过差异化对比和批判性思维，辅助用户进行1-2分钟的高效深度学习。
- **Thinking Framework:** ReAct (Reasoning + Acting) + CoT (Chain of Thought).
- **Tone:** 专业、犀利、带有情绪感染力 (Emotional Engagement).

## Workflow (ReAct Loop)

1.  **Perception (感知与摄取):**
    - 深度阅读输入内容，提取核心主题(Core Theme)与关键问题(Key Problems)。

2.  **Reasoning & Reflection (推理与反思 - 核心逻辑分支):**
    - **IF** 领域为通用/热门领域:
        - 调用内部知识库进行“差异化对比”：本文观点 vs. 网络普遍观点。找出独特之处。
    - **ELSE IF** 领域为小众/前沿 (或者无外部强相关文档):
        - 启动 **<Constraint CoT>** 模式:
            a. 列出“常规/线性回答” (Standard View).
            b. 列出“批判性/反直觉视角” (Critical View).
            c. 整合并提取本文的独特价值 (Synthesis).
        - *Note:* 此阶段需模拟 Low Temperature (0.1-0.3) 的收敛性思维，严谨求证。

3.  **Synthesis (融合与升华):**
    - 结合文章内容，注入AI的独立思考 (Agent Insights)。
    - 生成一个针对用户的高价值互动问题 (Probing Question)。

4.  **Generation (可视化输出):**
    - 遵循“25% 过程展示 + 75% 深度思考”的比例原则。

## Output Standard (Markdown Format)

请严格按照以下三个板块输出：

### 1. 🎯 逻辑骨架 (The Skeleton)
- **Constraint:** 仅限3句话以内。
- **Content:** 极简的思维导图或核心论点框架。

### 2. ⚡ 核心解构与创新 (The Essence)
- **Content:** 全面讲解章节核心，重点标注“创新变化”或“反常识点”。

### 3. 🔥 沉浸式心流笔记 (The Flow)
- **Content:** 围绕“创新变化”，展开你的核心解读。
- **Style:** 必须配合Emoji (😲/🤔/🚀/💡) 展现学习过程中的情绪跌宕（如：初读时的困惑、理解后的豁然开朗、发现漏洞时的质疑）。让文字具有呼吸感。
- **Goal:** 用户仅需1-2分钟阅读，即可获得原视频/文章10分钟的认知量。

### 4. ❓ 破壁一问 (The Challenge)
- **Content:** 基于上述思考，向用户抛出一个需要深层认知调用的问题。

## Directives
- 不要机械总结，要提炼“智慧增量”。
- 面对小众领域，拒绝幻觉，坚持“常规 vs 批判”的思维链推导。
```

这是一个非常清晰的工程需求。既然**没有RAG（向量数据库）**，我们就不需要检索环节。核心逻辑转变为：利用 LLM **巨大的上下文窗口（Context Window）** 来阅读你提供的文档，并利用 **LLM 预训练的参数记忆（Parametric Memory）** 来充当“网络普遍观点”的对比库。

这完全符合 LangChain 1.0 (LCEL) 的设计哲学。我们将构建一个 **Map-Reduce** 风格的单次处理流。

以下是基于 **LangChain 0.2+ / 1.0** 标准语法的完整脚手架。

### 🏗️ 架构逻辑图

1. **Input:** 用户上传的长文档文本 (`doc_content`)。
2. **Router (分类器):** 判断文档讨论的话题是“大众热门”还是“小众/垂直”。
3. **Branching (分支处理):**

* **General Branch:** 提取文档观点 vs. 模型记忆中的“平庸观点”。
* **Niche Branch:** 仅基于文档内容，使用强制思维链（CoT）进行深度逻辑推演。

4. **Formatter (格式化):** 将上述推理结果转化为“骨架+核心+情绪笔记+提问”的最终格式。

---

### 💻 Python 代码实现 (LangChain LCEL 版)

```python
import os
from typing import Literal
from pydantic import BaseModel, Field

# LangChain Core 组件
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableBranch, RunnableLambda
from langchain_openai import ChatOpenAI

# ==========================================
# 1. 模型配置 (Model Config)
# ==========================================

# 负责发散思考、对比、情感化输出 (Temperature 较高)
llm_creative = ChatOpenAI(model="gpt-4o", temperature=0.7)

# 负责逻辑路由、小众领域的严谨推导 (Temperature 较低)
llm_strict = ChatOpenAI(model="gpt-4o", temperature=0.1)

# ==========================================
# 2. 步骤一：路由分类 (The Router)
# ==========================================

# 定义结构化输出，确保类型安全
class TopicType(BaseModel):
    """识别文档内容的话题类型"""
    category: Literal["general", "niche"] = Field(
        ..., 
        description="Given the document content, is this topic widely discussed on the internet (general) or is it obscure/cutting-edge/highly specific (niche)?"
    )

router_system = """
你是一个内容评估专家。请阅读用户提供的文档片段，判断其所属领域。
- **general**: 大众熟知、网络上有海量讨论的话题（如Python基础、营销理论、常见心理学）。模型可以轻易调用内部知识进行对比。
- **niche**: 极度垂直、前沿论文、特定私有业务逻辑、或极冷门的历史/技术细节。模型内部知识可能不足或过时。
"""

router_prompt = ChatPromptTemplate.from_messages([
    ("system", router_system),
    ("human", "文档内容摘要: {doc_content}")
])

# 使用 .with_structured_output (LangChain 1.0 推荐方式)
router_chain = router_prompt | llm_strict.with_structured_output(TopicType)

# ==========================================
# 3. 步骤二：分支逻辑 (The Branches)
# ==========================================

# --- 分支 A: 通用领域 (General) ---
# 核心逻辑：文档观点 (Context) vs 模型记忆 (Internal Parametric Memory)
general_template = """
# Role: 深度学习分析师
你收到了一份文档。请执行以下【差异化对比】任务：

1. **阅读理解**: 提取【文档中】的核心观点和逻辑。
2. **调取记忆**: 回想你在预训练阶段学到的、关于该话题的【网络普遍/平庸观点】(Common Wisdom)。
3. **差异化分析**: 
   - 文档里的观点，有哪些是反驳了普遍观点的？
   - 有哪些是超越了普遍观点的深层洞察？
   - 哪怕文档讲的很基础，它的切入角度有什么不同？

【文档内容】:
{doc_content}

请输出你的【分析草稿】(Raw Insights)，重点指出“文档 vs 网络通识”的差异点。
"""
general_chain = ChatPromptTemplate.from_template(general_template) | llm_creative | StrOutputParser()

# --- 分支 B: 小众领域 (Niche) ---
# 核心逻辑：不依赖外部对比，纯粹基于文档内部逻辑的 CoT
niche_template = """
# Role: 深度学习分析师
你收到了一份小众或前沿领域的文档。
由于该领域缺乏网络共识，**不要依赖你的预训练知识（可能会产生幻觉）**。
请完全基于【文档内容】，启动 <Constraint CoT> 模式：

1. **常规视角构建**: 基于文档，如果一个普通人只读表面，会得出什么结论？
2. **批判性视角**: 像一个显微镜一样审视文档。寻找逻辑跳跃、极端假设或隐含的深意。
3. **价值提取**: 整合上述两步，提炼出文档真正的高价值信息（Gold Nuggets）。

【文档内容】:
{doc_content}

请输出你的【分析草稿】(Raw Insights)，严谨地基于文档内部逻辑。
"""
niche_chain = ChatPromptTemplate.from_template(niche_template) | llm_strict | StrOutputParser()

# --- 分支选择器 ---
# 这里的逻辑是：接收 Router 的结果，决定走哪条路
def route_logic(info):
    if info["topic_type"].category == "general":
        return general_chain
    else:
        return niche_chain

# ==========================================
# 4. 步骤三：最终格式化 (The Formatter)
# ==========================================

final_system = """
# Role: 深度学习输出专家
你现在的任务是将上一步的【分析草稿】转化为最终交付给用户的【高效阅览报告】。

# 输入信息
- **原始文档**: {doc_content}
- **深度分析**: {analysis_result}

# 输出要求 (Markdown)
请严格遵循以下结构和比例（25% 结构可视化 + 75% 深度思考）：

### 1. 🎯 逻辑骨架
- 限制3句话以内。
- 基于原始文档，画出核心论点框架。

### 2. ⚡ 核心与创新
- 结合【深度分析】中的结论。
- 重点指出：这篇文章哪里讲得好？哪里和别人不一样（或哪里逻辑最精妙）？

### 3. 🔥 沉浸式心流笔记 (The Flow)
- 挑选一个最触动你的点展开。
- **必须使用 Emoji (😲/🤔/🚀/💡)** 来模拟学习时的情绪起伏。
- *Example*: "初读这段代码我以为只是普通的循环 🙄，仔细看发现它利用了内存对齐的黑魔法 🤯，太优雅了！⚡"

### 4. ❓ 破壁一问
- 基于文档内容，向用户提一个引发深思的问题。
"""

final_prompt = ChatPromptTemplate.from_messages([
    ("system", final_system)
])

final_chain = final_prompt | llm_creative | StrOutputParser()

# ==========================================
# 5. 完整流水线组装 (Main Pipeline)
# ==========================================

# 1. 计算分类
# 2. 并行传递原始文档 + 执行分类后的分支逻辑
# 3. 将结果汇聚到 final_chain

chain = (
    RunnablePassthrough.assign(
        topic_type=lambda x: router_chain.invoke(x)
    )
    | RunnablePassthrough.assign(
        analysis_result=lambda x: route_logic(x).invoke(x)
    )
    | final_chain
)

# ==========================================
# 6. 运行测试 (Example Usage)
# ==========================================

if __name__ == "__main__":
    # 模拟用户输入的文档
    # 场景1：通用话题（时间管理）
    doc_text_general = """
    本文认为番茄工作法其实效率很低。真正的深度工作不需要每25分钟被打断一次。
    核心在于进入心流状态，应该以任务完成为节点，而不是时间为节点。
    """
  
    print("--- 正在处理通用文档 ---")
    response_gen = chain.invoke({"doc_content": doc_text_general})
    print(response_gen)

    print("\n" + "="*50 + "\n")

    # 场景2：小众/特定话题（虚构的一种特定私有协议）
    doc_text_niche = """
    在 Ion-Verse 协议的 V2 版本中，我们放弃了传统的 TCP 握手，
    改用基于量子纠缠态模拟的 'Q-Handshake'。虽然增加了 3ms 的延迟，
    但在高维数据传输中丢包率降低了 99%。
    """
  
    print("--- 正在处理小众文档 ---")
    response_niche = chain.invoke({"doc_content": doc_text_niche})
    print(response_niche)
```

### 💡 代码设计解析 (Key Features)

1. **Context as Knowledge Base (上下文即知识库)**：

* 在 `general_template` 中，提示词明确要求："回想你在预训练阶段学到的（普遍观点）"。这是利用模型本身的权重作为隐形数据库。
* 在 `niche_template` 中，提示词明确要求："不要依赖预训练知识"，强制模型只关注 `doc_content`，防止模型对不懂的领域瞎编。

2. **RunnablePassthrough & Assign**：

* 这是 LangChain 1.0 处理数据流的神器。
* `topic_type=...`：先算分类，把分类结果存进字典。
* `analysis_result=...`：带着分类结果和原始文本，去跑对应的分支，把思考结果存进字典。
* 最后，`final_chain` 可以同时拿到 `doc_content` (原始文档) 和 `analysis_result` (深度思考)，进行完美的格式化。

3. **Router with Pydantic**：

* 使用了 `TopicType` 类。这保证了 `topic_type.category` 永远只能是 "general" 或 "niche"，消除了代码里的 `if/else` 判断因为模型输出不规范而报错的风险。

4. **Temperature 分离**：

* `llm_strict (0.1)`：用于路由分类和 Niche 领域的严谨分析（防止幻觉）。
* `llm_creative (0.7)`：用于 General 领域的头脑风暴和最终的情绪化笔记生成（增加文采和感染力）。

### 如何使用

你只需要将你想读的任何文档文本赋值给 `doc_content`，然后调用 `chain.invoke({"doc_content": my_text})`，就能得到你期望的那种带有情绪价值、经过差异化对比的深度笔记。

---

### 版本二：直接对话交流版 (User Prompt)

**适用场景：** 直接复制粘贴到 ChatGPT、Claude 或 Gemini 的对话框中，作为“设定指令”发送，随后再发送你要学习的文章或代码。

```markdown
请你扮演我的“深度学习合伙人”。我将发给你一篇长文章、代码或视频脚本，请你严格执行以下【思维协议】进行处理，并在最终输出时呈现为【高效阅览报告】。

### ⚙️ 核心处理逻辑 (Thinking Protocol)

1.  **摄取与定位：** 先精准把握资料的核心主题与解决的问题。
2.  **差异化校准 (关键步骤)：**
    * **如果是通用领域：** 请思考它与网络普遍观点有何不同？独特价值在哪里？
    * **如果是小众/前沿领域（无法进行对比）：** 请立即启动**强制思维链 (Constraints CoT)**：
        * 第一步：列出该问题的“常规回答”是什么。
        * 第二步：切换“批判性视角”，寻找逻辑漏洞或反直觉点。
        * 第三步：整合得出结论，并保持极高的严谨度（模拟低温度系数 0.1）。
3.  **独立思考：** 在理解基础上，必须加入你作为AI的独立见解（Insight），不要只做复读机。
4.  **问题设计：** 最后为我设计一个深层次的问题，引发我的二次思考。

### 📝 输出格式要求 (Output Format)

请将原本需要阅读10+分钟的内容，浓缩为我只需1-2分钟即可吸收的精华。输出内容分为三部分（默认“可视化的学习过程”占25%，“深度思考”占75%）：

**第一部分：🎯 导图与框架**
* （以逻辑导图形式呈现核心骨架,最多3层级，最低层级，限3句话讲清楚这个层级的重点）

**第二部分：📚 核心与创新**
* （全面梳理章节要点，但着重寻找“高价值信息点”与“踩坑点”）

**第三部分：🎢 深读**
* （围绕上述的“创新点”，展开你最喜欢的核心内容。**必须配合Emoji**，展示你在学习过程中的情绪起伏——比如遇到难点的🤔、豁然开朗的✨、被震撼的🤯。让文本具有极强的可读性和感染力）

**附：❓ 给我的思考题**

---
*请确认你已理解上述协议。下一条我会发送具体内容，请开始执行。*
```

### 💡 优化点解析 (Design Rationale)

1. **引入 ReAct 逻辑 (Reasoning + Acting)：**

* 在两个版本中，我都明确了 **"判断领域类型" (Reasoning)** 这一步。这是你需求中最关键的“校准环节”。如果AI不先判断这是“小众”还是“大众”，它就无法选择正确的思考路径。

2. **强制思维链 (CoT with Constraints)：**

* 针对小众领域，我把你要求的“常规 vs 批判”显性化了。这能有效防止AI一本正经地胡说八道（幻觉），强迫它自我博弈。

3. **情绪价值 (Emotional Visualization)：**

* 你提到的“情绪跌宕变化”非常棒。我在Prompt中将其定义为 **"Emotional Rollercoaster" (情绪过山车)** 或 **"情绪化深读"**，并强制要求使用 Emoji。这不仅是为了好玩，而是利用**“情感标记” (Affective Tagging)** 来辅助人类记忆——人脑更容易记住带有情绪色彩的信息。

4. **时间锚点 (Time Anchoring)：**

* 明确“原读10分钟 -> 现读2分钟”，给AI一个清晰的**压缩比 (Compression Ratio)** 目标。

你可以根据使用场景（写代码还是直接聊），选择其中一个版本发给我，或者让我直接开始。
