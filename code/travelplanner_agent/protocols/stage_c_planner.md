# Stage C — Explicit Planner + ReAct

Status: **complete and frozen**. Train development, matched validation pilot,
full 180-query validation, official aggregation, and B/C paired comparison have
all completed.

## Controlled mechanism

Stage C starts from the same query-only input as B and uses the same
`deepseek-chat`, temperature 0, official tools, complete tool observations,
30-call budget, context limit, final JSON contract, and evaluator. It adds one
1,500-token maximum Planner call before tool interaction. The Planner receives no
reference information and cannot use tools or name evidence-dependent entities.

The structured blueprint contains `trip_facts`, `global_route`,
`constraint_ledger`, `retrieval_checklist`, and `planning_risks`. It is guidance,
not a scripted workflow: the ReAct executor remains autonomous. A malformed
blueprint terminates as `planner_invalid`; no repair LLM is used.

## Engineering evidence

The fixed nine-cell train experiment `stage-c-train-dev-v1` reached 9/9 explicit
terminal states. All nine Planner outputs passed schema validation and all runs
contain a blueprint, Planner audit, evidence audit, and trajectory. Two samples
delivered evaluator-ready JSON; seven retained model failures (four `max_steps`
and three malformed final responses). These failures did not trigger prompt
tuning because the engineering gate tests observability and reproducibility.

The matched `stage-c-pilot-v1` completed all 18 validation samples: six delivered,
12 non-delivered, and three Final Passes. Metrics were 33.33% Delivery, 29.86%
commonsense micro, 22.22% commonsense macro, 16.67% hard micro, 22.22% hard macro,
and 16.67% Final Pass. Mean model calls were 6.33 and mean tool calls 18.11.

Relative to the frozen B pilot, C changed Delivery by -5.56 points and Final Pass
by +5.56 points while using 449,941 fewer tokens, 2.67 fewer tool calls per
sample, and 11.94 fewer seconds per sample. This small pilot is not a research
conclusion and was not used to alter the frozen protocol.

## Audits and interpretation

Each run stores `planner_audit.json` with Planner response/usage/latency, query
constraint coverage, blueprint/final-route consistency, checklist completion,
and unplanned-call rate. C's mutually prioritized failure view distinguishes
Planner non-delivery, Agent-control non-delivery, tool failure, insufficient
evidence, blueprint deviation, grounding failure, planning-constraint failure,
and success. The existing B evidence audit is retained unchanged alongside it.

## Full result

`stage-c-full-v1` delivered 72/180 plans and passed 29/180 completely: 40.00%
Delivery and 16.11% Final Pass. The official aggregate evaluator matches local
aggregation exactly. Relative to B, C raises Delivery by 5.00 points and Final
Pass by 0.56 points while saving 300,056 total tokens and 1.60 tool calls per
sample. Mean latency increases by 0.83 seconds because of the Planner call.

The improvement is concentrated in three-day, medium, and hard queries; C does
not improve five- or seven-day Final Pass. Checklist completion is only 59.49%
and the unplanned-call rate is 52.81%, showing that a valid blueprint does not
ensure faithful execution. See `stage_c_full_results.md` for the full tables,
failure analysis, costs, and interpretation.
