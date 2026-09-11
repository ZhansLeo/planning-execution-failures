# Stage D full results — Verifier + Single Replan

## Result

`stage-d-full-v1` completed all 180 validation queries. The official aggregate
evaluator exactly matches the local per-sample aggregation.

| Metric | Stage C | Stage D | D − C |
|---|---:|---:|---:|
| Delivery Rate | 40.00% | 41.67% | +1.67 pp |
| Commonsense micro | 36.88% | 37.92% | +1.04 pp |
| Commonsense macro | 21.67% | 22.22% | +0.56 pp |
| Hard micro | 31.67% | 32.62% | +0.95 pp |
| Hard macro | 24.44% | 25.56% | +1.11 pp |
| Final Pass | 16.11% | 16.11% | 0.00 pp |
| Total tokens | 10,075,583 | 11,338,831 | +1,263,248 |
| Mean latency | 39.47 s | 44.32 s | +4.85 s |
| Mean tool calls | 17.83 | 17.58 | −0.25 |

Excluding development smoke validation #1, D has 41.90% Delivery and 16.20%
Final Pass. The conclusion is unchanged.

## Paired C/D analysis

- C fail → D pass: 17
- C pass → D fail: 17
- both pass: 12
- both fail: 134
- Exact two-sided McNemar p-value: 1.0
- Paired bootstrap 95% CI for Final Pass difference: [−6.11, +6.11] percentage points

Therefore D does not produce a stable Final Pass improvement. The equal number of
positive and negative transitions is important: because the formal D protocol
independently reruns the full C chain, these paired changes include upstream model/API
nondeterminism as well as the downstream Verifier/Replan mechanism. They must not be
interpreted as 17 verified repairs caused solely by D.

The horizon pattern is heterogeneous. D changes Final Pass by −5.00 points on 3-day
queries, +3.33 points on 5-day queries, and +1.67 points on 7-day queries. These small
cell-level differences are exploratory and not statistically decisive.

## Verifier and repair behavior

- Upstream final responses: 119; upstream no-candidate failures: 61
  (`max_steps` 56, repeated calls 5).
- Verifier calls: 119.
- Replan calls: 46 (25.56% of all samples).
- Valid Replans: 16/46 (34.78%).
- Post-hoc `repair_success`: 4 samples.
- Deterministic original-candidate fallbacks: 59 samples.
- Verifier tokens: 2,001,770; Replan tokens: 605,963.

The audit also shows a major mechanism weakness: many Verifier responses were malformed,
unsupported, or otherwise rejected by the strict contract, and malformed candidates were
often not recoverable with one no-tool Replan. The verifier confusion table is incomplete
for unparseable candidates and invalid verifier reports, so its recorded TP/FP counts are
diagnostic rather than a full classification metric.

## Interpretation

Stage D is a **mechanism failure at the overall Final Pass level**. It slightly improves
Delivery and aggregate constraint rates, but adds 1.26 million tokens and 4.85 seconds per
sample on average without any net Final Pass gain. There is therefore no finite “token cost
per net new Final Pass”; the denominator is zero.

The result narrows the next research question. The dominant unresolved problem remains
upstream Agent control and evidence acquisition (61 samples never produced a candidate),
which a downstream verifier cannot address. Among candidates, a single unrestricted LLM
verifier over a large evidence catalog is itself brittle and expensive. A future extension
should be a separately named condition—not a silent modification of D—testing deterministic
constraint checking, compact structured state, or targeted retrieval/replan.

## Reproducibility artifacts

- `runs/experiments/stage-d-full-v1/manifest.json`
- `runs/experiments/stage-d-full-v1/submission.jsonl`
- `runs/experiments/stage-d-full-v1/summary.json`
- `runs/experiments/stage-d-full-v1/official_aggregate.json`
- `runs/experiments/stage-d-full-v1/stage_c_d_comparison.json`
- Per-run candidate, trajectory, evidence catalog, verifier report, optional Replan,
  repair decision, evaluator output, and audits.
