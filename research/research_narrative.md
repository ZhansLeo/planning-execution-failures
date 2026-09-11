# Diagnosing Planning–Execution Failures in Tool-Augmented LLM Agents

## Evidence from TravelPlanner and ChinaTravel

## 1. Research Problem

现实中的旅行规划不是一次文本生成任务。Agent 必须理解用户需求，识别需要补充的信息，调用环境工具，维护多轮 observation，将证据绑定到具体计划字段，并保证多天行程在路线、时间、预算、住宿、餐饮和偏好上整体可行。

这些环节形成一条相互依赖的 planning–execution chain：

```text
User requirement
→ Constraint representation
→ Information acquisition
→ Agent control and stopping
→ Plan-guided execution
→ Evidence utilization
→ Output contract
→ Global constraint satisfaction
```

其中任何一层失败都会使最终计划不可用。仅报告最终成功率无法区分：模型没理解、Planner 漏项、Executor 没搜索、搜索后没使用、输出 schema 错误，还是全局约束真正失败。

本项目因此不把目标设定为“构建更强的 Travel Agent”，而是研究：**工具增强 LLM Agent 的长程、多约束规划失败究竟发生在哪一层，常见的 Planner、Verifier 和 Replan 机制实际改变了什么。**

## 2. Why Travel Planning Is a Useful Testbed

旅行规划同时具备研究 Agent Planning 所需的几个性质：

- **long horizon：** 多日、多城市和跨城交通构成相互依赖的决策链；
- **partial information：** 航班、住宿、餐厅和景点信息需要主动查询；
- **mixed constraints：** 既有预算、时间和房型等明确硬约束，也有菜系、景点类型和便利性等偏好；
- **grounded execution：** 计划中的实体和数值应来自固定环境，而不是模型参数知识；
- **verifiable outcome：** sandbox、schema 和逻辑规则允许区分可行与不可行计划。

TravelPlanner 提供标准化的现实约束、六个工具和大规模离线 sandbox，并明确区分 sole-planning 与 two-stage planning [@xie2024travelplanner]。ChinaTravel 进一步引入开放中文需求、组合约束 DSL、偏好和更复杂的活动级输出格式 [@shao2026chinatravel]。两者结合，允许先进行较深的机制研究，再进行小规模跨 benchmark 检查。

## 3. Benchmark and Method Evolution

LLM Planning 的研究问题已经从“模型能否生成动作序列”逐渐扩展为“Agent 能否在不完全信息、工具交互和全局约束下可靠执行”。2024 年的 planning survey 将方法概括为 task decomposition、plan selection、external modules、reflection/refinement 和 memory [@huang2024understanding]；2025 年的系统综述进一步从 external-module、finetuning 和 search 角度组织方法，并区分 open-loop 与 closed-loop planning [@cao2025planning]。

ReAct 将 reasoning、action 和 observation 交替，使模型能够根据环境反馈更新决策 [@yao2023react]。Planner–Executor 架构则尝试将高层任务分解与低层行动分开；Plan-and-Act 同时指出，静态计划面对未知观察和执行失败时可能变得过时，因此提出逐步更新计划 [@erdogan2025planact]。

另一条路线不要求 LLM 独立保证正确性。LLM+P 将自然语言转成 PDDL，再由经典 Planner 搜索 [@liu2023llmp]；LLM-Modulo 主张把 LLM 与外部 model-based verifier 进行更紧密的双向结合 [@kambhampati2024llmmodulo]。PDDLEGO 则在部分可观察环境中随着新信息迭代形式规划表示 [@zhang2024pddlego]。

近期 benchmark 也越来越强调主动信息获取、隐式环境约束、全局一致性和 backtracking。DeepPlanning 将能力拆成 proactive information acquisition、local constrained reasoning 和 global constrained optimization [@zhang2026deepplanning]；层次化 web-agent 研究进一步把高层规划、低层执行和重规划分开诊断，并发现结构化高层计划并不自动消除执行瓶颈 [@aghzal2026hierarchical]。

这些工作共同说明，方法不应按“模块越来越多”线性排列，而应按 **Failure → Mechanism** 理解。

## 4. Research Questions

### Experimental RQ1 — Planning with supplied evidence

当 query 对应的完整 reference information 已提供时，模型自身能否组合证据并满足多日全局约束？

对应 TravelPlanner A。该条件移除信息获取责任，但仍保留计划组合、格式和约束满足。

### Experimental RQ2 — Autonomous acquisition and control

当 Agent 必须从 query 出发自主使用工具时，失败和成本如何变化？

对应 TravelPlanner A→B。该比较是 information-condition/system gap，不是工具单变量因果实验。

### Experimental RQ3 — Explicit Planner

在相同 query-only 工具条件下，一次显式 Planner 能否减少失控、提高 Delivery、降低成本并改善最终正确性？

对应 TravelPlanner B→C，以及 ChinaTravel CT-B→CT-C 的小规模泛化检查。

