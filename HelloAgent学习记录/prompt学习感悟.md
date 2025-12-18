<div align="center">
<img src="https://raw.githubusercontent.com/datawhalechina/Hello-Agents/main/docs/images/4-figures/4-4.png" alt="" width="70%"/>
<br>
<em>图1: 不同 Agent Loop 的选择策略</em>

</div>

## 习题

> <strong>提示</strong>:部分习题没有标准答案，重点在于培养学习者对智能体范式设计的综合理解和实践能力。

1. 本章介绍了三种经典的智能体范式:`ReAct`、`Plan-and-Solve` 和 `Reflection`。请分析:
   
   - 这三种范式在"思考"与"行动"的组织方式上有什么本质区别？
   - 如果要设计一个"智能家居控制助手"（需要控制灯光、空调、窗帘等多个设备，并根据用户习惯自动调节），你会选择哪种范式作为基础架构？为什么？
   - 是否可以将这三种范式进行组合使用？若可以，请尝试设计一个混合范式的智能体架构，并说明其适用场景。
2. 在4.2节的 `ReAct` 实现中，我们使用了正则表达式来解析大语言模型的输出（如 `Thought` 和 `Action`）。请思考:
   
   - 当前的解析方法存在哪些潜在的脆弱性？在什么情况下可能会失败？
   - 除了正则表达式，还有哪些更鲁棒的输出解析方案？
   - 尝试修改本章的代码，使用一种更可靠的输出格式，并对比两种方案的优缺点
3. 工具调用是现代智能体的核心能力之一。基于4.2.2节的 `ToolExecutor` 设计，请完成以下扩展实践:
   
   > <strong>提示</strong>:这是一道动手实践题，建议实际编写代码
   
   - 为 `ReAct` 智能体添加一个"计算器"工具，使其能够处理复杂的数学计算问题（如"计算 `(123 + 456) × 789/ 12 = ?` 的结果"）
   - 设计并实现一个"工具选择失败"的处理机制:当智能体多次调用错误的工具或提供错误的参数时，系统应该如何引导它纠正？
   - 思考:如果可调用工具的数量增加到$50$个甚至$100$个，当前的工具描述方式是否还能有效工作？在可调用工具数量随业务需求显著增加时，从工程角度如何优化工具的组织和检索机制？
4. `Plan-and-Solve` 范式将任务分解为"规划"和"执行"两个阶段。请深入分析:
   
   - 在4.3节的实现中，规划阶段生成的计划是"静态"的（一次性生成，不可修改）。如果在执行过程中发现某个步骤无法完成或结果不符合预期，应该如何设计一个"动态重规划"机制？
   - 对比 `Plan-and-Solve` 与 `ReAct`:在处理"预订一次从北京到上海的商务旅行（包括机票、酒店、租车）"这样的任务时，哪种范式更合适？为什么？
   - 尝试设计一个"分层规划"系统:先生成高层次的抽象计划，然后针对每个高层步骤再生成详细的子计划。这种设计有什么优势？
5. `Reflection` 机制通过"执行-反思-优化"循环来提升输出质量。请思考:
   
   - 在4.4节的代码生成案例中，不同阶段使用的是同一个模型。如果使用两个不同的模型（例如，用一个更强大的模型来做反思，用一个更快的模型来做执行），会带来什么影响？
   - `Reflection` 机制的终止条件是"反馈中包含<strong>无需改进</strong>"或"达到最大迭代次数"。这种设计是否合理？能否设计一个更智能的终止条件？
   - 假设你要搭建一个"学术论文写作助手"，它能够生成初稿并不断优化论文内容。请设计一个多维度的Reflection机制，从段落逻辑性、方法创新性、语言表达、引用规范等多个角度进行反思和改进。
