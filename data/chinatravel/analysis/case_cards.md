# CT-B / CT-C 代表性案例卡

所有卡片由冻结 run 的只读审计生成；案例用于解释机制，不替代频率统计。

## 1. 零工具伪 Delivery

- 样本：`medium:e20241028161334777418`；条件：C；run：`ct-c-20260908T145356Z-e20241028161334777418`
- 主失败：`evidence_free_false_stop`；终态：`finalized_response`
- 工具/Token：0 / 12,035
- Schema / Environment / Logical / All：True / False / False / False
- 主实体 grounding：`{'not_retrieved_but_exists_in_sandbox': 3, 'generic_placeholder': 6}`
- 市内交通 grounding：`{'not_retrieved_or_fabricated': 8}`
- Planner flags：`['retrieval_checklist_incomplete', 'blueprint_execution_deviation']`
- 对照条件：B，terminal=tool_budget_exceeded，tools=30，tokens=213,205，schema=False
- 复核文件：`query_visible.json`, `planning_blueprint.json`, `trajectory.jsonl`, `final_raw_response.txt`, `parse_result.json`, `evaluation.json`

## 2. Planner 实体注入与零工具生成

- 样本：`human:h20241029143736524841`；条件：C；run：`ct-c-20260908T150133Z-h20241029143736524841`
- 主失败：`evidence_free_false_stop`；终态：`finalized_response`
- 工具/Token：0 / 13,550
- Schema / Environment / Logical / All：True / False / False / False
- 主实体 grounding：`{'not_retrieved_but_exists_in_sandbox': 8, 'fabricated_or_invalid': 4, 'generic_placeholder': 12}`
- 市内交通 grounding：`{'not_retrieved_or_fabricated': 12}`
- Planner flags：`['planner_entity_violation', 'blueprint_execution_deviation']`
- 对照条件：B，terminal=finalized_response，tools=30，tokens=271,670，schema=True
- 复核文件：`query_visible.json`, `planning_blueprint.json`, `trajectory.jsonl`, `final_raw_response.txt`, `parse_result.json`, `evaluation.json`

## 3. 及时停止但约束仍失败

- 样本：`easy:m20241028164815894420`；条件：C；run：`ct-c-20260908T145255Z-m20241028164815894420`
- 主失败：`evidence_utilization_failure`；终态：`finalized_response`
- 工具/Token：28 / 205,807
- Schema / Environment / Logical / All：True / False / False / False
- 主实体 grounding：`{'retrieved_and_used_consistently': 8, 'retrieved_but_used_inconsistently': 8}`
- 市内交通 grounding：`{'retrieved_and_used_consistently': 6, 'retrieved_but_used_inconsistently': 1}`
- Planner flags：`['blueprint_execution_deviation']`
- 对照条件：B，terminal=tool_budget_exceeded，tools=30，tokens=156,065，schema=False
- 复核文件：`query_visible.json`, `planning_blueprint.json`, `trajectory.jsonl`, `final_raw_response.txt`, `parse_result.json`, `evaluation.json`

## 4. 检索后证据利用/全局一致性失败

- 样本：`medium:e20241028161327496043`；条件：C；run：`ct-c-20260908T145509Z-e20241028161327496043`
- 主失败：`evidence_utilization_failure`；终态：`finalized_response`
- 工具/Token：27 / 298,167
- Schema / Environment / Logical / All：True / False / False / False
- 主实体 grounding：`{'retrieved_and_used_consistently': 14, 'retrieved_but_used_inconsistently': 1}`
- 市内交通 grounding：`{'not_retrieved_or_fabricated': 14}`
- Planner flags：`['retrieval_checklist_incomplete', 'blueprint_execution_deviation']`
- 对照条件：B，terminal=finalized_response，tools=22，tokens=194,477，schema=True
- 复核文件：`query_visible.json`, `planning_blueprint.json`, `trajectory.jsonl`, `final_raw_response.txt`, `parse_result.json`, `evaluation.json`

## 5. 航班字段输出契约回归

- 样本：`easy:m20241028164642633824`；条件：C；run：`ct-c-20260908T144953Z-m20241028164642633824`
- 主失败：`output_contract_failure`；终态：`finalized_response`
- 工具/Token：27 / 220,846
- Schema / Environment / Logical / All：False / False / False / False
- 主实体 grounding：`{'retrieved_but_used_inconsistently': 4, 'retrieved_and_used_consistently': 14}`
- 市内交通 grounding：`{'retrieved_and_used_consistently': 4, 'not_retrieved_or_fabricated': 11}`
- Planner flags：`['blueprint_execution_deviation']`
- 对照条件：B，terminal=finalized_response，tools=28，tokens=292,309，schema=True
- 复核文件：`query_visible.json`, `planning_blueprint.json`, `trajectory.jsonl`, `final_raw_response.txt`, `parse_result.json`, `evaluation.json`

## 6. 逻辑通过但 taxi schema near-miss

- 样本：`human:h20241029143832205713`；条件：C；run：`ct-c-20260908T150155Z-h20241029143832205713`
- 主失败：`output_contract_failure`；终态：`finalized_response`
- 工具/Token：23 / 163,491
- Schema / Environment / Logical / All：False / False / True / False
- 主实体 grounding：`{'retrieved_and_used_consistently': 24, 'generic_placeholder': 2}`
- 市内交通 grounding：`{}`
- Planner flags：`['planner_source_text_mismatch', 'blueprint_execution_deviation']`
- 对照条件：B，terminal=tool_budget_exceeded，tools=30，tokens=169,980，schema=False
- 复核文件：`query_visible.json`, `planning_blueprint.json`, `trajectory.jsonl`, `final_raw_response.txt`, `parse_result.json`, `evaluation.json`

## 7. Planner 预填实体且 Executor 耗尽预算

- 样本：`human:h20241029143648613072`；条件：C；run：`ct-c-20260908T150012Z-h20241029143648613072`
- 主失败：`agent_control_exhaustion`；终态：`tool_budget_exceeded`
- 工具/Token：30 / 286,024
- Schema / Environment / Logical / All：False / False / False / False
- 主实体 grounding：`{}`
- 市内交通 grounding：`{}`
- Planner flags：`['planner_entity_violation', 'blueprint_execution_deviation']`
- 对照条件：B，terminal=tool_budget_exceeded，tools=30，tokens=268,994，schema=False
- 复核文件：`query_visible.json`, `planning_blueprint.json`, `trajectory.jsonl`, `final_raw_response.txt`, `parse_result.json`, `evaluation.json`

## 8. 无 Planner 条件下持续 Agent-control failure

- 样本：`human:h20241029143451793119`；条件：B；run：`ct-b-smoke-20260908T080851Z-h20241029143451793119`
- 主失败：`agent_control_exhaustion`；终态：`tool_budget_exceeded`
- 工具/Token：30 / 242,314
- Schema / Environment / Logical / All：False / False / False / False
- 主实体 grounding：`{}`
- 市内交通 grounding：`{}`
- Planner flags：`[]`
- 对照条件：C，terminal=tool_budget_exceeded，tools=30，tokens=209,194，schema=False
- 复核文件：`query_visible.json`, `trajectory.jsonl`, `final_raw_response.txt`, `parse_result.json`, `evaluation.json`
