# ChinaTravel 泛化验证最终收口

## 交付范围

本轮不调用模型、不调用工具、不重新评测，仅从冻结 CT-B/CT-C 的 manifest、trajectory、final
和 official evaluation 生成以下六项：

1. Entity/field-level grounding audit；
2. 8 个代表性案例卡；
3. Agent-control → Output-contract → Grounding → Official-correctness 四层指标；
4. 互斥主 Failure taxonomy 与 Planner secondary flags；
5. CT-B/CT-C paired conclusion；
6. 与 TravelPlanner A/B/C/D 的 cross-benchmark 机制对照。

## 四层漏斗

| 层级 | CT-B | CT-C |
|---|---:|---:|
| 1. Final response | 4/12 | 7/12 |
| 2. Schema delivery | 4/12 | 4/12 |
| 3a. Schema delivery 且有 observation | 4/12 | 2/12 |
| 3b. Fully entity-grounded plan | 2/12 | 1/12 |
| 4a. Schema∩Environment pass | 0/12 | 0/12 |
| 4b. Schema∩Logical pass | 0/12 | 0/12 |
| 4c. All Pass | 0/12 | 0/12 |

CT-C 唯一的 raw logical pass 发生在 schema-invalid 计划上，因此不能视为成功交付。

## Grounding audit

审计只认可 final 生成前 trajectory 中真实出现的 observation。未出现实体再与固定本地 sandbox
交叉核对，以区分 valid-but-unretrieved、invalid/fabricated 和 generic placeholder。

| 主实体状态 | CT-B | CT-C |
|---|---:|---:|
| Retrieved + field consistent | 69 | 70 |
| Retrieved but field inconsistent | 2 | 18 |
| Sandbox valid but not retrieved | 0 | 11 |
| Generic placeholder | 0 | 20 |
| Fabricated/invalid | 0 | 4 |

CT-C 虽然 final 更多，但新增内容的证据质量明显下降。市内交通 matching observation 比例也从
58.6% 降到 43.2%。

## Failure taxonomy

| 主失败 | CT-B | CT-C |
|---|---:|---:|
| Agent-control exhaustion | 8 | 5 |
| Evidence-free false stop | 0 | 2 |
| Output-contract failure | 0 | 3 |
| Evidence-utilization failure | 3 | 2 |
| Execution/constraint failure | 1 | 0 |

CT-C 把 3 个失败从“没有 final”移动到“有 final 但 schema 错误”，另外产生 2 个零工具 false
stop。Planner 自身没有 non-delivery，但 6 个样本存在 entity injection、checklist incomplete 或
source mismatch；这些只作为 secondary flags，不替代主失败归因。

## Paired conclusion

CT-C final response 提升 25 个百分点，但 Schema Delivery 和 All Pass 均无变化。Activity grounding
从 100.0% 降至 71.5%，字段一致率从 97.2% 降至 56.9%。总体 token 下降由两个零工具样本主导；
排除它们后 token 上升 2.9%、延迟上升 11.8%。

结论：Structured Planner 在该 Pilot 中增强停止倾向，却没有建立可靠的 evidence-grounded
execution；其控制收益被 false stop、schema regression 和证据利用失败抵消。

## Cross-benchmark conclusion

TravelPlanner B→C 的 Delivery +5.0 pp、Final Pass +0.56 pp、token -2.89%；ChinaTravel 的
Schema Delivery 与 All Pass 都是 0 pp。两个 benchmark 方向一致地表明 Planner 更像控制/表示
辅助，而不是正确性机制。ChinaTravel 额外暴露自然语言 constraint representation、Planner 实体
注入、JSON-mode blank response、活动 schema 和逐字段 grounding 问题。

## 文件索引

- `analysis/build_closing_analysis.py`：可复现只读分析入口。
- `analysis/grounding_audit.json`、`grounding_entities.csv`：完整 grounding 结果。
- `analysis/grounding/B|C/*.json`：逐样本审计。
- `analysis/four_layer_metrics.json|csv`：四层指标。
- `analysis/failure_taxonomy.json|csv|md`：failure taxonomy。
- `analysis/case_cards.json|md`：8 个案例卡。
- `analysis/ct_b_c_paired_conclusion.md`：paired conclusion。
- `analysis/cross_benchmark_comparison.json|md`：跨 benchmark 对照。
- `analysis/closing_integrity.json`：完整性检查。

当前证据不支持立即扩展到 36 条。若继续，先人工复核案例卡中两条 zero-tool、两条
evidence-utilization 和两条 Planner entity-injection 样本，再决定是否建立新的 paired protocol。