6. 提示词工程是影响智能体最终效果的关键技术。本章展示了多个精心设计的提示词模板。请分析:
   
   - 对比4.2.3节的 `ReAct` 提示词和4.3.2节的 `Plan-and-Solve` 提示词，它们显然存在结构设计上的明显不同，这些差异是如何服务于各自范式的核心逻辑的？
   - 在4.4.3节的 `Reflection` 提示词中，我们使用了"你是一位极其严格的代码评审专家"这样的角色设定。尝试修改这个角色设定（如改为"你是一位注重代码可读性的开源项目维护者"），观察输出结果的变化，并总结角色设定对智能体行为的影响。
   - 在提示词中加入 `few-shot` 示例往往能显著提升模型对特定格式的遵循能力。请为本章的某个智能体尝试添加 `few-shot` 示例，并对比其效果。
7. 某电商初创公司现在希望使用"客服智能体"来代替真人客服实现降本增效，它需要具备以下功能:
   
   a. 理解用户的退款申请理由
   
   b. 查询用户的订单信息和物流状态
   
   c. 根据公司政策智能地判断是否应该批准退款
   
   d. 生成一封得体的回复邮件并发送至用户邮箱
   
   e. 如果判断决策存在一定争议（自我置信度低于阈值），能够进行自我反思并给出更审慎的建议
   
   此时作为该产品的负责人:
   
   - 你会选择本章的哪种范式（或哪些范式的组合）作为系统的核心架构？
   - 这个系统需要哪些工具？请列出至少3个工具及其功能描述。
   - 如何设计提示词来确保智能体的决策既符合公司利益，又能保持对用户的友好态度？
   - 这个产品上线后可能面临哪些风险和挑战？如何通过技术手段来降低这些风险？

## 我的思考

结合deepseek与gpt

## 习题1：三种范式怎么选

- 我觉得核心不是“推理链多漂亮”，而是**信息什么时候可得、环境会不会变**。
  - `ReAct`：信息边拿边做，适合“我要先试一下才知道”的场景。
  - `Plan-and-Solve`：先整体规划，再执行。
    - `Reflection`：不是做事的主流程，而是**把输出质量拉到能用**的机制。

### 1.3 混合范式架构设计

- 智能家居我会偏 `ReAct`：传感器数据随时变，计划写得再好也会被打断。
- 组合是必须的：我更愿意把它们看成三层——
  - 高层 `Plan`（今天大概怎么过）
  - 执行层 `ReAct`（遇到突发就即时调整）
  - 复盘层 `Reflection`（把“这次不舒服/太亮/太冷”变成规则或偏好）

```python
# 混合范式智能家居架构
class HybridHomeAgent:
    def __init__(self):
        self.planner = PlanAndSolveModule()      # 高层规划
        self.executor = ReActModule()           # 实时执行
        self.reflector = ReflectionModule()     # 长期优化
  
    def run(self):
        # 1. 高层规划（每天早上执行一次）
        daily_plan = self.planner.generate_daily_plan(
            user_schedule, weather_forecast
        )
      
        # 2. 实时执行（持续运行）
        while True:
            sensor_data = read_sensors()
          
            # ReAct循环处理实时事件
            if unexpected_event(sensor_data):
                thought, action = self.executor.react_cycle(sensor_data)
                execute_action(action)
          
            # 按计划执行常规任务
            elif time_for_scheduled_task():
                execute_scheduled_task(daily_plan)
          
            # 3. 周期性反思（每小时一次）
            if time_for_reflection():
                self.reflector.analyze_and_optimize(
                    energy_usage, user_feedback
                )
```

**适用场景**：

- **智慧办公楼**：固定工作时间表（规划）+ 实时占用调整（ReAct）+ 能效优化（反思）
- **养老监护**：日常护理计划（规划）+ 紧急情况响应（ReAct）+ 健康模式学习（反思）
- **酒店客房**：客人入住流程（规划）+ 个性化服务调整（ReAct）+ 满意度优化（反思）

## 习题2：正则解析 LLM 输出

