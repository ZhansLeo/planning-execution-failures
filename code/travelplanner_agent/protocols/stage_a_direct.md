# Stage A — official-style sole-planning, Direct strategy

Date: 2026-09-04 (Asia/Shanghai)

## Research question

How well can DeepSeek perform TravelPlanner's sole-planning task when given one
query and its complete official reference information, using the Direct strategy
without tools or an agent loop?

Stage A is not query-only and not closed-book. “Direct” means the supplied
evidence is converted into a plan in one model call; it does not mean the model
must plan without TravelPlanner environment information.

Controlled configuration:

| Component | Stage A |
|---|---:|
| Search tools / environment interaction | No |
| ReAct | No |
| Explicit global planner | No |
| Verifier / replan | No |
| Memory / reflection / multi-agent | No |
| Planning-model calls per run | 1 |

Model: `deepseek-chat`, temperature 0, OpenAI-compatible JSON-object response.
Input: official validation index 1 and aligned
`database/validation_ref_info.jsonl` row 1. The official example itinerary is
loaded by the local adapter for phase-1 evidence but is deliberately excluded
from the Direct task and prompt.

## Prompt-development attempt

Run `20260904T025104391520Z_deepseek-chat_validation_001` made one successful
model call (6,109 tokens, 3.45 s). Its JSON schema and entity membership passed,
but manual source comparison found that it was not evaluator-ready: it used
`Flight F...` instead of `Flight Number: F...`, omitted `from` in travel-day
`current_city`, and omitted city suffixes on named venues. This output is retained
as a failure case; it was not repaired or submitted.

The prompt and deterministic checker were then strengthened using only the
official evaluator's general literal format rules, not query-specific answers.

## Accepted Stage-A run

Run `20260904T025346136616Z_deepseek-chat_validation_001` made exactly one model
call and completed:

- latency: 3.97 s
- prompt tokens: 5,813
- completion tokens: 471
- total tokens: 6,284
- JSON schema: pass
- official literal evaluator format: pass
- all named entities present in the supplied official reference row: pass

The evaluator-ready row is stored in that run's `submission.jsonl`, alongside
the complete prompt, raw response, parsed response, validation, configuration,
usage, and request status. No key is persisted.

## Early failure-analysis note

The selected accommodation has a three-night minimum while the itinerary lists
it on two travel nights. The restored official evaluator confirms the failure:

- Commonsense: 7/8 checks pass; `is_valid_accommodation` fails with the official
  minimum-nights message.
- Hard constraints: budget passes; the four optional easy-query constraints are
  not applicable.
- Commonsense pass: false.
- Hard pass: true.
- Final pass: false.

This legitimate Direct-baseline planning failure was not repaired. The result is
stored in the accepted run's `official_evaluation.json`. It is a single-query
official-constraint result, not the 180-query aggregate metric.

## PPT-ready stage card

- Purpose: measure sole-planning ability with complete official information but
  without autonomous information collection.
- Flow: Query + Reference Information → DeepSeek → JSON Itinerary.
- First technical finding: JSON validity alone is weaker than compatibility with
  the benchmark's literal parser contract.
- First planning finding: a reference-grounded plan can still violate a global
  constraint such as minimum stay.
- Next system comparison: a future Stage B may replace oracle reference input
  with autonomous official-tool collection. This changes the information regime,
  so A/B must not be described as a tools-only causal ablation.
