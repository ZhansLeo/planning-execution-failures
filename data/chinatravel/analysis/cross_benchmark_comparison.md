# TravelPlanner × ChinaTravel Cross-benchmark 对照

## 可比边界

TravelPlanner 使用 180 条 validation；ChinaTravel 只有 12 条 paired Pilot。两者数据分布、输出
格式和 evaluator 不同，因此不能直接比较绝对分数。这里只比较机制方向：Planner 是否改善
Agent control、信息获取、证据利用、约束满足和成本。

## B → C 机制变化

| 结果 | TravelPlanner B→C | ChinaTravel CT-B→CT-C |
|---|---:|---:|
| Delivery | +5.00 pp | 0 pp |
| Final/All Pass | +0.56 pp | 0 pp |
| Token/样本 | -2.89% | -14.24% 表面值；排除零工具后 +2.92% |
| Tool calls | -8.24% | -18.34% 表面值；排除零工具后 -1.38% |
| Agent-control | 117→108 个主失败 | 无 final 8→5，但增加 2 个 false stop |

## 跨 benchmark 稳定发现

1. Explicit Planner 主要影响控制与停止行为，而不是最终正确性。
2. Blueprint 不保证 Executor 忠实执行：TravelPlanner 中仍有 108 个 delivery/agent-control failure；
   ChinaTravel 中 12/12 都存在 checklist category deviation。
3. 信息获取责任交给 Agent 后，主要瓶颈从“计划内约束错误”前移到 acquisition/control。
4. 即使实体已经检索，字段抄写、交通衔接、时间、预算和多样性仍会失败。
5. 成本下降可能来自失败路径变短，而不是能力提高，必须结合 grounding 和成功条件解释。

## ChinaTravel 新增的失败层

ChinaTravel 相比 TravelPlanner 更突出：

- 中文自然语言 hard/soft constraint 表示与 source fidelity；
- Planner 将偏好硬化或预填具体 sandbox 实体；
- `JSON mode empty content × no-tool termination` 产生伪停止；
- 更复杂的官方活动 schema 使新增 final 被 contract failure 抵消；
- 餐厅营业时间、市内交通和逐活动 evidence grounding 成为明显问题。

Planner 的 trip facts 一致率为 100%，但 oracle 类别粗粒度覆盖约 59.9%。这说明自然语言表示是
新增瓶颈之一，却不是唯一主因；当前更直接的失败仍是 Executor-control、evidence grounding 和
output contract。

## 总结

TravelPlanner 与 ChinaTravel 共同支持：

> Planner 可以帮助 Agent 组织任务或减少部分失控，但不会自动建立
> `constraint → evidence → itinerary field → global consistency` 的可靠执行链。

ChinaTravel 没有推翻 TravelPlanner 结论，反而揭示了更细的边界：Planner 的控制收益在开放
自然语言环境中可能被 false stop、实体注入、grounding 下降和 schema failure 抵消。由于 CT
只有 12 条，该结论属于小规模机制验证，不是总体性能估计。