- 正则最怕的不是模型乱写，而是**模型“写得更像人”**：多解释一句、少一个换行、标签换成中文，解析就碎。
- 真正的脆弱点：你以为在解析 `Action`，其实在解析“格式”。格式崩了，你的 agent 也就崩了。
- 我更认可的做法：强制结构化输出 + 校验（哪怕失败也能兜底）。
  - 最简单可落地：要求模型输出 JSON，然后用 schema 验证；失败就触发“请只输出 JSON，不要解释”。
  - 如果平台支持：直接用工具/函数调用接口，省掉一半脏活。
- 第四章给的“排错顺序”我很认同：
  - 先 `print` 最终拼好的完整提示词（包含 history），别凭空猜模型怎么想。
  - 解析失败就把原始输出整段打印出来，判断是“模型不守规矩”还是“解析写错”。
  - 模型频繁跑偏时，加一两个 `few-shot` 的 `Thought-Action-Observation` 成功例子，往往比改十次正则更有效。

### 2.2 更鲁棒的解析方案

```python
# 使用LangChain的OutputParser
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate

parser = PydanticOutputParser(pydantic_object=AgentResponse)

prompt = PromptTemplate(
    template="回答以下问题：{question}\n{format_instructions}",
    input_variables=["question"],
    partial_variables={
        "format_instructions": parser.get_format_instructions()
    }
)
```

### 2.3 代码修改与对比

```python
# 修改前的正则解析版本
class RegexParser:
    def parse(self, text):
        thought_pattern = r'Thought:\s*(.*?)(?:\nAction:|\nFinal Answer:|$)'
        action_pattern = r'Action:\s*(\w+)'
        action_input_pattern = r'Action Input:\s*(.*?)(?:\nThought:|\nFinal Answer:|$)'
      
        # 多个正则匹配，容易出错
        thought = re.search(thought_pattern, text, re.DOTALL)
        action = re.search(action_pattern, text)
      
        return {
            "thought": thought.group(1) if thought else "",
            "action": action.group(1) if action else None
        }

# 修改后的结构化解析版本
class StructuredParser:
    def __init__(self):
        self.schema = {
            "type": "object",
            "properties": {
                "thought": {"type": "string"},
                "action": {"type": "string", "enum": ["search", "calculate", "query"]},
                "action_input": {"type": "object"},
                "final_answer": {"type": "string"}
            },
            "required": ["thought"]
        }
  
    def parse(self, text):
        # 要求模型输出JSON
        prompt = f"输出JSON格式：{json.dumps(self.schema, ensure_ascii=False)}\n\n{text}"
      
        try:
            # 尝试解析JSON
            result = json.loads(self.extract_json(text))
            return self.validate_schema(result)
        except json.JSONDecodeError:
            # 失败时回退到正则
            return self.fallback_parse(text)
  
    def extract_json(self, text):
        """从可能包含其他文本的内容中提取JSON"""
        # 查找第一个 { 和最后一个 }
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return text[start:end]
        return text
```

**方案对比**：

| 方案           | 优点                     | 缺点                        | 适用场景               |
| -------------- | ------------------------ | --------------------------- | ---------------------- |
| **正则表达式** | 简单、快速、无额外依赖   | 脆弱、难维护、扩展性差      | 原型验证、格式严格可控 |
| **结构化输出** | 鲁棒、类型安全、易扩展   | 需要模型配合、可能增加token | 生产环境、复杂输出     |
| **函数调用**   | 原生支持、最可靠、标准化 | 平台依赖、灵活性受限        | 商用API、工具调用场景  |

## 习题3：工具调用扩展——难点不在“加工具”，在“失败后怎么自救”

- 计算器工具我会做得很克制：只做一件事。
  - 接口：`calculate(expression: string) -> number`
  - 约束：`expression` 只允许算术表达式；输出只返回数值（别夹解释）。
- “工具选择失败”我会盯两件事：
  - 失败是因为**选错工具**，还是因为**参数不合法**？这两种提示策略完全不同。
  - 失败次数不是为了惩罚模型，而是为了触发**更强的约束提示**。
    - 例如：维护 `fail_count`；超过阈值直接要求模型输出 `tool_name`、`args` 的 JSON，并给一个最小可用示例。
