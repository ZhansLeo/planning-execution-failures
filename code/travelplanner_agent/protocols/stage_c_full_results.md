# Stage C — full validation and Stage B/C mechanism comparison

Date: 2026-09-05 (Asia/Shanghai)

Protocol: `C_explicit_planner_react`, Planner prompt `explicit-planner-v1.0`,
`deepseek-chat`, temperature 0. Stage C preserves Stage B's query-only input,
six official tools, full observations, 30-tool-call ceiling, context limit,
final-output contract, and evaluator. Its intended added mechanism is one
pre-tool structured global Planner call, capped at 1,500 output tokens. There is
no verifier, replan, repair, compression, scripted retrieval, or multi-agent
component.

## Official 180-query result

| Metric | Stage C |
|---|---:|
| Delivery Rate | 40.00% (72/180) |
| Commonsense Constraint Micro Pass Rate | 36.88% |
| Commonsense Constraint Macro Pass Rate | 21.67% |
| Hard Constraint Micro Pass Rate | 31.67% |
| Hard Constraint Macro Pass Rate | 24.44% |
| Final Pass Rate | 16.11% (29/180) |

All 180 samples have explicit terminal outcomes. The submission contains 180
ordered, unique rows. The official aggregate evaluator exactly matches the local
per-sample aggregation (`cross_check_pass: true`). There were 72 delivered plans
and 108 non-deliveries. One transport/API retry produced 181 recorded attempts;
only the terminal selected run contributes to results.

Sensitivity excluding validation #1: 39.66% Delivery, 36.59% commonsense micro,
21.79% commonsense macro, 31.50% hard micro, 24.02% hard macro, and 16.20% Final
Pass. Validation #1 does not determine the conclusion.

## Difficulty and horizon

| Group | Delivery | Commonsense macro | Hard macro | Final Pass |
|---|---:|---:|---:|---:|
| Easy | 36.67% | 20.00% | 25.00% | 16.67% |
| Medium | 43.33% | 21.67% | 25.00% | 16.67% |
| Hard | 40.00% | 23.33% | 23.33% | 15.00% |
| 3 days | 71.67% | 53.33% | 48.33% | 38.33% |
| 5 days | 26.67% | 10.00% | 16.67% | 8.33% |
| 7 days | 21.67% | 1.67% | 8.33% | 1.67% |

### PPT-ready 3 × 3 Final Pass table

| Difficulty / days | 3 days | 5 days | 7 days |
|---|---:|---:|---:|
| Easy | 35.00% | 15.00% | 0.00% |
| Medium | 45.00% | 5.00% | 0.00% |
| Hard | 35.00% | 5.00% | 5.00% |

Explicit planning does not solve the long-horizon problem. Final Pass remains
38.33% for three-day trips but falls to 8.33% for five days and 1.67% for seven
days.

## Planner, acquisition, and failure funnel

| Primary Stage-C outcome | Samples |
|---|---:|
| Success | 29 |
| Planning constraint failure | 12 |
| Blueprint execution deviation | 1 |
| Evidence utilization / grounding failure | 1 |
| Evidence insufficient | 29 |
| Agent-control non-delivery | 108 |

All selected Planner outputs were structurally usable; there was no terminal
`planner_invalid` sample. The Planner captured 98.70% of detected query
constraint categories, but the executor completed only 59.49% of blueprint
retrieval-checklist items on average. Moreover, 52.81% of successful tool calls
were outside the literal checklist. This shows that the blueprint was broadly
correct but only weakly controlled downstream search behavior.

The ReAct layer ended with 117 final responses, 55 `max_steps` terminations, and
eight repeated-call terminations. Compared with B, max-step failures decreased
from 61 to 55, while repeated-loop failures increased from one to eight. Mean
chosen-route evidence coverage was 77.39%, grounding was 99.37%, and oracle
alignment was 38.54%. Grounding remains strong once an answer is delivered;
information sufficiency and agent control remain the larger bottlenecks.

Overlapping constraint failures among the 72 delivered plans were restaurant
diversity 22, budget 17, route/current-city 9, incomplete information 6,
transportation 4, room type 3, sandbox validity 3, and one each for minimum
nights and house rules.

## Cost and interaction profile

| Quantity | Stage C |
|---|---:|
| Prompt tokens | 9,033,540 |
| Completion tokens | 1,042,043 |
| Total tokens | 10,075,583 |
| Planner tokens | 222,252 |
| Mean total latency | 39.47 s/sample |
| Mean Planner latency | 4.13 s/sample |
| Mean model calls | 6.68/sample |
| Mean tool calls | 17.83/sample |
| Tool-call p50 / p90 | 20 / 29 |

Although every sample adds a Planner call, the full system uses fewer tokens
than B because later execution uses fewer tool calls and less accumulated prompt
context. Planner cost is therefore more than offset by downstream savings.

## Stage B/C paired mechanism comparison

| Metric | Stage B | Stage C | C − B |
|---|---:|---:|---:|
| Delivery | 35.00% | 40.00% | +5.00 pp |
| Commonsense micro | 32.15% | 36.88% | +4.72 pp |
| Commonsense macro | 20.56% | 21.67% | +1.11 pp |
| Hard micro | 24.76% | 31.67% | +6.90 pp |
| Hard macro | 22.78% | 24.44% | +1.67 pp |
| Final Pass | 15.56% | 16.11% | +0.56 pp |
| Total tokens | 10,375,639 | 10,075,583 | −300,056 |
| Mean tool calls | 19.43 | 17.83 | −1.60 |
| Mean model calls | 6.31 | 6.68 | +0.37 |
| Mean latency | 38.64 s | 39.47 s | +0.83 s |

Paired transitions: 19 `B fail → C pass`, 18 `B pass → C fail`, 10 both-pass,
and 133 both-fail. The net gain is only one fully successful sample. In the
predefined efficiency view, C saves 300,056 tokens per net additional Final Pass,
but this ratio is unstable because its denominator is one sample.

The gain is heterogeneous. C improves Final Pass by 5 points on three-day tasks,
5 points on medium difficulty, and 6.67 points on hard difficulty. It loses 10
points on easy tasks and 1.67 points on both five- and seven-day tasks. Therefore
the result is best classified as an **efficiency success with a small overall
quality gain**, not a strong solution to long-horizon planning.

## Research conclusion

- A compact explicit blueprint can improve system completion: Delivery rises by
  nine samples and max-step failures fall by six.
- Planner overhead does not necessarily raise token cost. C saves 2.89% total
  tokens and 8.24% mean tool calls relative to B, despite adding one model call.
- Final reliability barely improves because gains and regressions occur on
  different samples. A Planner alone does not guarantee faithful execution.
- The 59.49% checklist completion and 52.81% unplanned-call rate identify the next
  mechanism question: whether a Verifier and bounded Replan can catch execution
  drift and constraint violations without erasing C's modest cost savings.
- Stage D must preserve C's information condition and frozen Planner/React
  protocol when attributing effects to verification and replanning.

Machine-readable evidence is in `runs/experiments/stage-c-full-v1/`, including
`summary.json`, `per_sample.json`, `submission.jsonl`,
`official_aggregate.json`, and `stage_b_c_comparison.json`.
