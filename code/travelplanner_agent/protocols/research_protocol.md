# TravelPlanner research protocol and terminology

## Information conditions

- **Sole-planning / oracle-reference condition:** the model receives the query
  plus complete aligned official reference information. Information collection is
  removed so the experiment focuses on planning over supplied evidence.
- **Tool-mediated / two-stage condition:** the agent starts from the query and
  must collect environment information through official tools before producing a
  plan.
- **Query-only closed-book condition:** the model receives neither reference
  information nor tools. This condition is not currently planned and must not be
  called Stage A.

## Current stages

- **Stage A — Sole-planning, Direct strategy:** complete official reference
  information, one planning-model call, structured itinerary output, no tools,
  repair, verifier, reflection, or multi-agent system. The 180-query result is
  complete and frozen.
- **Stage B — complete and frozen:** continuous autonomous tool interaction
  followed by a Direct final plan from the same model. Train development, the
  matched 18-query pilot, and all 180 validation samples are complete under
  `two-stage-react-v1.3` and `evidence-audit-v1.1`.
- **Stage C — complete and frozen:** B's information condition and execution
  limits plus one pre-tool structured global Planner call. Train development,
  the matched pilot, 180-query validation, official aggregation, and B/C paired
  report are complete under `explicit-planner-v1.0`.
- **Stage D — complete and frozen:** C's chain plus one Verifier for every final
  response and at most one evidence-grounded no-tool Replan. All 180 validation
  samples, official aggregation, and paired C/D analysis are complete under
  `verifier-v1.2` and `single-replan-v1.0`.

## Frozen full-experiment results

- A (`stage-a-full-v1`): 95.00% delivery and 13.89% Final Pass.
- B (`stage-b-full-v1`): 35.00% delivery and 15.56% Final Pass.
- C (`stage-c-full-v1`): 40.00% delivery and 16.11% Final Pass.
- D (`stage-d-full-v1`): 41.67% delivery and 16.11% Final Pass.
- Paired transitions: 22 A-fail/B-pass, 19 A-pass/B-fail, 6 both-pass, and
  133 both-fail.

The small +1.67-point Final Pass difference must be read alongside the 60-point
delivery loss, much higher cost, and sharp horizon degradation. It does not show
that tools caused a net improvement.

B/C adds the explicit Planner under the same two-stage condition. C improves
Delivery by 5.00 points and Final Pass by 0.56 points, saves 300,056 tokens and
1.60 tool calls per sample, but adds 0.83 seconds mean latency. Its effect is
small and heterogeneous rather than a general solution to long-horizon planning.

C/D adds one Verifier and at most one no-tool Replan, but independently reruns the
full upstream C chain. D gains 1.67 delivery points and small micro/macro constraint
improvements, while Final Pass is unchanged and token use rises by 1,263,248. The
paired result has 17 gains and 17 regressions (McNemar p=1.0); upstream rerun
nondeterminism means individual transitions are not pure repair effects.

## Interpretation rule

A/B changes both the source of information and responsibility for obtaining it:
A receives complete oracle evidence; B must retrieve its own evidence. Therefore
A/B can measure the end-to-end gap between sole-planning and two-stage operation,
but cannot isolate the causal benefit of tool use alone. Within-regime comparisons
must hold the information condition fixed.

For B/C, the intended added mechanism is one explicit Planner call. C keeps B's
full observations and 30-tool-call ceiling; it does not use Top-N, observation
compression, scripted checklist execution, verifier, or repair. Any reduction in
tokens or calls must arise from changed model behavior induced by the blueprint.
