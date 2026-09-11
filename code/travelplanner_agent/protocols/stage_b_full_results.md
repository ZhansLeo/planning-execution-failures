# Stage B — full validation and Stage A/B system-gap results

Date: 2026-09-05 (Asia/Shanghai)

Protocol: autonomous tool-mediated two-stage baseline `two-stage-react-v1.3`,
`deepseek-chat`, temperature 0, six official read-only tools, maximum 30 tool
calls, and evidence audit `evidence-audit-v1.1`. The model starts from the query;
official reference information is excluded from model context and is used only
for post-hoc oracle-alignment diagnostics. There is no explicit Planner,
Verifier, Replan, Memory, Reflection, repair LLM, or multi-agent component.

## Official 180-query result

| Metric | Result |
|---|---:|
| Delivery Rate | 35.00% (63/180) |
| Commonsense Constraint Micro Pass Rate | 32.15% |
| Commonsense Constraint Macro Pass Rate | 20.56% |
| Hard Constraint Micro Pass Rate | 24.76% |
| Hard Constraint Macro Pass Rate | 22.78% |
| Final Pass Rate | 15.56% (28/180) |

All 180 samples have one terminal result, with no duplicates or omissions. The
official aggregate evaluator returned exactly the same six values as local
per-sample aggregation (`cross_check_pass: true`). Sensitivity analysis excluding
validation #1 gives 34.64% delivery and 15.08% Final Pass, so the disclosed smoke
sample does not drive the overall result.

## Difficulty and horizon breakdown

| Group | Delivery | Commonsense macro | Hard macro | Final Pass |
|---|---:|---:|---:|---:|
| Easy | 41.67% | 30.00% | 33.33% | 26.67% |
| Medium | 30.00% | 15.00% | 16.67% | 11.67% |
| Hard | 33.33% | 16.67% | 18.33% | 8.33% |
| 3 days | 68.33% | 46.67% | 46.67% | 33.33% |
| 5 days | 25.00% | 11.67% | 15.00% | 10.00% |
| 7 days | 11.67% | 3.33% | 6.67% | 3.33% |

### PPT-ready 3 x 3 Final Pass table

| Difficulty / days | 3 days | 5 days | 7 days |
|---|---:|---:|---:|
| Easy | 55.00% | 20.00% | 5.00% |
| Medium | 25.00% | 10.00% | 0.00% |
| Hard | 20.00% | 0.00% | 5.00% |

The strongest pattern is horizon collapse. Most 7-day attempts do not reach a
valid evaluator-ready plan, so long-horizon agent control is at least as important
as constraint satisfaction within delivered plans.

## Acquisition, grounding, and planning funnel

| Primary outcome | Samples |
|---|---:|
| Success | 28 |
| Planning constraint failure | 13 |
| Evidence utilization / grounding failure | 5 |
| Evidence insufficient for chosen plan | 16 |
| Tool execution failure | 1 |
| Non-delivery / agent control | 117 |

Mean chosen-route coverage is 78.96%, mean plan-evidence grounding is 99.18%, and
diagnostic oracle alignment is 36.91%. Conditional planning success among the 41
samples with sufficient, grounded evidence is 68.29%. These diagnostics suggest
that B's dominant failure is completing and controlling the tool loop, followed
by acquiring enough route-specific evidence; unsupported entity hallucination is
not the main bottleneck once a plan is delivered.

The 117 non-deliveries include 61 `max_steps` terminations and one repeated-call
termination; 118 traces reached a final response, but 55 of those were malformed
or otherwise failed the strict output contract. Constraint failures among the 63
delivered plans overlap: restaurant diversity 16, route/current-city 11, budget
9, incomplete information 7, sandbox entities 5, and one each for transportation,
minimum nights, and room type.

## Cost and interaction profile

| Quantity | Stage B |
|---|---:|
| Prompt tokens | 9,338,555 |
| Completion tokens | 1,037,084 |
| Total tokens | 10,375,639 |
| Mean latency | 38.64 s/sample |
| Mean model calls | 6.31/sample |
| Mean tool calls | 19.43/sample |
| Tool-call p50 / p90 | 23 / 30 |

The agent issued 3,498 tool calls: 1,772 flight, 464 accommodation, 352
restaurant, 345 attraction, 329 distance-matrix, and 236 city searches. There
were 875 empty results and only one recorded tool error, indicating that model
search choices and available matches—not infrastructure exceptions—caused most
acquisition failures.

## Stage A/B paired system gap

| Metric | Stage A | Stage B | B - A |
|---|---:|---:|---:|
| Delivery | 95.00% | 35.00% | -60.00 pp |
| Commonsense micro | 79.72% | 32.15% | -47.57 pp |
| Commonsense macro | 25.00% | 20.56% | -4.44 pp |
| Hard micro | 69.52% | 24.76% | -44.76 pp |
| Hard macro | 53.89% | 22.78% | -31.11 pp |
| Final Pass | 13.89% | 15.56% | +1.67 pp |

Paired transitions are 22 `A fail -> B pass`, 19 `A pass -> B fail`, 6 both-pass,
and 133 both-fail. B improves Final Pass mainly on short/easy queries: relative to
A, it gains 20 points in easy 3-day queries and 8.33 points across all 3-day
queries, while it loses 3.33 points on 5-day queries and is unchanged on 7-day
queries. Total token use rises by 8,414,694 and mean latency by 33.96 seconds.

This is a **sole-planning to tool-mediated two-stage system gap**, not a tools-only
causal ablation. A supplies complete oracle evidence in context; B removes that
evidence and makes the Agent responsible for retrieval, evidence selection, loop
control, and final planning. The near-equal Final Pass rates therefore conceal a
major reliability and cost difference.

## Research interpretation and next hypothesis

- B can outperform A on some short cases because tool retrieval supplies highly
  grounded entities and transportation details, but this gain is unstable.
- Long-horizon degradation is dominated by non-delivery and search-loop control,
  not solely by evaluator constraints after a valid plan exists.
- High grounding with low oracle alignment indicates that the model usually uses
  what it found, but often searches a narrow or non-oracle slice of the available
  environment.
- Stage C should keep B's query-only input, tools, audit, evaluator, and model
  fixed while adding an explicit global planning mechanism. The key test is
  whether it reduces `max_steps`, incomplete evidence, and 5/7-day failures at an
  acceptable token/tool-call cost.

Machine-readable evidence is retained in `runs/experiments/stage-b-full-v1/`:
`summary.json`, `per_sample.json`, `submission.jsonl`,
`official_aggregate.json`, and `stage_a_b_comparison.json`.
