# TravelPlanner A/B/C/D 汇总与 Failure Analysis

## 结论摘要

四个正式实验均已冻结，各包含 180 条 validation，官方与本地评测完全一致。A/B/C/D 的 Delivery 分别为 95.00%、35.00%、40.00%、41.67%；Final Pass 分别为 13.89%、15.56%、16.11%、16.11%。

结果不支持“增加更多 Agent 组件会稳定提高效果”。A 表明 oracle 信息下模型能高概率交付，但全局约束满足仍弱；B 暴露自主信息获取和 Agent 控制的巨大系统成本；C 的显式 Planner 带来小幅效率与 Delivery 改善；D 的一次 Verifier/Replan 增加 1,263,248 Token，却没有净增 Final Pass。

## 三条机制链

### A → B：sole-planning 到 two-stage system gap

A/B 同时改变信息来源和信息获取责任，不能解释为工具的单变量因果效果。Delivery 从 95.00% 降至 35.00%，而 Token 从 1,960,945 增至 10,375,639。Final Pass 仅从 13.89% 到 15.56%，说明端到端自主检索的主要影响是成本和 non-delivery，而非稳定提升规划正确性。

### B → C：Explicit Planner

C 将 Delivery 提升至 40.00%，Final Pass 提升 0.56 个百分点，同时节省 300,056 Token 和每样本 1.60 次工具调用。Planner 对检索失焦和部分 Agent 控制有帮助，但没有解决 5/7 天长程一致性。

### C → D：Verifier + Single Replan

D 将 Delivery 提升 1.67 个百分点，Final Pass 保持 16.11%，并增加 1,263,248 Token。C fail→D pass 与 C pass→D fail 均为 17，McNemar p=1.0，bootstrap 95% CI 为 [−6.11,+6.11] 个百分点。由于 D 独立重跑 C 上游，这些转移同时包含上游非确定性，不能全部归因于修复机制。

## Failure analysis

统一 taxonomy 只用于跨阶段汇总，原始 failure flags 和 evaluator constraint 均保留。最重要的发现是 failure 的位置发生了变化：A 主要是已经交付计划中的约束错误；B/C/D 则首先受到 Agent-control/non-delivery 限制。D 中 61 条没有候选，Verifier 无法介入；119 个候选触发 119 次验证，46 次 Replan 仅产生 16 个合法结果和 4 个 post-hoc repair success。

预算、minimum nights、路线/交通、餐厅多样性仍是交付计划中的主要错误。单次 LLM Verifier 读取完整 evidence catalog 成本高且自身存在格式、引用和判断失败。因此下一步若继续研究，应建立独立条件测试结构化状态、确定性 constraint checker 或 targeted replan，而不能修改已冻结 D。

## 有效性边界

- A/B 是信息条件和系统责任的整体差距，不是工具因果效应。
- C/D 独立重跑上游，逐样本转移包含模型/API 非确定性。
- validation #1 曾用于格式开发；排除后各阶段结论不变。
- 代表案例采用固定规则抽取，仅用于解释，不替代总体统计。

## 产物索引

- `analysis/freeze_manifest.json`：冻结协议与输入哈希。
- `analysis/abcd_main_metrics.csv`：四阶段主表。
- `analysis/paired_statistics.csv`：配对检验和置信区间。
- `analysis/failure_taxonomy.csv`：统一失败类别。
- `analysis/representative_cases.json`：确定性案例集。
- `analysis/figures/`：10 张 SVG、高清 PNG、数据表和图注。
