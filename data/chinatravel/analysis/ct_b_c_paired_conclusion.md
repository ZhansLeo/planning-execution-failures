# CT-B vs CT-C Paired Conclusion

## 配对结果

12 条 query、顺序、模型、工具、预算、Executor、finalization 和 evaluator 相同，CT-C 只增加一次
Structured Planner。

| 层级 | CT-B | CT-C | 结论 |
|---|---:|---:|---|
| Final response | 4/12 | 7/12 | Planner 后更容易停止检索并生成 final |
| Schema delivery | 4/12 | 4/12 | 新增 final 被 3 条 schema failure 完全抵消 |
| Schema delivery 且调用过工具 | 4/12 | 2/12 | CT-C 两条 delivery 是零工具计划 |
| Fully entity-grounded plan | 2/12 | 1/12 | Grounding 没有改善 |
| Environment pass | 0/12 | 0/12 | 无改善 |
| Logical pass | 0/12 | 1/12 | 唯一通过者 schema-invalid；schema∩logical 仍为 0 |
| All Pass | 0/12 | 0/12 | 无改善 |

Schema Delivery 配对转移是 2 条 fail→pass、2 条 pass→fail、2 条 pass→pass、6 条 fail→fail。
净变化为 0，bootstrap 95% CI 为 [-33.3,+33.3] 个百分点。All Pass 12 条均为 fail→fail。

## Grounding 结果

对所有已解析 final 的每个主活动实体做 observation 对齐：

| Grounding 指标 | CT-B | CT-C |
|---|---:|---:|
| 主实体在 observation 出现 | 100.0% | 71.5% |
| 主实体关键字段一致 | 97.2% | 56.9% |
| 市内交通段有 matching `goto` evidence | 58.6% | 43.2% |

CT-B 的 71 个活动实体全部检索过，69 个关键字段一致。CT-C 的 123 个活动中，88 个检索过，
70 个字段一致；另有 11 个 sandbox-valid 但未检索实体、20 个泛称占位符和 4 个 sandbox 无法对应
的实体。CT-C 更多 final 带来了更多无证据内容，而不是更强的 evidence utilization。

## 成本敏感性

全部 12 条上，CT-C 平均 token 下降 14.2%、工具调用下降 18.3%、延迟下降 6.9%。但这主要由
两条零工具 false stop 驱动。排除这两条后，配对的 10 条样本中：

- token 增加 2.9%；
- 工具调用仅下降 1.4%；
- 延迟增加 11.8%。

因此不支持“Planner 普遍提高检索效率”。更准确的说法是 Planner 改变了停止行为，其中既有
及时停止，也有 evidence-free early stop。

## 最终机制结论

CT-C 在本 Pilot 中表现为：

`Structured representation → stronger stopping tendency → more final responses`

但随后出现：

`false stop / schema regression / weaker grounding → no net Delivery or All-Pass gain`

所以 Planner 是控制与表示辅助机制，不是可靠的正确性机制。当前结果不足以支持直接扩展 36 条。