- 我从第四章学到一个很“工程”的点：工具最关键的不是函数本身，而是 `description`（模型靠它做选择）。描述写泛了，就等于随机选工具。
- 工具爆炸（50~100 个）时，我的经验是：**别把所有工具一股脑塞进提示词**。
  - `vector_recall`：根据任务描述召回 Top-K 工具（先缩小范围）。
  - `hierarchy(domain -> subdomain -> tool)`：让“组织结构”替你减少搜索成本。
  - `metadata_filter(input_schema/cost/permission)`：先过滤掉“不能用/不该用”的工具。
  - 提示词只暴露 `candidate_tools`：让模型在 5~8 个候选里选，而不是在 100 个里瞎猜。

## 习题4：Plan-and-Solve 需要“能重规划”

- 设定重规划触发条件：
  - `step_failed`（工具报错/无结果）
  - `constraint_changed`（价格变了/无库存/时间冲突）
  - `confidence_low`（模型自己都不确定）
- 旅行预订这种强依赖任务：我倾向 `Plan-and-Solve` 做“全局一致性”，再用 `ReAct` 处理突发（航班取消、酒店满房）。
- 分层规划的最大价值：**你可以只改一层**。
  - 高层目标不变（到上海开会），只在子层换方案（航班→高铁）。

### 4.1 动态重规划机制

```python
class DynamicReplanningAgent:
    def __init__(self):
        self.original_plan = []
        self.execution_history = []
      
    def execute_with_replanning(self, task):
        """带动态重规划的执行"""
        # 1. 初始规划
        plan = self.planning_phase(task)
      
        step_index = 0
        while step_index < len(plan):
            current_step = plan[step_index]
          
            # 2. 执行当前步骤
            result = self.execution_phase(current_step)
            self.execution_history.append((current_step, result))
          
            # 3. 检查执行结果
            if self.needs_replanning(result, current_step):
                # 4. 触发重规划
                remaining_task = self.reconstruct_remaining_task(
                    plan[step_index:], result
                )
              
                new_plan = self.replanning_phase(
                    remaining_task, 
                    self.execution_history
                )
              
                # 5. 替换后续计划
                plan = plan[:step_index] + new_plan
                print(f"步骤{step_index}后重规划，新计划：{new_plan}")
          
            step_index += 1
      
        return self.execution_history
  
    def needs_replanning(self, result, step):
        """判断是否需要重规划"""
        checkpoints = [
            result.get("status") == "failed",          # 步骤失败
            result.get("confidence", 0) < 0.5,         # 置信度低
            self.unexpected_output(result, step),      # 意外输出
            self.external_change_detected(),           # 环境变化
            self.timeout_exceeded(step)                # 超时
        ]
        return any(checkpoints)
  
    def replanning_phase(self, remaining_task, history):
        """基于历史的重规划"""
        prompt = f"""
        原始任务剩余部分：{remaining_task}
        执行历史：{history}
      
        由于步骤'{history[-1][0]}'执行{history[-1][1]['status']}，
        请重新规划剩余步骤，考虑：
        1. 跳过失败步骤的替代方案
        2. 调整步骤顺序
        3. 分解复杂步骤
      
        输出新的步骤列表：
        """
      
        # 调用LLM生成新计划
        new_plan = self.llm_generate_plan(prompt)
        return self.validate_plan(new_plan)
  
    def reconstruct_remaining_task(self, remaining_steps, last_result):
        """基于最后结果重建剩余任务描述"""
        # 如果步骤失败，可能需要修改任务描述
        if last_result.get("status") == "failed":
            return f"原任务受阻于'{remaining_steps[0]}'，需要绕行方案"
        return f"继续完成：{' -> '.join(remaining_steps)}"
```

### 4.2 预订旅行任务范式对比

