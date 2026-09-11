# Frozen Research Claims

这些是未来 Deck、摘要和联系材料可以使用的最高层结论。除非开展新的预注册实验，否则不应通过改变措辞扩大其因果或泛化范围。所有数字来自 [`results_master.json`](results_master.json)。

## Claim 1 — Tool-mediated planning changes the failure regime

> **Tool-mediated planning introduces substantial information-acquisition and agent-control failures beyond plan generation.**

### 中文解释

当所需信息不再直接提供、而由 Agent 自主检索时，任务不再只是组合一份计划。Agent 还必须决定查什么、如何修正空结果、何时停止以及如何保存证据。TravelPlanner A→B 的主要变化是 Delivery 和成本，而不是稳定的 Final Pass 提升。

### Evidence

- TP-A（oracle-aligned evidence）Delivery 为 171/180；TP-B（query-only + tools）为 63/180，下降 60 pp。
- TP-B 有 117/180 个主失败位于 delivery/agent-control，平均使用 19.43 次工具调用和 57,642 tokens/query。
- CT-B 有 8/12 个 Agent-control exhaustion，只有 4/12 产生 final response。
- TravelPlanner 官方论文同样报告工具使用、不完整信息收集、约束维护和长程退化问题 [@xie2024travelplanner]。

### Boundary

TP A→B 同时改变信息输入与信息获取责任，因此只表示 **sole-planning → two-stage system gap**。

### Safe wording

- “Autonomous information acquisition substantially changed the system's failure profile.”
- “The two-stage setting incurred much higher non-delivery and inference cost.”

### Prohibited wording

- “Tools caused a 60-point performance drop.”
- “ReAct is worse than direct LLM planning.”
- “Tool use does not help planning.”

## Claim 2 — Explicit planning changes control more than correctness

> **Explicit planning changes agent-control and stopping behavior more consistently than end-to-end correctness.**

### 中文解释

在同一 query-only、工具和 evaluator 条件下加入一次 Planner，TravelPlanner 的 Delivery 小幅上升、工具调用略降，但 Final Pass 几乎不变；ChinaTravel 的 final response 增加，却没有增加 schema-valid 或 All-Pass 输出。

### Evidence

- TP B→C：Delivery +5.00 pp，Final Pass +0.56 pp，tokens/query −2.89%，tool calls/query −8.24%。
- CT B→C：Final Response +25 pp，但 Schema Delivery 0 pp、All Pass 0 pp。
- CT-C 新增 2 个 zero-tool false stop。排除这两条后，Token +2.92%、延迟 +11.75%、工具调用仅 −1.38%。

### Boundary

CT 只有 12 条 paired pilot，不能据此估计总体 Planner 效应。TP 中 +0.56 pp 仅对应一个净新增 Final Pass，且 paired 置信区间覆盖零。

### Safe wording

- “Planner affected termination and modestly improved control in TravelPlanner.”
- “We found no stable evidence that the one-shot Planner improved end-to-end correctness.”

### Prohibited wording

- “Planner improves search efficiency across benchmarks.”
- “Planner is ineffective.”
- “Planner reduced ChinaTravel cost by 14.2%”而不同时披露 zero-tool sensitivity。

## Claim 3 — A valid Blueprint is not an execution guarantee

> **A schema-valid planning blueprint does not guarantee evidence-grounded or faithful execution.**

### 中文解释

结构化输出成功只证明 Planner 遵守 JSON 形式，不证明约束理解、检索清单或 Executor 执行正确。当前 Blueprint 是被动上下文，没有逐项完成条件和偏离检测。

### Evidence

- TP-C 仍有 108/180 个 delivery/agent-control 主失败；Delivery 为 72/180，Final Pass 为 29/180。
- CT-C 12/12 Blueprint 可解析，但 6/12 存在实体注入、checklist 缺失或 source mismatch。
- CT fully grounded plan 从 B 的 2/12 降至 C 的 1/12。
- CT-C 的 123 个主活动中只有 70 个检索后字段一致；另有 18 个检索后使用不一致、11 个未检索、20 个 placeholder、4 个 invalid/fabricated。
- 近期层次化 web-agent 诊断也区分高层规划与低层执行，并报告执行仍是主要瓶颈 [@aghzal2026hierarchical]。

### Boundary

这些结果只检验一次前置、静态 Blueprint；不能推广到训练过的 Planner、动态 Planner 或带执行约束的形式计划。

### Safe wording

- “Blueprint validity was a formatting property, not a semantic or execution guarantee.”
- “The observed gap motivates explicit plan state and adherence monitoring.”

### Prohibited wording

- “Structured planning cannot work.”
- “All Planner–Executor systems suffer the same failure.”
- “12/12 Planner outputs were correct.”

## Claim 4 — The tested post-hoc repair was late and brittle

> **Under our protocol, a single post-hoc LLM Verifier and no-tool Replan could not reliably recover upstream failures and added substantial cost.**

### 中文解释

Stage D 只在 C 链路已产生候选后介入，因此无法处理没有候选的上游失败。Verifier 和 Replan 自身也会产生格式、引用和约束错误。

### Evidence

- 180 条 D 运行中只有 119 条有 candidate；61 条上游无 candidate，Verifier 无法介入。
- 119 次 Verifier 调用触发 46 次 Replan，只有 16 次 Replan schema-valid，只有 4 个 post-hoc repair success。
- D 比 C 多使用 1,263,248 tokens，平均延迟增加 4.85 秒，Final Pass 仍为 29/180。
- C→D 有 17 个 fail→pass 和 17 个 pass→fail；McNemar p=1.0。
- LLM-Modulo 工作主张将可靠检查与外部 model-based verifier 更紧密结合 [@kambhampati2024llmmodulo]。

### Boundary

D 独立重跑整个 C 上游，paired transition 包含上游非确定性；4 个 repair success 是离线诊断，不是 evaluator feedback 驱动选择。

### Safe wording

- “The tested post-hoc LLM repair did not yield a net Final Pass gain.”
- “Many failures occurred before a verifier could intervene.”

### Prohibited wording

- “Verifier and Replan never work.”
- “Verification has no value for LLM agents.”
- “D caused exactly 17 regressions”而不披露独立上游重跑。

## Cross-claim synthesis

四条 Claim 共同支持的是 failure localization，而不是组件排名：

```text
Information condition
→ Acquisition/control
→ Plan adherence
→ Evidence binding
→ Output contract
→ Global correctness
```

下一步研究不应再任意增加 Agent 模块，而应让上述中间状态可表示、可检查、可局部修复。
