# CT-B / CT-C 深度失败分析与下一步判断

## 一、最重要的结论修正

CT-C 的表面结果是：final response 从 4/12 增至 7/12，平均工具调用下降 18.3%，平均
token 下降 14.2%。但逐样本拆解后，这不能简单解释成“Planner 让检索更高效”。

两条 CT-C 样本在得到 blueprint 后完全没有调用工具，直接生成计划。它们把大量工具调用和
token 变成了零，但 environment micro 只有 22.2 和 9.1。排除这两条零工具样本后，剩余
10 条 CT-C 相比配对 CT-B：

- 平均 token **增加 2.9%**；
- 平均工具调用只下降 **1.4%**；
- 平均延迟 **增加 11.8%**。

因此，更准确的机制结论是：

> Structured Planner 提高了 Executor 的停止倾向，但这种倾向同时包含及时停止与无证据早停。
> 当前数据不能证明 Planner 普遍提高了检索效率。

进一步检查 `medium:e20241028161334777418` 后确认：第 0 轮不是明确输出“停止检索”，而是只
返回空白字符且没有 `tool_calls`。冻结 harness 把任何“无 tool call”响应都当作检索完成，并
立即触发一次无工具 finalization。因此该样本同时暴露 `Executor blank response` 与
`termination protocol treats blank as stop` 两个问题；最终计划没有任何 observation 支持。

该空响应还与请求配置有关：工具选择轮同时设置了 `tool_choice=auto` 与
`response_format=json_object`。前者允许模型选择不调用工具；DeepSeek 官方文档明确说明 JSON
Output 偶尔可能返回空 content。控制器没有保存 `finish_reason`，也没有区分“有效 final / 明确
停止 / 空响应”，使一次 provider/model 空输出被放大为完整的虚构行程。因此这条应归为
`protocol-mediated agent-control failure`，不能单独作为 Planner 改善 Delivery 的证据。

## 二、失败发生在哪一层

### 1. Planner 表示层：基本事实好，语义约束仍不可靠

12 条 blueprint 的出发地、目的地、天数和人数一致率为 100%，source text 定位率为
98.96%，检索清单类别设计覆盖率为 95%。这说明 Planner 对显式 trip facts 的抽取较稳定。

但仍有三个明显问题：

- 与 oracle hard-logic 的粗粒度类别覆盖均值只有 59.9%；
- 3/12 blueprint 填入用户未指定的具体 sandbox 景点；
- 1 条把自行改写的表述当作原文 source text。

所以 `valid JSON blueprint` 只证明结构合法，不证明约束理解完整，也不证明 Planner 遵守了
“不预填具体实体”的语义要求。

### 2. Executor 控制层：停止改善，但 checklist 没有成为执行承诺

CT-B 有 8 条因 tool budget / max steps 无计划结束，CT-C 降为 5 条。这是 Planner 最真实的
正向信号。然而 12 条 CT-C 的实际工具类别都没有完整覆盖 blueprint checklist；两条甚至是
零工具结束。

所有真实工具调用均成功，工具运行错误为 0。因此主要瓶颈不是 sandbox 或 tool API 不稳定，
而是模型如何决定“查什么、查多久、何时停止，以及如何把 observation 写进行程”。

### 3. 输出契约层：新增的 final response 被 schema failure 抵消

CT-C 比 CT-B 多生成 3 个 final response，但 CT-C 恰好有 3 个 final 未通过 schema：

- 两条遗漏 airplane activity 必需的 `start` / `end`；
- 一条把 `taxi` 写成官方 schema 不允许的顶层 activity type，同时遗漏 `position`。

CT-B 的 4 个 final 全部通过 schema；CT-C 的 7 个 final 只有 4 个通过。因此 final-response
改善没有转化为 Delivery 改善。这不是信息获取失败，而是 structured output / execution
consistency 回归。

### 4. Evidence 与环境可行性层：严格交付中只有两条真正查过工具

CT-C 的 4 条 schema delivery 中，两条没有任何 tool observation。若把“至少使用过一次官方
工具”作为最弱的 evidence-backed 条件，则 evidence-backed delivery 从 CT-B 的 4/12 降到
CT-C 的 2/12。

而且 CT-C 的 4 条 schema-delivered plan 没有一条通过 environment macro。高频问题集中在：

