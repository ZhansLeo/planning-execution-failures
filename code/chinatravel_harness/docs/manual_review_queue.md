# CT-B / CT-C 人工复核清单

本清单只包含自动日志不能可靠判定“因果归属”的项目。不要重跑模型或 evaluator，也不要修改
冻结 run。所有路径都位于 `ChinaTravel-Experiments/runs/`。

## 复核顺序与通用文件

每条样本按以下顺序查看：

1. `query_visible.json`：模型实际看到的需求。
2. `planning_blueprint.json`：Planner 抽取的事实、硬约束、软偏好与 checklist。
3. `planner_audit.json`：自动发现的实体预填、source mismatch、checklist coverage。
4. `trajectory.jsonl`：Executor 每轮调用了什么工具、参数和完整 observation。
5. `final_raw_response.txt` 与 `evaluator_ready.json`：最终计划；后者只在 JSON 可解析时存在。
6. `parse_result.json`：严格 schema 错误。
7. `evaluation.json`：官方 environment / logical 失败明细。

人工复核只需记录三项：`判断`、`证据所在轮次/字段`、`主要责任层`。主要责任层只能从
Planner、Executor-control、Executor-evidence-use、Output-contract、Evaluator-compatibility 中选一项；
其他问题记为 secondary。

## A. Planner 语义复核（6 条）

### `ct-c-20260908T145213Z-m20241028164800617250`

- 对比 `query_visible.json` 和 `planning_blueprint.json`，确认“颐和园”是否由 Planner 自行加入。
- 检查 checklist 缺失的类别是否属于形成完整 itinerary 的必要信息。
- 最终没有 candidate，主要失败暂定 Executor-control；Planner 缺陷只记 secondary，除非轨迹明确
  显示 Executor 被该实体或缺失 checklist 引向无效检索。

### `ct-c-20260908T145356Z-e20241028161334777418`

- 检查 blueprint 是否遗漏餐厅检索，以及这是否影响两日计划的完整性。
- `trajectory.jsonl` 只有零工具停止；判断 Executor 是否无视仍然存在的 checklist。
- 主要失败暂定 Executor-control/evidence-free early stop，Planner checklist 不完整为 secondary。

### `ct-c-20260908T145509Z-e20241028161327496043`

- 检查缺失 checklist 类别及其与 `evaluation.json` 中餐厅、市内交通错误的对应关系。
- 检查 observation 中是否已经有最终使用实体；若有而字段仍错，归 Executor-evidence-use；若无，
  再判断是 Planner checklist 缺失还是 Executor 未执行。

### `ct-c-20260908T150012Z-h20241029143648613072`

- 确认“紫金山”并非用户明确指定，而是 Planner 预填的 sandbox 实体。
- 在 `trajectory.jsonl` 搜索该实体，判断它是否实际改变检索方向；若没有，不把最终 30-call
  non-delivery 因果归给 Planner。

### `ct-c-20260908T150133Z-h20241029143736524841`

- 确认“宽窄巷子/青城山”等是否由 Planner 自行加入。
- 该样本零工具生成。检查 `final_raw_response.txt` 是否复用了 Planner 实体；若是，可形成清晰链条：
  Planner entity injection → Executor no retrieval → hallucinated/ungrounded final。

### `ct-c-20260908T150155Z-h20241029143832205713`

- 对比 hard constraint 的 `source_text` 与 `query_visible.json`，确认是合理摘录还是模型改写。
- 该问题本身不应解释最终 schema failure；最终失败的直接原因在 `parse_result.json` 中。

## B. Executor-control 复核（5 条无 final）

- `ct-c-20260908T145213Z-m20241028164800617250`
- `ct-c-20260908T145410Z-e20241028161119161993`
- `ct-c-20260908T145753Z-e20241028161015707983`
- `ct-c-20260908T145926Z-h20241029143451793119`
- `ct-c-20260908T150012Z-h20241029143648613072`

只看 `trajectory.jsonl` 的最后 3–5 轮并回答：

- 是否仍在查询已经足够的信息？
- 是否重复同一工具和参数，或反复 `goto`？
- 是否在 25 次调用前已经覆盖主要 checklist，却没有主动进入 final？
- 最后一轮是一次 bundle 越过剩余预算，还是达到轮数后仍继续请求工具？

这些终态和工具成功状态是确定性的，不必复核“是否真的没有 final”；人工复核的目标只是解释
为什么 Executor 没停。

## C. 零工具早停复核（2 条，高优先级）

- `ct-c-20260908T145356Z-e20241028161334777418`
- `ct-c-20260908T150133Z-h20241029143736524841`

查看 `trajectory.jsonl` 第一行的 `retrieval_stop_response`、`planning_blueprint.json` 和
`final_raw_response.txt`：

- Executor 是否明确声称信息已经充分？
- final 中具体实体和数值是否完全来自 query/blueprint，还是凭空出现？
- human 样本是否直接沿用了 Planner 违规预填实体？

这两条决定总体 token 下降应解释为效率收益还是过早停止，因此优先级最高。

## D. 输出契约问题（3 条，无需人工判定，仅建议抽查）

### 航班缺失 `start/end`

- `ct-c-20260908T144953Z-m20241028164642633824`
- `ct-c-20260908T145112Z-m20241028164924049935`

查看 `parse_result.json`，再打开 `evaluator_ready.json`：错误位于第 1 天首个 airplane activity
和最后一天返程 airplane activity。这两条直接归 Output-contract，不归 Planner。

### 非法顶层 `taxi`

- `ct-c-20260908T150155Z-h20241029143832205713`

查看 `parse_result.json`：第 1 天和第 5 天把 taxi 写成顶层 activity，而官方 schema 只允许它
位于 `transports`。该样本虽然 logical macro 为 100%，仍必须按 schema non-delivery 记录。

## E. 有工具但语义失败（2 条，高优先级）

- `ct-c-20260908T145255Z-m20241028164815894420`
- `ct-c-20260908T145509Z-e20241028161327496043`

针对 `evaluation.json` 中每个值为 1 的 commonsense failure，在 `evaluator_ready.json` 找到对应
实体，再在 `trajectory.jsonl` 搜索同名实体：

- observation 中没有实体：information acquisition / grounding failure；
- observation 中有实体，但价格、时间、位置或费用抄错：Executor evidence utilization failure；
- observation 和字段都正确，但日程顺序冲突：Executor global consistency failure。

这是区分“没查到”和“查到但没用好”的核心人工步骤。

## F. Evaluator exception 最小复核（2 条）

- `ct-c-20260908T145112Z-m20241028164924049935`
- `ct-c-20260908T150133Z-h20241029143736524841`

先看 `evaluation.json` 的 `Commonsense Evaluator Exception`，再看 `parse_result.json`：第一条本身
schema-invalid，异常可能是非法输入的下游结果；第二条 schema-valid 但零工具生成，更值得单独
最小复现。官方捕获异常的位置在：

`ChinaTravel/chinatravel/evaluation/commonsense_constraint.py` 的 evaluator try/except 区域。

不要用复现结果改写官方分数；只标注异常属于 invalid-input fragility 还是 valid-input evaluator bug。