```python
# Plan-and-Solve方案（更适合）
class TravelPlanner:
    def plan_trip(self, from_city, to_city, requirements):
        """一次性生成完整旅行计划"""
        plan = [
            "1. 查询北京到上海的航班，筛选商务舱",
            "2. 根据航班时间选择浦东机场附近的五星级酒店",
            "3. 预订酒店接送或租车服务",
            "4. 协调航班、酒店、租车的时间衔接",
            "5. 生成完整行程单和预订确认"
        ]
      
        # 批量执行所有步骤
        results = []
        for step in plan:
            result = self.execute_step(step)
            if result["status"] == "failed":
                # 需要协调重试
                self.adjust_dependent_steps(plan, step_index)
            results.append(result)
      
        return self.compile_itinerary(results)

# ReAct方案对比
class ReactiveTravelAgent:
    def book_trip(self, from_city, to_city):
        """交替决策可能低效"""
        steps = []
      
        # 可能出现的低效循环
        thought1 = "先查航班"
        action1 = search_flights("北京", "上海", "business")
        # 发现没有合适航班
        # 重新思考...
        thought2 = "也许可以中转"
        action2 = search_flights("北京", "南京", "business")
        # 又需要重新考虑酒店...
```

**范式选择分析**：

- **Plan-and-Solve优势**：
  
  - 预订任务**步骤间强依赖**（酒店依赖航班时间）
  - 需要**全局协调优化**（避免时间冲突）
  - 可以**批量获取信息**（比多次API调用高效）
- **ReAct适用场景**：
  
  - 用户需求**模糊或变化**（"我想去个暖和的地方"）
  - 需要**实时探索选项**（比较多个目的地）
  - 环境**高度不确定**（航班突然取消）

### 4.3 分层规划系统设计

```python
class HierarchicalPlanner:
    def __init__(self):
        self.abstract_levels = 3  # 抽象层级数
      
    def hierarchical_plan(self, task):
        """分层规划主流程"""
        # 第一层：抽象战略规划
        strategic_plan = self.strategic_planning(task)
      
        detailed_plan = []
        for abstract_step in strategic_plan:
            # 第二层：战术分解
            tactical_steps = self.tactical_decomposition(abstract_step)
          
            for tactical_step in tactical_steps:
                # 第三层：操作级详细步骤
                operational_steps = self.operational_planning(tactical_step)
                detailed_plan.extend(operational_steps)
      
        return {
            "strategic": strategic_plan,
            "tactical": self.group_by_tactical(detailed_plan),
            "operational": detailed_plan
        }
  
    def strategic_planning(self, task):
        """高层抽象规划（做什么）"""
        prompt = f"""
        将任务分解为3-5个高层目标：
        任务：{task}
      
        高层目标（抽象，不涉及具体操作）：
        1. 
        2. 
        3. 
        """
        return ["解决交通", "安排住宿", "准备地面交通", "协调时间"]
  
    def tactical_decomposition(self, abstract_step):
        """中层战术分解（怎么做）"""
        decompositions = {
            "解决交通": [
                "选择交通方式（飞机/高铁）",
                "查询班次和时间",
                "比较价格和服务"
            ],
            "安排住宿": [
                "确定酒店标准和位置",
                "查询空房和价格",
                "查看评价和设施"
            ]
        }
        return decompositions.get(abstract_step, [abstract_step])
  
    def operational_planning(self, tactical_step):
        """操作级详细步骤（具体执行）"""
        steps = {
            "查询班次和时间": [
                "访问航空公司官网API",
                "设置查询参数：日期、舱位",
                "解析返回的航班列表",
                "筛选符合时间的选项"
            ],
            "比较价格和服务": [
                "收集各渠道价格",
                "比较退改签政策",
                "评估累积里程",
                "选择最优选项"
            ]
        }
        return steps.get(tactical_step, [tactical_step])
```

**分层规划优势**：

1. **复杂度管理**：将复杂任务分解为可管理的层级
2. **重用性**：高层计划可复用于类似任务
3. **灵活性**：可在不同层级进行调整
4. **可解释性**：清晰的规划结构便于调试
5. **并行处理**：不同层级可独立优化