- 餐厅开放时间、重复选择、价格/可用性和用餐时间；
- 城际交通费用；
- 景点价格与费用；
- 市内交通费用、时空顺序和地点衔接。

这说明即便完成检索并产出合法 JSON，模型仍无法稳定把离散 observation 组合成全局一致的
itinerary。Planner 解决的是“意图表示”，却没有建立 `constraint → evidence → itinerary field`
的执行绑定。

### 5. 自然语言约束：目前不是唯一主瓶颈

human split 中 CT-C 的 Delivery 仍为 1/4。Planner 能正确抽取人数、天数、预算、交通和景点
意图等显式事实，但仍出现：

- 30-call 耗尽；
- blueprint 预填实体；
- 零工具 hallucinated plan；
- checklist 与实际调用偏离；
- 有逻辑通过但 schema 无效的 near miss。

所以 ChinaTravel 的自然语言结构化确实增加了一个 failure layer，但当前更强的瓶颈仍是
acquisition control、evidence utilization 与输出契约。不能把 human 低分单独归因于中文需求
理解失败。

## 三、四类代表性转移

### 真正的控制改善：`easy:m20241028164815894420`

CT-B 在 30 次工具调用后没有输出；CT-C 在 28 次后输出合法计划。这是最接近预期机制链的
样本：Planner 帮助模型及时停止。但其 environment micro 仅 42.9、logical micro 71.4，说明
停止问题改善后，证据利用和约束满足仍未解决。

### 伪效率正转移：`medium:e20241028161334777418`

CT-B 耗尽 30 次工具；CT-C 零工具便形成 schema-valid plan，token 从 213,205 降至 12,035。
然而 environment micro 只有 22.2。这是 Delivery 指标被结构合法性“抬高”，而 grounding
实际恶化的典型样本。

### 输出契约负转移：两个 easy 样本

`m20241028164642633824` 与 `m20241028164924049935` 在 CT-B 中都可交付；CT-C 也完成了
27/30 次工具调用并生成 final，却同时遗漏往返航班的 start/end。两条完全相同的 schema
错误提示 blueprint 加入上下文后，Executor/finalizer 对实体字段契约的维护可能变弱。

### 有价值但未交付的 near miss：`human:h20241029143832205713`

CT-B 无输出；CT-C 在 23 次调用后结束，logical macro 达到 100%，environment micro 为
63.0，却因为把 taxi 写成顶层 activity 而 schema failure。它说明 CT-C 可能改善了一部分逻辑
约束维护，但这种改善会被输出契约错误完全阻断。

## 四、关于 evaluator exception

两条 CT-C 输出触发 commonsense evaluator 捕获的 pandas 赋值异常。官方 evaluator 将其记录为
`Commonsense Evaluator Exception=1` 并判为不通过。这里不应直接断言 evaluator 本身损坏：
其中一条同时存在 schema-invalid 航班字段，另一条是零工具生成且包含大量无依据实体。更合理的
处理是用已保存输出进行只读最小复现，区分“非法输入触发的预期脆弱性”和“合法 schema 下的
evaluator bug”。正式指标仍保留官方原结果。

## 五、现在是否扩展到 36 条

结论：**暂不扩展。** 当前 12 条已经足以说明总指标混合了相反机制。如果直接增加样本，只会
更精确地估计一个含义不清的平均数。

下一步应先完成四项不调用模型的分析：

1. 做 entity-level grounding audit：逐项判断 final 中的航班、景点、餐厅、住宿和交通数值是否
   在此前 observation 出现。
2. 为 4 个 Delivery 正负转移、2 个零工具 final 和 human split 形成固定模板案例卡，并由人工
   复核 failure tag。
3. 后续汇报同时区分 `final response`、`strict schema delivery`、`evidence-backed delivery` 和
   `All Pass`，不再让单一 Delivery 掩盖无证据计划。
4. 用保存的输出最小复现两条 evaluator exception，不改变 plan、不重新评分择优。

完成后再设门槛：只有 evidence-backed delivery 或 grounding 明确改善，且提升不是由零工具早停
造成，才值得运行 36 条。如果主要问题确认是 output contract，可以建立单独的 CT-C-v2 研究
协议；它必须作为新实验，而不能改写或混入当前冻结 Pilot。

结构化数据见 `experiments/ct-pilot-v1/ct_failure_analysis.json`。
