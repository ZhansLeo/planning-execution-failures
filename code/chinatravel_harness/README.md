# ChinaTravel Generalization Harness

这是官方 ChinaTravel 仓库之外的独立实验 harness，不修改其源码。ChinaTravel 在本项目中用于
TravelPlanner 机制结论的小规模跨 benchmark 泛化验证，不是第二套完整 A/B/C/D。

冻结的 CT-B / CT-C 12 条 paired pilot 均已完成：Final Response 从 4/12 增至 7/12，
但 Strict Schema Delivery 维持 4/12，All Pass 均为 0/12。CT-C 平均工具调用从 29.08
降到 23.75，平均 token 从 229,938 降到 197,205；敏感性分析表明，表面成本下降主要
由两条 zero-tool premature-stop 样本驱动，不能解释为稳定的检索效率提升。

完整报告见 [CT-C 配对 Pilot 报告](docs/ct_c_paired_pilot_report.md)，结构化比较见
`experiments/ct-pilot-v1/ct_b_c_comparison.json`。

进一步的逐样本机制拆解见 [深度失败分析](docs/ct_failure_analysis.md)。该分析发现总体成本下降
主要由两条零工具早停驱动，因此当前不直接扩展到 36 条。

最终收口材料见 [ChinaTravel 最终收口报告](docs/ct_closing_report.md)，包含 grounding audit、
四层指标、failure taxonomy、8 个案例卡、B/C paired conclusion 和 TravelPlanner cross-benchmark
对照。所有分析均为冻结结果上的只读计算。

```powershell
.\run.ps1 inspect
.\run.ps1 ct-b --split easy --uid UID
.\run.ps1 ct-c --split easy --uid UID
.\run.ps1 ct-c --split easy --uid UID --real
.\run.ps1 evaluate --run RUN_ID
.\run.ps1 pilot --baseline ct-b --resume
.\run.ps1 aggregate-pilot --baseline ct-b
.\run.ps1 dev --baseline ct-c --resume
.\run.ps1 pilot --baseline ct-c --resume
.\run.ps1 aggregate-pilot --baseline ct-c
.\run.ps1 compare-pilot
```

Required environment variables:

- `OPENAI_API_KEY` or `DEEPSEEK_API_KEY`
- `OPENAI_BASE_URL` (default `https://api.deepseek.com`)
- `MODEL_NAME` (default `deepseek-chat`)
- `CHINATRAVEL_OFFICIAL_REPO`：官方 ChinaTravel 仓库路径
- `CHINATRAVEL_DATA_ROOT`：官方中文 query CSV 所在目录
- `CHINATRAVEL_RUNS_ROOT`：可选的运行输出目录

Main-experiment prompts never receive `hard_logic`, `hard_logic_py`, or
`hard_logic_nl`. Those fields are retained only inside the evaluator process.

## 协议边界

CT-B 已冻结，不再修改或重跑。CT-C 只比 CT-B 增加一次无工具 Structured Planner；
Executor、18 个官方工具、30-call budget、完整 observation、JSON finalization 和 evaluator
均保持一致。隐藏 oracle 字段不进入 Planner、Executor、trajectory 或 tool observation，
仅在运行结束后由 evaluator / oracle audit 使用。

早期 smoke 和冻结过程见 `docs/first_smoke_report.md`、`docs/ct_b_pilot_report.md`。