## 习题5：Reflection——我更关心“反思能不能落到修改动作”

- 第四章把 Reflection 定义成 `post-hoc` 的“执行 -> 反思 -> 优化”循环，我很赞同：先接受“初稿必烂”，关键是迭代回路是否稳定。
- 1、双模型（强反思 + 快执行）我觉得是合理的工程折中：强模型出“返工单”，快模型按单改；为避免反复横跳，我会把反思输出固定成 checklist。
- 2、我觉得 Reflection 真正的隐藏成本是“上下文太长”：第四章也提到需要一个临时“短期记忆”模块，把每轮的关键信息/改动记录下来，而不是把全文都塞给评审员。
- 3、终止条件我不喜欢只靠“无需改进”这句话：
  - 更像工程的做法是：`diminishing_returns`（连续两轮改动很小） + `budget_limit`（成本/时间上限） + `validator_passed`（规则/测试通过）。

### （补充）学术论文写作助手：我会怎么做“多维反思”

- 我会按“写作流程”拆产物：`problem_statement` → `evidence_pool` → `related_work_outline` → `research_question` → `feasibility_notes` → `outline` → `milestones` → `draft`。
- 每轮反思不直接“点评全文”，而是让不同评审器盯不同目标，并统一输出格式（方便落地改稿）：
  - 逻辑性 critic：输出 `issues[]`（定位到段落）+ `rewrite_instruction` + `acceptance_check`。
  - 创新性 critic：逼自己说清 `novelty_claim`、`baseline`、`why_better`（不清楚就等于没创新）。
  - 语言表达 critic：术语一致、主谓清楚、删掉“看起来学术但没信息量”的句子。
  - 引用规范 critic：关键断言必须有证据；格式统一；“该引未引”要列清单。
- 我会把“段落逻辑性”写成可验收的 4 条（改完能自测）：`topic_sentence`、`linking`、`one_point_per_paragraph`、`alignment_to_title`。

### 5.1 多模型策略的影响

```python
class MultiModelReflection:
    def __init__(self, fast_model, strong_model):
        self.fast_model = fast_model  # 用于执行
        self.strong_model = strong_model  # 用于反思
      
    def reflect_and_improve(self, initial_output, task):
        """使用强模型反思，快模型执行"""
        # 第一轮：快速生成初稿
        draft = self.fast_model.generate(task)
      
        iterations = 0
        current_best = draft
      
        while iterations < self.max_iterations:
            # 使用强模型进行深度反思
            critique = self.strong_model.reflect(current_best, task)
          
            if self.is_sufficient(critique):
                break
              
            # 生成改进指导
            guidance = self.extract_guidance(critique)
          
            # 使用快模型执行改进
            improved = self.fast_model.improve(
                current_best, 
                guidance
            )
          
            # 质量评估
            if self.is_improvement(improved, current_best):
                current_best = improved
              
            iterations += 1
      
        return current_best
  
    def cost_benefit_analysis(self):
        """成本效益分析"""
        # 假设模型调用成本
        fast_model_cost = 0.01  # 美元/次
        strong_model_cost = 0.10  # 美元/次
      
        scenarios = [
            {
                "strategy": "仅强模型",
                "iterations": 3,
                "total_cost": 3 * strong_model_cost,
                "expected_quality": 0.95
            },
            {
                "strategy": "混合模型",
                "fast_calls": 5,
                "strong_calls": 2,
                "total_cost": (5 * fast_model_cost + 2 * strong_model_cost),
                "expected_quality": 0.90
            }
        ]
      
        return scenarios
```

**影响分析**：

- **优势**：
  
  - **成本优化**：强模型用于关键反思，快模型处理常规执行
  - **质量提升**：强模型的深度反思能力带来更好改进
  - **并行可能**：可以同时使用多个专业模型反思不同方面
- **挑战**：
  
  - **一致性**：不同模型可能有不同"风格"
  - **协调开销**：需要在模型间传递和转换信息
  - **错误传播**：反思模型的错误会误导执行模型

