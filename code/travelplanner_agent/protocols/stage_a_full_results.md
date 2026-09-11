# Stage A — full validation results

Date: 2026-09-04 (Asia/Shanghai)

Protocol: official-style sole-planning with frozen Direct strategy
`direct-v1.1-frozen`, `deepseek-chat`, temperature 0, one planning-model call per
semantic attempt, complete official reference information, no autonomous tool
use or repair. This is not a query-only condition. Validation #1 is disclosed as
a development smoke case. Validation #162
was superseded once because the repository example query said `allow parties`
while the canonical Hugging Face row said `allow smoking`; only the canonical
input is included in results.

## Official 180-query result

| Metric | Result |
|---|---:|
| Delivery Rate | 95.00% |
| Commonsense Constraint Micro Pass Rate | 79.72% |
| Commonsense Constraint Macro Pass Rate | 25.00% |
| Hard Constraint Micro Pass Rate | 69.52% |
| Hard Constraint Macro Pass Rate | 53.89% |
| Final Pass Rate | 13.89% (25/180) |

The official aggregate evaluator returned exactly the same six values as the
local per-query aggregation (`cross_check_pass: true`). There were 171 delivered
plans, eight model-format non-deliveries, and one API-blocked non-delivery after
the frozen retry limit.

## Breakdown

| Group | Delivery | Commonsense macro | Hard macro | Final pass |
|---|---:|---:|---:|---:|
| Easy | 93.33% | 26.67% | 71.67% | 20.00% |
| Medium | 96.67% | 23.33% | 55.00% | 10.00% |
| Hard | 95.00% | 25.00% | 35.00% | 11.67% |
| 3 days | 98.33% | 46.67% | 45.00% | 25.00% |
| 5 days | 95.00% | 20.00% | 66.67% | 13.33% |
| 7 days | 91.67% | 8.33% | 50.00% | 3.33% |

Dominant failure counts are minimum nights (79), restaurant diversity (64),
transportation consistency (44), budget (41), room/house rule (14), incomplete
information (13), route/current-city (11), sandbox entities (9), cuisine (4),
and room type (1). Counts overlap because one plan can fail multiple checks.

Total recorded usage for selected runs: 1,838,964 prompt tokens, 121,981
completion tokens, 1,960,945 total tokens. Mean model latency was 4.68 seconds.

Sensitivity analysis excluding development-smoke validation #1: delivery
94.97%, commonsense micro 79.68%, commonsense macro 25.14%, hard micro 69.45%,
hard macro 53.63%, and Final Pass 13.97%. The negligible difference from the
180-query metrics indicates that #1 does not drive the conclusion.

## Research interpretation

- Direct sole-planning over complete supplied evidence is viable but far from
  constraint reliable: only 25 of 180 plans pass every applicable check.
- Performance degrades strongly with horizon: Final Pass falls from 25.00% at
  three days to 3.33% at seven days.
- The largest bottlenecks are not entity availability but coordinating lodging,
  meal diversity, transportation, and budget across the whole itinerary.
- These results form the frozen A sole-planning baseline; the Direct prompt must
  not be tuned further on validation. A future tool-mediated B is a comparison of
  benchmark operating modes, while causal component comparisons should be made
  among systems sharing B's two-stage information condition.
