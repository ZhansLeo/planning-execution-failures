# ChinaTravel CT-B / CT-C 12 条配对 Pilot 报告

## 研究定位与对照

本实验是 TravelPlanner 机制结论的小规模跨 benchmark 泛化检查。CT-B 从中文自然语言
query 出发自主调用 ChinaTravel 官方本地工具；CT-C 仅在相同 Executor 前增加一次
Structured Planner。两者使用相同 12 条 query、`deepseek-chat` 请求（服务端均解析为
`deepseek-v4-flash`）、temperature 0、18 个工具、30 次工具调用上限、完整 observation、
无工具 JSON finalization 和官方 evaluator。

Planner 不访问工具、sandbox、oracle constraint translation 或 evaluator，只把 visible query
表示为 trip facts、hard constraints、soft preferences、retrieval checklist 和 planning risks。
正式 Pilot 前，3 条排除在 Pilot 外的 easy UID 均完成真实 development 闭环。

## 主要结果

| 指标 | CT-B | CT-C | 变化 |
|---|---:|---:|---:|
| Delivery | 4/12 (33.3%) | 4/12 (33.3%) | 0 |
| Environment macro pass | 0/12 | 0/12 | 0 |
| Logical macro pass | 0/12 | 1/12 (8.3%) | +1 |
| All Pass | 0/12 | 0/12 | 0 |
| 平均工具调用 | 29.08 | 23.75 | -5.33 (-18.3%) |
| 平均 token | 229,938 | 197,205 | -32,733 (-14.2%) |
| 平均延迟 | 70.55 s | 65.68 s | -4.88 s (-6.9%) |
| CT-C 平均 Planner token | — | 2,492 | — |

Delivery 配对转移为：2 条 `B fail → C pass`、2 条 `B pass → C fail`、2 条持续 pass、
6 条持续 fail。净变化为 0，bootstrap 95% CI 为 [-33.3, +33.3] 个百分点。All Pass 的
12 条均为 fail → fail。

CT-C 的终态从 CT-B 的 4 个 finalized / 8 个预算或步数终止，变化为 7 个 finalized /
5 个预算或步数终止。Planner 改善了主动结束检索，但 finalized response 不等于 schema-valid
Delivery：7 个 final 中只有 4 个满足交付契约。

## 分层观察

| Split | CT-B Delivery | CT-C Delivery | CT-C 平均工具调用 | CT-C 平均 token |
|---|---:|---:|---:|---:|
| easy | 2/4 | 1/4 | 28.75 | 216,535 |
| medium | 1/4 | 2/4 | 21.75 | 207,015 |
| human | 1/4 | 1/4 | 20.75 | 168,065 |

样本量很小，split 差异不能作显著性结论。human 上成本下降并未转化为更高 Delivery；这与
“自然语言约束结构化后，Executor 仍可能不检索或不忠实执行”的解释一致。

## Planner 与执行审计

- 12 个 Planner 均通过严格 JSON schema，服务端实际模型一致，无 planner non-delivery。
- 3/12 blueprint 填入了用户未明确指定的具体 sandbox 景点（颐和园、紫金山、宽窄巷子等），
  被实体隔离审计标记。这说明严格结构 schema 并不能独立保证“Planner 不预填实体”的语义约束。
- Planner 平均约占 CT-C token 的 1.3%；总 token 下降来自 Executor 消耗下降，而非观察裁剪。
- 平均 checklist 执行覆盖率 65.8%；oracle 类别覆盖诊断均值 59.9%，oracle 仅在运行后使用。
- 两条 CT-C 样本在 Planner 后未调用任何工具就生成计划。这降低成本，却展示了 blueprint
  不能强制 evidence acquisition。
- 两条可解析计划触发官方 commonsense evaluator 的内部表格赋值异常。原始输出与官方结果
  均已保留，没有模型重跑或计划修复；这是 evaluator compatibility 限制。

## Failure → Mechanism → Effect

`Agent-control / 检索停止困难 → Structured Planner → finalized 4→7，工具和 token 下降`

`自然语言约束表示 → Structured blueprint → logical macro 出现 1 条通过，但 All Pass 无变化`

`Blueprint 与执行脱节 → 自主 ReAct Executor → checklist 覆盖不完整，并出现零工具计划`

`约束满足 / 环境可行性失败 → 仅前置 Planner → 未被稳定修复，All Pass 仍为 0`

当前最稳妥的结论是：CT-C 在 12 条 Pilot 上是“效率/控制层面的局部有效”，不是“正确性
提升”。它与 TravelPlanner 中 Planner 主要改善 Agent control、但很少改善 Final Pass 的
发现方向一致。Delivery 正负转移相抵，每新增 Delivery / All Pass 的 token 成本均不成立。

## 有效性限制与下一步门槛

Pilot 只有 12 条，置信区间宽，且官方 evaluator 对两条计划出现兼容性异常。目前不应直接
扩展到 36 条或增加 Verifier/Replan 来追分。下一步应先做只读案例分析：对 2 条
`B fail → C delivery`、2 条 `B delivery → C fail`、两条零工具 final 和 human split 的
constraint representation / acquisition / execution consistency 分别编码，确认成本下降究竟
来自更聚焦检索还是过早停止。只有趋势具有清晰、可复核的机制证据时，才讨论 36 条扩展。

## 可复现文件

- `experiments/ct-pilot-v1/manifest.json`：冻结 CT-B 样本与协议。
- `experiments/ct-pilot-v1/ct_c_manifest.json`：CT-C Planner 与 Executor 对照协议。
- `experiments/ct-pilot-v1/state_ct_c.json`：12 条 CT-C run 映射。
- `experiments/ct-pilot-v1/ct_b_summary.json`：CT-B 汇总。
- `experiments/ct-pilot-v1/ct_c_summary.json`：CT-C 汇总。
- `experiments/ct-pilot-v1/ct_b_c_comparison.json`：配对转移、bootstrap 与成本变化。
- `runs/ct-c-*`：逐样本 Planner、trajectory、usage、audit 与官方 evaluation。
