# ChinaTravel CT-B / CT-C Failure Taxonomy

## 主类别优先级

每条样本只进入一个主类别，Planner 缺陷作为 secondary flags 单独保留：

1. `agent_control_exhaustion`：工具预算或轮数耗尽，没有 final。
2. `evidence_free_false_stop`：有 final，但工具调用为 0；包括 blank/no-tool 被终止协议当作停止。
3. `output_contract_failure`：有 final 且使用过工具，但未通过官方 JSON schema。
4. `direct_fabrication_or_generic_entity`：schema 合法，但活动使用 sandbox 不存在的实体或泛称占位符。
5. `information_acquisition_missing`：实体存在于 sandbox，但没有在该轨迹 observation 中出现。
6. `evidence_utilization_failure`：实体检索过，但价格、时间、路线、房型等关键字段使用不一致。
7. `execution_consistency_or_constraint_failure`：证据及字段基本一致，仍违反时空、预算或用户约束。
8. `success`：官方 All Pass。

## 主类别结果

| 主类别 | CT-B | CT-C |
|---|---:|---:|
| Agent-control exhaustion | 8 | 5 |
| Evidence-free false stop | 0 | 2 |
| Output-contract failure | 0 | 3 |
| Evidence-utilization failure | 3 | 2 |
| Execution/constraint failure | 1 | 0 |
| Success | 0 | 0 |

Planner 的 secondary flags 仅存在于 CT-C：3 条 entity injection、3 条 checklist incomplete、
1 条 source-text mismatch，共涉及 6 个不重复样本。Planner 12/12 均有合法 blueprint，trip facts
一致率为 100%，所以没有 `planner_non_delivery`；这些 secondary flags 不能在没有轨迹证据时被
当作最终失败的直接原因。

## Grounding 状态

- `retrieved_and_used_consistently`：实体/ID 在先前 observation 中出现，关键字段一致。
- `retrieved_but_used_inconsistently`：实体检索过，但至少一个关键字段不一致。
- `not_retrieved_but_exists_in_sandbox`：实体真实存在，但该 run 从未观察到。
- `fabricated_or_invalid`：轨迹未观察到，固定 sandbox 也无法对应。
- `generic_placeholder`：如“酒店附近”“武汉市区酒店”，不是可评测的正式实体。
- `not_retrieved_or_fabricated`：市内交通段没有匹配的 `goto` observation；固定数据库无法在不调用
  路由工具的情况下进一步区分真实但未查与直接编造。

该 taxonomy 是诊断口径，不替代 ChinaTravel 官方 evaluator。