### 5.2 智能终止条件设计

```python
class IntelligentTermination:
    def __init__(self):
        self.metrics_history = []
      
    def should_terminate(self, current_output, previous_output, 
                        iteration, feedback):
        """智能终止条件判断"""
        conditions = []
      
        # 1. 质量收敛检测
        if self.has_converged():
            conditions.append(("质量收敛", True))
      
        # 2. 改进幅度阈值
        improvement = self.calculate_improvement(
            current_output, previous_output
        )
        if improvement < self.min_improvement_threshold:
            conditions.append(("改进不足", True))
      
        # 3. 检测振荡/循环
        if self.detected_oscillation():
            conditions.append(("检测到振荡", True))
      
        # 4. 外部验证通过
        if self.external_validation_passed(current_output):
            conditions.append(("外部验证通过", True))
      
        # 5. 时间/成本限制
        if iteration >= self.max_iterations:
            conditions.append(("达到最大迭代", True))
        if self.exceeded_time_budget():
            conditions.append(("超时", True))
      
        # 加权决策
        termination_score = self.calculate_termination_score(conditions)
        return termination_score > self.termination_threshold
  
    def calculate_improvement(self, current, previous):
        """计算改进幅度"""
        # 使用多个维度评分
        metrics = {
            "correctness": self.evaluate_correctness(current, previous),
            "completeness": self.evaluate_completeness(current, previous),
            "clarity": self.evaluate_clarity(current, previous),
            "conciseness": self.evaluate_conciseness(current, previous)
        }
      
        # 加权平均
        weights = {"correctness": 0.4, "completeness": 0.3, 
                  "clarity": 0.2, "conciseness": 0.1}
        total_improvement = sum(
            metrics[m] * weights[m] for m in metrics
        )
      
        self.metrics_history.append(total_improvement)
        return total_improvement
  
    def has_converged(self):
        """检测是否收敛"""
        if len(self.metrics_history) < 3:
            return False
      
        # 最近3次改进幅度都很小
        recent = self.metrics_history[-3:]
        avg_improvement = sum(recent) / len(recent)
        return avg_improvement < self.convergence_threshold
  
    def detected_oscillation(self):
        """检测振荡模式"""
        if len(self.metrics_history) < 4:
            return False
      
        # 检查是否在几个状态间来回切换
        pattern = self.metrics_history[-4:]
        differences = [pattern[i+1] - pattern[i] for i in range(3)]
      
        # 符号交替变化表明振荡
        signs = [1 if d > 0 else -1 for d in differences]
        oscillation_score = abs(sum(signs))  # 全同号=3，交替=1
      
        return oscillation_score <= 1
```

### 5.3 学术论文写作助手的多维度Reflection