### Experimental RQ4 — Post-hoc verification and repair

在 Planner+ReAct 已产生候选后，一次显式 Verifier 和一次 no-tool Replan 能否修复格式、证据和约束错误？

对应 TravelPlanner C→D。

## 5. TravelPlanner Controlled Study

### A — Supplied-evidence sole-planning

Stage A 向模型提供 query 和完整官方 reference information，只调用一次规划模型，不使用工具或修复模型。A 在 180 条 validation 上的 Delivery 为 171/180（95%），但 Final Pass 只有 25/180（13.89%）。

这说明信息完整并不等于计划正确。A 的主失败集中在预算、minimum nights、route/transportation 和多样性等已交付计划内部的约束。模型能够高概率输出 itinerary，却不能稳定维护全局一致性。

### B — Query-only ReAct with tools

Stage B 移除 oracle-aligned reference，让 Agent 自主使用六个官方工具。Delivery 降至 63/180（35%），平均成本从 10,894 增至 57,642 tokens/query，平均工具调用达到 19.43。

Final Pass 从 25 增到 28，但这个小变化不能掩盖 failure regime 的改变：B 有 117/180 个主失败位于 delivery/agent-control。大量样本在形成候选之前已经耗尽步骤、重复调用或无法结束。

因此 A→B 的核心发现不是“工具使分数下降”，而是：**自主信息获取把 planning problem 扩展为 acquisition、control、state maintenance 和 stopping problem。**

### C — Explicit Planner + ReAct

Stage C 在 B 的信息条件、工具、30-call budget、完整 observation、模型和 evaluator 上增加一次前置 Planner。

相对 B：

- Delivery：35%→40%（+5 pp）；
- Final Pass：15.56%→16.11%（+0.56 pp，即净增 1 条）；
- tokens/query：−2.89%；
- tool calls/query：−8.24%；
- latency/query：+0.83 秒。

Planner 对部分控制和检索组织有帮助，但没有稳定改变 end-to-end correctness。C 仍有 108 个 delivery/agent-control 主失败，且 5/7 天长程任务没有得到决定性改善。

案例进一步显示，合法且完成 checklist 的 Blueprint 仍可能生成重复餐厅或无效 sandbox 实体。因此：

> **Plan quality and plan execution are separate capabilities.**

### D — Verifier + Single Replan

Stage D 独立重跑完整 C 链路，对有 final response 的 candidate 调用一次 Verifier，并在 `repair` 时进行一次无工具 Replan。

漏斗为：

```text
180 runs
→ 119 candidates
→ 119 verifier calls
→ 46 replans
→ 16 schema-valid replans
→ 4 post-hoc repair successes
```

D 的 Delivery 为 75/180，Final Pass 仍为 29/180，与 C 完全相同；总成本增加 1,263,248 tokens，平均延迟增加 4.85 秒。C→D 同时出现 17 个 fail→pass 和 17 个 pass→fail。

更重要的是，61 个没有 candidate 的上游失败无法进入 Verifier。TP-D #4 还显示一个原本 Final Pass 的 candidate 在 Replan 后被改成餐厅重复的失败计划。

因此项目只得出受限结论：**该单次 post-hoc LLM verification/repair protocol 没有产生净 Final Pass，并且对许多上游失败介入过晚。**

## 6. ChinaTravel Generalization Check

ChinaTravel 不是第二套完整 A/B/C/D，而是 TravelPlanner 结论的小规模泛化检查。实验选择 easy、medium、human 各 4 条，共 12 条 paired queries：

- CT-B：Query-only ReAct + 官方 ChinaTravel tools；
- CT-C：在完全相同 Executor 前增加一次 Structured Planner。

### 四层结果

| Layer | CT-B | CT-C |
|---|---:|---:|
| Final response | 4/12 | 7/12 |
| Strict schema delivery | 4/12 | 4/12 |
| Schema delivery with any observation | 4/12 | 2/12 |
| Fully entity-grounded plan | 2/12 | 1/12 |
| Schema∩Environment | 0/12 | 0/12 |
| Schema∩Logical | 0/12 | 0/12 |
| All Pass | 0/12 | 0/12 |

CT-C 增加了模型停止并输出 final 的倾向，却没有增加合法交付。两个新增 schema-valid final 完全没有工具 observation。

### Entity-level grounding

CT-B 的 71 个主活动实体全部在 observation 中出现，其中 69 个字段一致、2 个字段不一致。CT-C 的 123 个主活动分解为：

- 70 retrieved and consistent；
- 18 retrieved but inconsistent；
- 11 sandbox-valid but unretrieved；
- 20 generic placeholders；
- 4 fabricated/invalid。

这说明“信息获取失败”不是单一类型：没搜、搜到没用、字段错绑、placeholder 和直接虚构需要分别诊断。

### Apparent efficiency

