# ChinaTravel 第一条 CT-B Smoke 记录

## 定位

该阶段是 TravelPlanner 机制结论的跨 benchmark 泛化检查。当前只验证环境和
单样本实验协议，不将一次 smoke 的得分解释为方法结论，也未启动 Pilot。

## 环境结论

- 官方仓库固定为 commit `0936f2727dd102ad811ed015b7bf6f7d6533f28e`。
- 使用官方中文固定 sandbox，共安装 132 个数据库文件。
- easy、medium、human 本地固定数据分别包含 300、150、154 条。
- 18 个结构化领域工具向模型开放；任意字符串命令、query loader 和 split 管理工具不开放。
- 21 项本地工具调用检查通过，覆盖全部开放工具、分页、空结果和参数错误。
- 官方 schema、commonsense/environment 和 hard logical evaluator 已完成本地调用验证。
- Oracle constraint 字段只保留给 evaluator，不存在于模型 prompt 或 tool trajectory。

## 唯一真实运行

- 条件：CT-B Query-only ReAct
- split：中文 easy
- UID：`e20241028160248698752`
- 选择规则：官方 easy CSV 第一行
- 模型：`deepseek-chat`，temperature 0
- 结果：`parallel_tool_calls`

模型首轮同时请求了城际火车、景点字段和餐厅字段三个工具。协议规定每轮最多
一个工具，因此运行确定性终止，没有执行工具，也没有产生最终 itinerary。

- model calls：1
- tool calls：0
- tokens：3,820（input 3,644；output 176）
- model latency：约 3.03 秒
- Delivery：失败
- Schema / Environment / Logical / All Pass：均记为失败
- Preference：不适用于 easy/medium/human 主 split

这不是网络、认证、数据库或 evaluator 故障，而是首个可观察的 Agent-control
non-delivery。按照预注册边界，没有顺序执行并行请求、没有修改 prompt、没有
repair，也没有重跑同一 query。

## 测试说明

- 独立 harness：5 项契约测试全部通过。
- 官方仓库：51 项测试通过，6 项失败；其中 5 项要求本阶段未安装的英文
  `database_en`，另 1 项是 Windows 下测试通过修改 `HOME` 模拟用户目录时的
  路径展开差异。中文 tools/evaluator 闭环相关检查通过，官方 tracked files
  保持零改动。

## 下一道门

当前已经验证真实 API 请求、工具选择、终止记录与失败计分链路，但尚未观察到
真实的 `Tool → Observation → Final Output`。在决定是否冻结 12 条 Pilot 前，
应先审查“并行工具请求即失败”是否继续作为 CT-B/CT-C 的正式控制规则。该决定
会改变协议，因此不能在本 smoke 内静默调整。

## v0.2 开发修订

后续开发检查确认 DeepSeek 原生返回多工具 bundle，因此 v0.2 将 bundle 按模型
顺序串行执行，并以工具调用总数执行 30-call 上限。easy #1 和 #2 均完成检索并
生成完整计划，但缺少 TravelPlanner 阶段已经使用的 API JSON mode，导致 Markdown
包裹响应被严格解析拒绝；easy #3 则暴露旧字符阈值不等于 56k token 阈值。

正式 Pilot 前只修复这两项协议一致性问题：启用 `response_format=json_object`，
并使用稳定的 token 估算实施 56k context guard。不增加 JSON repair，不改变工具、
检索策略、30-call budget 或 evaluator。

JSON mode 验证随后发现重复检测必须同时包含 observation：连续 `next_page` 虽然
工具名和参数相同，但页面内容持续变化，不属于死循环。v0.4 将调用与返回内容
共同纳入重复签名，仍然只在连续三个完全相同的 call-result bundle 时终止。

开发调用还确认请求名 `deepseek-chat` 当前由服务端解析为
`deepseek-v4-flash`。因此 CT-B/CT-C 可以保持同模型配对，但 CT 与更早完成的
TravelPlanner 结果存在模型时间版本混杂，跨 benchmark 只作辅助解释。v0.5 同时
向 Agent 明示 30-call 总预算和 bundle 串行语义，并在 manifest 保存服务端实际
模型名。

服务端当前默认启用 thinking mode；带 tools 的多轮会要求完整回传隐藏的
`reasoning_content`。旧 `deepseek-chat` 实验则是非思考模式。v0.6 因而显式设置
`thinking.type=disabled`，既保持 TravelPlanner 运行设定，也避免把未回传的推理
状态误诊为工具或 JSON failure。

由于当前服务端在带 tools 的结束轮仍可能把草稿或 DSML 写进 `content`，v0.7 将
“停止检索”和“输出计划”拆成同一 Executor 的两个动作：停止后追加一次无工具、
JSON-mode 的最终序列化调用。它不解析或修复候选，不接触 evaluator，也不获取
新证据；CT-B/CT-C 共用同一策略。