```python
class AcademicPaperReflector:
    def __init__(self):
        self.critics = {
            "logic": LogicCritic(),
            "innovation": InnovationCritic(),
            "language": LanguageCritic(),
            "citation": CitationCritic(),
            "structure": StructureCritic()
        }
      
    def multidimensional_reflection(self, paper_draft):
        """多维度反思与改进"""
        # 并行收集各维度反馈
        all_feedback = {}
        for dimension, critic in self.critics.items():
            feedback = critic.analyze(paper_draft)
            all_feedback[dimension] = feedback
      
        # 优先级排序
        prioritized = self.prioritize_feedback(all_feedback)
      
        improvements = []
        for dimension, feedback in prioritized:
            # 生成具体修改建议
            suggestions = self.generate_suggestions(dimension, feedback)
          
            # 应用改进
            if self.should_apply_now(suggestions, dimension):
                improved_draft = self.apply_improvements(
                    paper_draft, suggestions
                )
                improvements.append((dimension, improved_draft))
      
        # 冲突解决
        if self.has_conflicts(improvements):
            final_draft = self.resolve_conflicts(improvements)
        else:
            final_draft = self.merge_improvements(improvements)
      
        return {
            "final_draft": final_draft,
            "feedback_by_dimension": all_feedback,
            "applied_improvements": improvements
        }
  
    def prioritize_feedback(self, feedback_dict):
        """基于严重性和影响排序"""
        priority_scores = {}
      
        for dimension, feedback in feedback_dict.items():
            score = 0
          
            # 严重性权重
            severity_weights = {
                "critical": 3.0,
                "major": 2.0,
                "minor": 1.0
            }
          
            for issue in feedback.get("issues", []):
                severity = issue.get("severity", "minor")
                score += severity_weights.get(severity, 1.0)
          
            # 维度重要性权重
            dimension_weights = {
                "logic": 1.5,      # 逻辑性最重要
                "citation": 1.2,   # 引用规范很关键
                "innovation": 1.0,
                "structure": 0.9,
                "language": 0.8
            }
          
            score *= dimension_weights.get(dimension, 1.0)
            priority_scores[dimension] = score
      
        # 按优先级排序
        return sorted(
            feedback_dict.items(), 
            key=lambda x: priority_scores.get(x[0], 0), 
            reverse=True
        )

class LogicCritic:
    """逻辑性评审专家"""
    def analyze(self, paper):
        issues = []
      
        # 检查论点一致性
        if not self.check_argument_consistency(paper):
            issues.append({
                "type": "argument_inconsistency",
                "severity": "critical",
                "description": "文中存在矛盾论点",
                "location": self.find_inconsistent_sections(paper)
            })
      
        # 检查推理链条
        if not self.check_reasoning_chain(paper):
            issues.append({
                "type": "broken_reasoning_chain",
                "severity": "major",
                "description": "推理步骤不连贯",
                "suggestion": "添加过渡句或明确逻辑连接"
            })
      
        return {"issues": issues, "score": self.calculate_logic_score(paper)}

class CitationCritic:
    """引用规范评审专家"""
    def analyze(self, paper):
        issues = []
      
        # 检查格式一致性
        formats = self.extract_citation_formats(paper)
        if len(set(formats)) > 1:
            issues.append({
                "type": "citation_format_inconsistency",
                "severity": "major",
                "description": f"发现{len(set(formats))}种引用格式",
                "suggestion": "统一为{recommended_format}格式"
            })
      
        # 检查是否引用关键文献
        missing_key = self.check_key_citations(paper)
        if missing_key:
            issues.append({
                "type": "missing_key_citations",
                "severity": "critical",
                "description": f"缺失{len(missing_key)}篇关键文献",
                "suggested_citations": missing_key
            })
      
        return {"issues": issues, "score": self.calculate_citation_score(paper)}
```

## 习题6：提示词工程——我关注的是“约束行为”，不是“写得像论文”

- `ReAct` 提示词最关键的是：把输出拆成可执行的槽位（tool name / args / observation），减少模型自由发挥。
- `Plan-and-Solve` 的提示词我会强调：先给出高层步骤，再给每步的“完成判定条件”，否则计划很容易写成空话。
- 角色设定对我来说是“拉偏好”的旋钮：
  - “严格评审”会更愿意否定、找错；
  - “开源维护者”更看重可读性和可维护性（命名、结构、注释）。
- `few-shot` 的收益点很实际：不是让模型更聪明，而是让它**更守规矩**。

## 习题7：客服智能体——我最在意“可审计的决策链路”

- 这类系统最怕的不是答得慢，而是**乱批/乱拒**还说不清原因。
- 我会用 `ReAct + Reflection`：
  - `ReAct` 做查询与动作（查订单、查物流、查政策、发邮件）。
  - `Reflection` 只在低置信度或高风险场景触发（比如金额大、超政策边界、用户投诉关键词）。
- 工具我会至少拆成三块：`order_lookup`、`policy_eval`、`send_email`，并且让 `policy_eval` 输出结构化理由（方便审计）。
- 风险控制我更偏工程手段：权限边界、日志、规则引擎兜底、人工复核入口，而不是“写更长的提示词”。

