# Representative Case Cards

案例按固定诊断目的选择，用于说明“失败发生在哪一层”，不替代总体统计。完整机器可读信息与证据路径见 [`representative_cases.json`](representative_cases.json)。

## 1. TP-B #41 — 长程 Agent-control exhaustion

**Query：** 从 Philadelphia 出发，7 天游览 Virginia 三个城市，预算 $1,800。

**轨迹：** Query-only ReAct 进行了 29 次工具调用和 6 次模型调用，最终到达 `max_steps`，没有 evaluator-ready candidate。

**失败层：** L4 Agent control and stopping。

**解释：** 约束 evaluator 尚未有机会判断路线或预算，系统已经在信息获取/控制阶段失败。这类样本不能通过最终 Verifier 修复。

**支持：** Claim 1；RQ1、RQ5。

## 2. TP-C #1 — Checklist 完成不等于规划正确

**Query：** Washington 到 Myrtle Beach 三日旅行，预算 $1,400。

**轨迹：** Blueprint 合法，五项检索 checklist 全部完成，Executor 使用 7 次工具并交付。

**结果：** Day 3 早餐重复餐厅；schema 和 hard constraints 通过，但 commonsense/Final Pass 失败。

**失败层：** L8 Global constraint satisfaction。

**解释：** Planner 能组织检索，却没有在最终组合时维护餐厅多样性。该样本同时是 validation #1，应保留 development-smoke 披露。

**支持：** Claim 2、3；RQ2、RQ3。

## 3. TP-C #80 — 检索完成后的 grounding mismatch

**Query：** 两人 Atlanta 到 Chicago 三日旅行，预算 $1,900，要求 entire room。

**轨迹：** Blueprint 与 checklist 均合法并完成，Executor 交付。

**结果：** Day 2 dinner 无法通过官方 sandbox validity。

**失败层：** L6 Evidence utilization and grounding。

**解释：** 失败不是简单“没搜索”，而是具体 evidence 没有被可靠绑定到最终字段。

**支持：** Claim 3；RQ2、RQ3。

## 4. TP-D #4 — Replan 将正确候选改错

**Query：** Ontario 到 Honolulu 三日单人旅行，预算 $3,200。

**轨迹：** 原 candidate 通过全部 official constraints。Verifier 要求 repair，确定性策略采用 schema-valid Replan。

**结果：** Replan 引入重复餐厅，最终从 `Final Pass=true` 变为 `false`。

**失败层：** L8 Global constraint satisfaction；secondary flag 为 replan regression。

**解释：** schema-valid repair 不是正确 repair；没有可靠 checker 时，生成式后处理可能破坏原本正确的字段。

**支持：** Claim 4；RQ4、RQ5。

## 5. CT-C medium — Zero-tool false stop

**UID：** `e20241028161334777418`

**Query：** 上海到武汉两日单人火车旅行，预算 ¥2,500，单床房，偏好黄鹤楼类历史古迹。

**轨迹：** Executor 在第 0 轮停止，工具调用数为 0。

**结果：** 输出通过 schema，但含 3 个 sandbox-valid yet unobserved 实体、6 个 placeholder 和 8 条无 observation 支持的交通。

**失败层：** L4 Agent control and stopping。

**解释：** 这是“有 final”但没有 evidence-backed delivery。它降低了平均 Token，却不能作为检索效率提升。

**支持：** Claim 2、3；RQ1、RQ2。

## 6. CT-C easy — 搜到了但字段没有忠实使用

**UID：** `m20241028164815894420`

**Query：** 两人杭州到成都三日旅行，要求双床房和酒店健身设施。

**轨迹：** 28 次工具调用后成功交付，不属于纯 acquisition omission。

**结果：** 16 个主活动中，8 个与 observation 一致，另外 8 个虽然检索到同一实体但关键字段不一致。

**失败层：** L6 Evidence utilization and grounding。

**解释：** 该样本明确区分“没搜到”和“搜到了没用对”。增加调用次数无法自动修复 evidence binding。

**支持：** Claim 3；RQ3。

## 7. CT-C human — Planner 实体注入被 Executor 放大

**UID：** `h20241029143736524841`

**Query：** 五人南京到成都四日动车往返，观赏熊猫和附近景点，预算不超过 ¥20,000。

**轨迹：** Planner 违反 entity-free contract，Executor 随后 zero-tool stop。

**结果：** 8 个实体在 sandbox 存在但未检索，4 个无法匹配，12 个为 placeholder；交通也没有 observation 支持。

**失败层：** L2 Constraint representation；L4/L6 为后续影响。

**解释：** 上游 Blueprint 的语义错误可以在没有环境反馈的情况下被 Executor 直接扩散为完整虚构计划。

**支持：** Claim 3；RQ1、RQ2、RQ3。

## 8. CT-C human — Logical near-miss，但输出契约失败

**UID：** `h20241029143832205713`

**Query：** 中秋期间四人杭州飞广州五日旅行，两个孩子想去海洋馆和动物园。

**轨迹：** 23 次工具调用；26 个活动中 24 个检索并字段一致。

**结果：** raw logical evaluator 通过，但 taxi 被写成非法 activity type，且缺少 schema 要求字段。Schema Delivery、Schema∩Logical 和 All Pass 均失败。

**失败层：** L7 Output contract。

**解释：** 这是“计划语义接近正确，但不能合法交付”的独立失败层，不能与 constraint-understanding failure 混为一类。

**支持：** Claim 3；RQ3、RQ4。

## 案例集共同结论

八个案例覆盖了不同的断点：

```text
No candidate
→ Premature candidate
→ Blueprint not followed
→ Evidence misbound
→ Contract invalid
→ Grounded plan violates constraints
→ Repair introduces regression
```

这说明 Final Pass 只是终点指标；可靠的研究诊断必须同时观察控制、证据、契约与全局约束。