总体上 CT-C tokens −14.24%、tools −18.34%、latency −6.91%。但排除两个 zero-tool false stop 后：

- tokens +2.92%；
- tools −1.38%；
- latency +11.75%。

因此更准确的结论是：

> **Structured Planner changed stopping behavior, but did not demonstrate a general improvement in information-acquisition efficiency.**

## 7. Unified Failure Analysis

跨 benchmark taxonomy 将失败定位为八层：

1. Natural-language understanding；
2. Constraint representation；
3. Information acquisition；
4. Agent control and stopping；
5. Planner–Executor adherence；
6. Evidence utilization and grounding；
7. Output contract；
8. Global constraint satisfaction。

TravelPlanner A 主要显示 L6/L8：信息已经提供，但计划仍会混用实体或违反全局约束。B/C/D 的主瓶颈前移到 L3/L4：Agent 经常在形成 candidate 前失败。ChinaTravel 又使 L1/L2/L7 更清晰：开放中文需求需要 hard/soft 表示，Planner 可能注入实体，复杂 activity schema 可能抵消新增 final。

这个分析也改变了机制解释：

- 更多 final response 不等于更高 Delivery；
- 更少工具调用不等于更高检索效率；
- schema-valid Blueprint 不等于语义正确；
- evidence retrieved 不等于 evidence used；
- schema-valid Replan 不等于 constraint-improving repair。

## 8. Main Claims

### Claim 1

**Tool-mediated planning introduces substantial information-acquisition and agent-control failures beyond plan generation.**

### Claim 2

**Explicit planning changes control behavior more consistently than end-to-end correctness.**

### Claim 3

**A valid planning blueprint does not guarantee grounded or faithful execution.**

### Claim 4

**Under the tested protocol, post-hoc LLM verification was too late and too brittle to reliably recover many upstream failures.**

这些是本项目的 evidence-bounded claims，不是对所有 Planner、ReAct 或 Verifier 架构的普遍判断。

## 9. Contributions

本项目的贡献不是新的 SOTA 系统，而是一个完整的小型研究链路：

1. **Controlled mechanism study**：区分 supplied-evidence planning、自主信息获取、Explicit Planner 和 post-hoc repair。
2. **Failure-oriented diagnosis**：同时分析 non-delivery、约束、Agent control、cost 和 paired transitions，而不是只报总分。
3. **Entity/field-level grounding audit**：区分没检索、检索未用、字段误用、placeholder 和 invalid/fabricated entity。
4. **Cross-benchmark evidence**：用 ChinaTravel 小规模检查 TravelPlanner 的 Planner/control 结论在开放中文需求下是否仍可观察。
5. **Mechanism-driven research questions**：从观测 failure 推导 structured state、deterministic checking 和 execution-time repair，而不是继续堆叠模块。

## 10. Limitations

- A→B 是系统条件差距，不是工具因果消融。
- TP C/D 有服务端非确定性；D 又独立重跑上游。
- validation #1 曾用于格式开发。
- CT 只有 12 条，不能估计总体 benchmark 性能或稳定 split 差异。
- TP/CT 的 schema、evaluator、任务分布与服务端模型时间版本不同。
- Grounding audit 对部分市内交通只能保守标为 `not_retrieved_or_fabricated`。
- 本项目只测试一次静态 Planner 和一次 post-hoc LLM repair，不能代表其他实现。

完整限制及推荐表述见 [`validity_boundaries.md`](validity_boundaries.md)。

## 11. Open Research Questions

### RQ1 — Evidence sufficiency

如何显式表示检索目标、当前证据覆盖和剩余不确定性，使 Agent 能判断何时应继续搜索、修正查询或安全停止？

### RQ2 — Executable planning commitments

如何让 Blueprint 包含依赖、完成条件和可监控状态，使 Executor 偏离时能够被即时检测，而不是把计划仅作为一段额外 prompt？

### RQ3 — Constraint–Evidence–Plan binding

能否维护一个结构化 ledger，将每条用户约束连接到 evidence rows、计划字段和当前验证状态，并在每次工具调用或字段更新后增量检查？

### RQ4 — Hybrid verification

预算、时间、schema、实体存在性和交通衔接等确定性约束应由程序/solver 验证；自然语言偏好和开放语义仍由模型处理。二者应如何划分并协作？

### RQ5 — Targeted execution-time repair

能否在首次 invariant violation 时只重新检索或修改受影响字段，保留已经验证正确的部分，而不是等完整计划失败后整体重写？

## 12. Closing Perspective

TravelPlanner 与 ChinaTravel 共同支持的不是“Planner 无用”或“Verifier 无用”，而是一个更精确的判断：

> **Reliable agent planning requires more than producing a plan. It requires an explicit and verifiable link between constraints, acquired evidence, execution state, and final plan fields.**

这将研究重点从增加更多生成式组件，转向构建可观测、可验证、可在执行中修复的 planning state。
