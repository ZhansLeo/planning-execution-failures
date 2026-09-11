# Challenge → Evidence → Research Question

## 目的与证据原则

这不是一份覆盖所有 Agent Planning 论文的 survey，而是把正式文献与本项目的冻结实验连接起来，回答：现有机制试图解决什么、失败实际发生在哪里、下一步研究问题为什么成立。

- Literature evidence 来自 [`literature_evidence.json`](literature_evidence.json) 和 [`references.bib`](../references/references.bib)。
- TP evidence 来自 TravelPlanner 冻结的 4×180 条实验。
- CT evidence 来自 ChinaTravel 12 条 paired pilot，只提供小规模机制对照。
- “Remaining gap”是基于两者的研究推断，不冒充原论文结论。

## 总矩阵

| Challenge | Literature evidence | TravelPlanner evidence | ChinaTravel evidence | Unresolved gap | Open RQ |
|---|---|---|---|---|---|
| Information sufficiency and stopping | ReAct 说明 observation 可反馈到行动；TravelPlanner 和 DeepPlanning 均报告信息收集不完整、遗漏必要工具调用及长程退化 [@yao2023react; @xie2024travelplanner; @zhang2026deepplanning] | A→B 后 Delivery 95%→35%，B 有 117/180 个 delivery/agent-control 主失败，平均 19.43 次工具调用 | CT-B 8/12 没有 final；CT-C 虽将 final response 提高到 7/12，却产生 2 个 zero-tool false stop | 调用次数少既可能是效率，也可能是证据不足；现有 Planner 没有可验证的“证据充分”状态 | **RQ1：Agent 如何判断已经获得足够证据，并区分合理停止与 premature stop？** |
| Planner–Executor adherence | Plan-and-Act 将高层计划与执行分离，同时指出静态计划在未知观察下会失效；层次化诊断研究发现结构化高层计划并未消除低层执行瓶颈 [@erdogan2025planact; @aghzal2026hierarchical] | B→C Delivery +5 pp、Final Pass 仅 +0.56 pp；C 仍有 108 个 agent-control failure，且存在 blueprint 与实际检索/最终计划偏离 | 12/12 blueprint schema-valid，但 6/12 有实体注入、checklist 缺失或 source mismatch；CT-C grounded plan 反从 2 降至 1 | Blueprint 当前只是 prompt context，没有逐项完成状态、违反检测或执行承诺 | **RQ2：如何让 Planning Blueprint 成为可监控的 execution commitment？** |
| Constraint–Evidence–Plan state maintenance | LLM+P 展示语言到形式规划表示再到求解器的分工；PDDLEGO 在部分可观察环境中迭代更新形式状态；ChinaTravel 用 DSL 将自然语言约束与组合验证分离 [@liu2023llmp; @zhang2024pddlego; @shao2026chinatravel] | 即使 A 已获得完整 reference，Final Pass 仍只有 25/180；预算、minimum nights、route/transportation 说明“看到信息”不等于全局正确使用 | CT-C 123 个主活动中，18 个 retrieved-but-inconsistent、11 个 sandbox-valid-but-unretrieved、20 个 placeholder、4 个 invalid/fabricated | 消息历史保存 observation，却没有显式表示某条约束由哪条证据支持、落实到哪个输出字段 | **RQ3：如何在执行过程中持续维护 `Constraint ↔ Evidence ↔ Plan Field`？** |
| Reliable verification | LLM-Modulo 主张将可靠检查交给外部 model-based verifier，并反对把 LLM self-verification 当作 sound check；DeepPlanning 采用离线 sandbox 与 rule-based checker [@kambhampati2024llmmodulo; @zhang2026deepplanning] | D 对 119 个 candidate 全部验证，46 次 Replan 仅 16 个合法、4 个 post-hoc repair success；比 C 多 1,263,248 tokens，Final Pass 不变 | CT 暴露可确定性检测的 schema、实体存在性、字段一致性和 evidence provenance 错误 | 预算、日期、schema、实体和交通等可程序化检查不应全部交给另一个生成式模型；但软偏好仍需语义判断 | **RQ4：哪些约束应交给确定性或符号模块，哪些仍需要模型判断？** |
| Execution-time monitoring and targeted repair | Plan-and-Act 的 dynamic replanning 在每步后更新计划；PDDLEGO 随新信息迭代状态；DeepPlanning 指出全局检查和 backtracking 仍不足 [@erdogan2025planact; @zhang2024pddlego; @zhang2026deepplanning] | D 只能处理已有 final candidate；61/180 个无 candidate 的上游失败天然无法由 post-hoc verifier 修复 | zero-tool false stop、retrieved-but-misused 和 schema regression 都在最终输出前已经可观察，但当前链路不做中途检查 | 最终整体重写太晚且容易破坏正确字段；需要基于首次可观察偏差触发局部恢复 | **RQ5：如何基于局部状态偏差触发 targeted replan，而不是最终输出后的整体重写？** |

## Challenge 1：Information sufficiency and stopping

核心并非“会不会调用工具”，而是何时搜索、搜索哪些类别、何时可以停止。ReAct 提供闭环形式，但不自带信息充分性判据。TravelPlanner 与 DeepPlanning 的官方分析均把不完整信息获取和长程遗漏列为关键问题。

本项目进一步显示停止行为本身不能直接作为能力指标：CT-C 的 final response 增加 25 pp，但 Schema Delivery 不变，且其中两条完全没有工具证据。未来机制需要显式维护 required evidence、observed evidence 和 unresolved uncertainty，而不是只靠 Executor 的语言判断。

## Challenge 2：Planner–Executor adherence

一次性 Blueprint 可以改善任务组织，却不会自动约束 Executor。TP-C 只带来小幅 Delivery/成本变化；CT-C 更明确显示 schema-valid Blueprint 仍可能包含具体实体、遗漏类别，或在第 0 轮诱发停止。

因此研究对象应从“生成更好的计划文本”转为“让计划具有执行语义”：步骤状态、依赖、证据要求、完成条件和偏离信号都应可观测。

## Challenge 3：Constraint–Evidence–Plan state maintenance

消息历史不是结构化状态。模型即使检索到实体，也会混用价格、时间、路线或房型；即使 reference 完整，也可能违反预算和住宿夜数。更合适的中间状态应能回答：某条约束是否已解析、由哪些 observation 支持、最终落在哪个字段、是否与其他选择冲突。

## Challenge 4：Reliable verification

Stage D 的负结果针对的是本项目的“单次 post-hoc LLM Verifier + Single Replan”，不是对所有验证机制的否定。结果支持更精确的问题：哪些检查是确定性的，哪些需要语义或偏好判断，二者如何在执行期协作。

## Challenge 5：Execution-time monitoring and targeted repair

如果失败发生在信息获取、错误停止或 evidence binding 阶段，最终候选生成后才验证已经太晚。未来 repair 应尽量定位最早违反的 invariant，只更新受影响的检索任务或计划字段，并保护已经验证正确的部分。

## 冻结的研究方向

五个 RQ 不是下一版系统的功能清单，也不意味着继续叠加 Memory、Reflection 或 Multi-Agent。它们共同指向一个更窄的方向：**显式、可验证、在执行中更新的 planning state**。
