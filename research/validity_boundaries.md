# Validity and Interpretation Boundaries

## 1. Stage A 的定义

TravelPlanner Stage A 是官方风格的 sole-planning：模型同时接收 query 和该 query 的完整、oracle-aligned reference information。它不是 query-only closed-book Direct，也不测自主信息获取能力。

因此 A 的作用是：在信息收集责任被移除时，观察模型组合证据并满足全局约束的能力。

## 2. A→B 不是工具单变量消融

A→B 同时改变：

- 模型可见的信息；
- 信息获取责任；
- 调用轮数与上下文增长；
- Agent-control 与停止决策。

所以 95%→35% Delivery 只能称为 sole-planning → two-stage system gap，不能称为“工具的因果效果”。A 与 B 的 Final Pass 分母均为全部 180 条，包括 non-delivery。

## 3. B→C 是主要 Planner 机制对照

TravelPlanner C 与 B 复用 query-only 信息条件、六个工具、30-call limit、完整 observation、模型、temperature、输出契约和 evaluator，新增一次前置 Planner。

但模型 API 即使 temperature=0 仍可能存在服务端非确定性，因此单样本转移应结合 180 条总体与 bootstrap interval，而不是作为确定性反事实。

## 4. C→D 的独立上游重跑

D 没有直接复用冻结 C candidate，而是独立重跑完整 C 链路后增加 Verifier/Replan。因此：

- 17 个 C fail→D pass；
- 17 个 C pass→D fail；

不能全部归因于 Verifier/Replan。更稳健的结论是：在完整端到端成本下，D 没有获得净 Final Pass，且后处理只能覆盖有 candidate 的 119 条。

## 5. validation #1 的开发暴露

TravelPlanner validation #1 曾用于格式开发。正式结果保留全部 180 条，并同时保存排除 #1 的 179 条敏感性结果。既有分析确认排除后不改变总体解释，但对外披露时不能把全部 validation 描述为完全未见。

## 6. ChinaTravel 是小规模泛化检查

ChinaTravel 只运行了 easy/medium/human 各 4 条，共 12 条 paired pilot。它能够：

- 检查链路是否在更开放的中文需求下出现相似 failure pattern；
- 暴露 constraint representation、grounding 和 output-contract 新问题。

它不能：

- 给出总体 benchmark 排名；
- 稳健估计 Planner 平均效应；
- 支持 split-level prevalence 结论；
- 证明某个机制在 ChinaTravel 全集上无效。

## 7. CT zero-tool 对成本的影响

CT-C 的总体均值显示 tokens −14.24%、tools −18.34%、latency −6.91%。其中两条在第 0 轮停止、没有任何 observation。

排除这两条后：

- Token +2.92%；
- latency +11.75%；
- tool calls −1.38%。

因此只能说 Planner 改变了停止行为，不能说它普遍提高了信息获取效率。

## 8. CT raw logical pass 不是合法交付

CT-C 有一个 raw logical pass，但该输出违反官方 schema。Schema∩Logical 为 0/12，All Pass 为 0/12。对外不得把 raw logical pass 计为成功案例。

## 9. 跨 benchmark 指标不可直接相加

TravelPlanner 与 ChinaTravel 使用不同：

- query 分布和语言；
- sandbox、tools 和分页协议；
- 输出 schema；
- evaluator 和 constraint semantics；
- 样本规模。

因此跨 benchmark 只比较机制方向和 failure location，不比较绝对分数，也不合并计数。

## 10. 服务端模型时间版本

两个 benchmark 均通过 `deepseek-chat` 请求模型，但 ChinaTravel 运行记录要求并观察到服务端实际模型版本；TravelPlanner 较早运行没有同等粒度的服务端版本冻结。跨 benchmark 差异可能包含模型时间版本变化。

## 11. Negative result 的范围

现有结果只针对：

- 一次静态前置 Planner；
- 将 Blueprint 作为 Executor 上下文；
- 一次 post-hoc LLM Verifier；
- 最多一次、无工具 Replan；
- 固定调用上限和完整 observation。

它不否定训练过的 Planner、动态重规划、形式状态、确定性 verifier、局部 repair、其他模型或其他预算设置。

## 12. Grounding audit 的范围

ChinaTravel grounding audit 只承认 final 产生之前的 observation。未观察实体会与固定 sandbox 交叉核对，从而区分：

- retrieved and consistent；
- retrieved but inconsistent；
- sandbox-valid but unretrieved；
- generic placeholder；
- invalid/fabricated。

对于无法通过静态数据库唯一复现的市内交通，`not_retrieved_or_fabricated` 是保守合并类别，不能全部称为 hallucination。

## 对外最小披露

任何短版材料至少保留三句话：

1. A→B 是 information-condition/system gap，不是工具因果效应。
2. ChinaTravel 只有 12 条 paired pilot，提供模式证据而非总体估计。
3. D 和跨 benchmark 分析受上游非确定性及服务端模型版本差异限制。
