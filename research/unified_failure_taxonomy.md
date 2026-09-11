# Unified Planning–Execution Failure Taxonomy

## 使用目的

该 taxonomy 用于定位失败发生在哪一层，而不是把 TravelPlanner 与 ChinaTravel 的 evaluator 计数相加。两个 benchmark 的数据、schema 和 evaluator 不同，保留各自原始 category；这里仅建立共同的诊断语言。

主类别采用 **earliest supported failure** 原则：如果 Blueprint 已经漏掉住宿查询，后续住宿无证据和预算失败可以作为 secondary flags，但主问题优先定位在 representation。不能确定早期原因时，选择有直接证据的较晚层，不进行猜测。

## 分层链路

```text
L1 Natural-language understanding
 ↓
L2 Constraint representation
 ↓
L3 Information acquisition
 ↓
L4 Agent control and stopping
 ↓
L5 Planner–Executor adherence
 ↓
L6 Evidence utilization and grounding
 ↓
L7 Output contract
 ↓
L8 Global constraint satisfaction
```

## L1 — Natural-language understanding

**定义：** 从可见 query 中抽取出的事实、意图、范围或 hard/soft 属性与原文矛盾。

**信号：** 人数、天数、预算、目的地理解错误；将软偏好硬化；source text 无法在原文定位。

**边界：** 如果理解正确但 Blueprint 遗漏该约束，属于 L2；如果表示正确但最终没执行，属于 L5/L8。

- TP：没有独立、可干净计数的理解层标签。
- CT：`planner_source_text_mismatch`、可证实的 constraint understanding error。

## L2 — Constraint representation

**定义：** 正确理解的需求在结构状态中被遗漏、重复、虚构或改变语义。

**信号：** checklist 缺类别、Blueprint 预填未经检索实体、日期/住宿夜数内部冲突。

**边界：** 表示中已有正确任务但 Executor 未执行属于 L5；查询执行了但无结果属于 L3。

- TP：Planner audit 中的 constraint/checklist omission。
- CT：`retrieval_checklist_incomplete`、`planner_entity_violation`。

## L3 — Information acquisition

**定义：** 必需的信息类别、城市、路线、日期、分页或实体在 final 前从未成功出现在 observation。

**信号：** 未调用必要工具、参数错误、持续空结果、未翻页、直接使用 sandbox-valid 但未观察实体。

**关键区分：**

- **没搜到/没搜：** L3；
- **搜到了但没用：** L6；
- **搜到了但字段抄错：** L6；
- **数据库存在但轨迹没有：** 仍是 L3，不因离线存在而视为 grounded。

- TP：`tool_execution/acquisition`、`evidence_coverage`。
- CT：`information_acquisition_missing`、`sandbox_valid_but_not_retrieved`。

## L4 — Agent control and stopping

**定义：** 循环在预算内无法结束、重复无进展、超过 context，或在最低证据条件满足前结束。

**信号：** max steps、tool-budget exhaustion、重复调用、blank response、zero-tool final。

**边界：** L4 关心循环控制；某一类别为什么缺证据可同时标 L3。zero-tool final 的主问题是 false stop，而其中的具体实体无证据是 secondary grounding consequence。

- TP：`delivery/agent_control`。
- CT：`agent_control_exhaustion`、`evidence_free_false_stop`。

## L5 — Planner–Executor adherence

**定义：** Blueprint 中合法、明确的任务没有被执行，或最终路线无新证据地违背 Blueprint。

**信号：** checklist 未尝试、计划路线偏离、Executor 在完成任务前停止、计划外调用占比过高。

**边界：** Blueprint 自身漏项时以 L2 为主；Blueprint 正确而 Executor 偏离时才以 L5 为主。

- TP/CT：`blueprint_execution_deviation`、checklist completion/category deviation。

## L6 — Evidence utilization and grounding

**定义：** 相关 evidence 已观察，但最终计划忽略、错绑、改写字段，或用 placeholder/虚构实体替代。

**信号：** retrieved-but-unused、price/time/route/room mismatch、generic placeholder、invalid entity。

**关键区分：**

- `retrieved_not_used`：证据存在但没有进入输出；
- `retrieved_used_inconsistently`：实体相同但字段不一致；
- `generic_placeholder`：如“酒店附近”，无法唯一匹配；
- `fabricated_or_invalid`：轨迹和 sandbox 都无法匹配。

- TP：`grounding/utilization`、sandbox/current-city validation failure。
- CT：`evidence_utilization_failure` 及 entity-level grounding 状态。

## L7 — Output contract

**定义：** 候选内容已经形成，但 JSON、字段、enum、顺序或交通条件字段违反官方 schema。

**信号：** 非 JSON、缺字段、错误 activity type、TrainID/FlightID 条件错误、天数/顺序错误。

**边界：** 实体本身无证据属于 L6；实体和结构都合法但不可行属于 L8。

- TP：schema/format/non-delivery flags。
- CT：`output_contract_failure`，包括 raw logical pass 但 taxi schema invalid 的 near-miss。

## L8 — Global constraint satisfaction

**定义：** 计划已经 schema-valid、证据基本充分，但组合后仍违反全局或用户约束。

**信号：** budget、minimum nights、route/transport、diversity、room、cuisine、house rule、opening hours。

**边界：** 如果违反是因为没有证据或字段抄错，早期 L3/L6 优先；L8 保留为 evaluator consequence。

- TP：`route/transportation`、`budget/minimum_nights`、`diversity/preference/room_rule`。
- CT：充分证据后的 environment/logical/preference failure。

## Taxonomy 所揭示的研究变化

TravelPlanner A 的主要问题集中在已交付计划的 L6/L8；进入 query-only tool-mediated 条件后，B/C/D 的主瓶颈前移到 L3/L4。ChinaTravel 又增加 L1/L2/L7 的可见性。

因此，简单增加最终 Verifier 只覆盖链路末端。更直接的研究方向是把 L2–L6 变为显式、可更新和可检查的执行状态。
