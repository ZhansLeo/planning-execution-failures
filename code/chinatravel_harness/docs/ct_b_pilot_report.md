# CT-B：12 条 Query-only ReAct Pilot

## 实验定位

CT-B 是 ChinaTravel 泛化验证的 query-only、official-tools ReAct 条件。它用于为
后续同样本 CT-C Structured Planner 对照建立基线，不复刻 TravelPlanner 全部阶段。

协议 `ct-b-react-v1.0-pilot` 在运行前冻结。12 条样本由 seed `20260904` 从
easy、medium、human 各抽 4 条，并排除所有开发 UID。运行不使用 oracle
translation、JSON repair、Verifier、Replan、Memory 或多智能体。

## 总体结果

| 指标 | CT-B Pilot |
|---|---:|
| 完成样本 | 12 / 12 |
| 基础设施失败 | 0 |
| Delivery / Schema Pass | 4 / 12（33.3%） |
| Environment Macro Pass | 0 / 12 |
| Logical Macro Pass | 0 / 12 |
| All Pass | 0 / 12 |
| 总 Tokens | 2,759,254 |
| 平均 Tokens / 样本 | 229,938 |
| 平均 Tool Calls / 样本 | 29.08 |
| 平均延迟 / 样本 | 70.55 秒 |

四条成功交付 schema-valid itinerary 的样本中，environment micro 平均为
73.54%，logical micro 平均为 77.71%；但没有样本同时通过全部 environment 或
logical constraints，因此 All Pass 为零。

## 分层 Delivery

| Split | Delivery | 平均 Tokens | 平均 Tool Calls |
|---|---:|---:|---:|
| easy | 2 / 4（50%） | 208,901 | 29.25 |
| medium | 1 / 4（25%） | 242,674 | 28.00 |
| human | 1 / 4（25%） | 238,240 | 30.00 |

12 条中只有 4 条进入无工具 JSON finalization 并成功交付；7 条因为模型新一轮
tool-call bundle 超过剩余预算而终止，1 条在用满 30 次后仍继续请求工具。由此形成：

`12 queries → 4 delivered → 0 environment pass → 0 logical pass → 0 all pass`

## 初步 Failure Analysis

### 1. Agent control / information acquisition 是首要瓶颈

8/12 没有交付最终计划，且平均工具调用已接近 30-call 上限。这不是 API 或
sandbox 故障，而是 Agent 无法在有限预算中判断证据是否充分并及时停止检索。

### 2. 成功交付不等于约束满足

四条 delivered 样本仍存在时间顺序、实体费用、城际交通费用、票数或用户逻辑
约束错误。说明在获得大量 observation 后，evidence utilization 与 execution
consistency 仍未解决。

### 3. human 的自然语言问题尚不能单独归因

human Delivery 为 25%，但 medium 也是 25%，且 human 四条都使用满 30 次工具。
当前样本量只能支持“human 没有更容易”的观察，不能证明自然语言 constraint
understanding 已经是独立主因。需要与同样本 CT-C blueprint audit 配对后再判断。

### 4. 成本压力明显

CT-B 平均约 23 万 tokens，是多轮完整 observation 反复进入上下文造成的。当前
阶段不做 observation 压缩，因为这会新增实验变量；CT-C 是否减少无效检索和
总体 token 将成为主要机制指标。

## 模型版本限制

请求名仍为 `deepseek-chat`，但服务端在本轮返回的实际模型为
`deepseek-v4-flash`。因此 CT-B/CT-C 可以在同一当前模型上做严格配对；与此前
TravelPlanner 结果的数值差异不能全部归因于 benchmark，也包含模型时间版本变化。

## 下一步

冻结 CT-B 结果，不修改或重跑。下一步应在同一 12 条 manifest 上实现并运行
CT-C，仅增加一次 Structured Planner，并重点比较：

- Delivery 与 tool-budget failure；
- tool calls、tokens 和延迟；
- blueprint constraint coverage；
- blueprint 与 Executor 行程的一致性；
- environment/logical micro 与 All Pass；
- human split 的自然语言硬约束与软偏好维护。
