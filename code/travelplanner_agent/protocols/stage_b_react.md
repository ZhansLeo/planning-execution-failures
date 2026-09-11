# Stage B — autonomous information acquisition / Two-stage ReAct

Status: **full 180-query validation experiment complete**. Prompt v1.3 and audit
v1.1 are frozen. No validation result was used to modify the protocol.

## Research variable

The candidate keeps the Stage-A model, temperature, output contract, validation
set, and evaluator, but it does not differ from A only by adding tools. It removes
the complete oracle reference input used by sole-planning and transfers
responsibility for information acquisition to an agent using six official tools.
It therefore represents TravelPlanner's tool-mediated/two-stage information
condition and must be interpreted as a system-level comparison with A.

The legacy TravelPlanner agent is not reused because it couples retrieval to a
Notebook and a separate Planner LLM. Those components would confound the planned
B -> C comparison. Stage B therefore uses one DeepSeek model for tool selection
and final JSON, with no Planner, verifier, repair, memory, reflection, or multi-agent
component.

## Pre-pilot candidate protocol

- Prompt version: `two-stage-react-v1.3`
- Temperature: `0`
- Native structured function calling; multiple calls from one model turn are
  executed sequentially in returned order and each counts toward the 30-call budget
- The one-call-per-turn v1.0/v1.1 candidates were rejected because DeepSeek
  returned parallel calls even when `parallel_tool_calls=false`; those engineering
  failures remain in `stage-b-train-dev-v1` and `stage-b-train-dev-v2`
- The v1.2 train trace redundantly rediscovered already specified cities and then
  repeated the same successful city query; v1.3 adds general tool-use guidance to
  consume successful observations and skip city discovery when exact cities are given
- The first v1.3 trace exposed an audit-only bug that removed a legitimate trailing
  period from an accommodation name; audit v1.1 preserves exact entity names and
  the affected v4 development run is not mixed into the replacement experiment
- Maximum tool calls: `30`
- Three identical consecutive calls terminate the sample
- Complete official query results; deterministic JSON serialization; no Top-N
- Estimated input-context guard: `56,000` tokens; output reservation: `8,000`
- Only transport/API failures are experiment-level retryable
- Train-only engineering smoke tests, then the same 18 validation pilot indices as A
- Post-hoc audit version: `evidence-audit-v1.1`; oracle reference never enters model context

The implementation creates an evidence audit for tool execution, chosen-route
coverage, plan grounding, diagnostic oracle alignment, official sandbox validity,
and one primary failure category. Oracle-route divergence is never treated as an
official correctness failure.

Run the fixed nine-cell train development suite before validation. Once train
engineering succeeds, launch the existing 18-query validation pilot and freeze
all protocol hashes. Any later protocol change requires a new experiment ID.

## Commands

Commands in `README.md` execute train development, pilot, full validation, and the
sole-planning-to-two-stage system-gap report. A/B results must not be described as
the causal effect of tools alone.

## Train engineering result

Experiment `stage-b-train-dev-v5` completed all nine fixed
difficulty-by-horizon cells. Three runs produced evaluator-ready JSON and six had
explicit model/agent terminal failures: three `max_steps`, two invalid final
responses, and one repeated tool call. All nine retained trajectories and evidence
audits; total usage was 64 model calls and 187 tool calls. These failures are not
prompt-tuned away because the train gate checks infrastructure and observability,
not baseline quality.

Earlier `v1`–`v4` directories are retained as superseded engineering evidence for
parallel-call handling, repeated city discovery, and the trailing-period audit
bug. They must not be aggregated with `v5` or the validation pilot.

## Validation pilot result

Experiment `stage-b-pilot-v1` completed all 18 fixed Stage-A-matched pilot
indices with no API-blocked sample. Seven outputs were evaluator-ready and eleven
were retained Agent/model failures: six `max_steps`, one repeated-tool loop, and
four invalid final responses. Every sample has a trajectory and evidence audit.

- Delivery: 38.89%
- Commonsense micro / macro: 37.50% / 27.78%
- Hard micro / macro: 28.57% / 16.67%
- Final Pass: 11.11% (2/18)
- Mean model calls / tool calls: 7.17 / 20.78
- Recorded tokens: 1,377,712

The low delivery rate was treated as a baseline result rather than an
infrastructure blocker. The same frozen protocol then ran all 180 validation
queries without prompt or tool-policy tuning.

## Full validation result

Experiment `stage-b-full-v1` reached explicit terminal outcomes for all 180
samples: 63 evaluator-ready plans and 117 invalid/non-delivered plans. The
official aggregate evaluator and local per-sample aggregation agree exactly.

- Delivery: 35.00%
- Commonsense micro / macro: 32.15% / 20.56%
- Hard micro / macro: 24.76% / 22.78%
- Final Pass: 15.56% (28/180)
- Mean model calls / tool calls: 6.31 / 19.43
- Recorded tokens: 10,375,639
- Mean latency: 38.64 seconds

The primary acquisition funnel contains 28 successes, 13 planning-constraint
failures, 117 non-delivery/agent-control failures, one tool-execution failure, 16
insufficient-evidence failures, and five evidence-utilization/grounding failures.
Final Pass falls from 33.33% on 3-day queries to 10.00% on 5-day and 3.33% on
7-day queries. The complete breakdown and paired interpretation are in
`stage_b_full_results.md`.
