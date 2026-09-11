# Stage D — Verifier + Single Replan

## Research question

Under the same query-only information condition, explicit Planner, six official tools,
complete observations, and ReAct execution used by Stage C, can one explicit verification
and at most one evidence-grounded, no-tool repair improve Delivery and Final Pass at an
acceptable token and latency cost?

Stage D is a C/D mechanism comparison. Its only intended additions are one Verifier call
for every upstream final response and, when the Verifier returns `repair`, one Replan call.
The Planner and tool loop are independently rerun for every D sample. D does not reuse C
outputs, query the official evaluator, expose oracle reference information, add retrieval,
or select between candidates by score.

## Frozen execution contract

- Model: `deepseek-chat`, temperature 0 for Planner, ReAct, Verifier, and Replan.
- C execution remains unchanged: six official tools, full observations, 30 tool calls,
  three-identical-call termination, 56k input threshold, and 8k final-output allowance.
- A final response—parseable or malformed—receives exactly one Verifier call.
- An upstream termination without a candidate (`max_steps`, repeated call, or context
  limit) does not receive a Verifier.
- Verifier output is a strict `pass|repair` report with typed issues and stable evidence IDs.
- Only `repair` triggers one Replan. Replan has no tools and receives only cited evidence
  plus evidence rows already used by the original candidate.
- Deterministic selection is: valid Replan, else valid original candidate, else empty plan.
- Neither official reference information nor evaluator results enter any model context.

The Verifier output limit is 2,500 tokens and the Replan output limit is 8,000 tokens.
Protocol hashes, prompts, evidence catalog format, audit versions, and fallback policy are
recorded in each manifest and run directory.

## Commands

```powershell
.\run.ps1 verifier-replan -Split train -Index 1
.\run.ps1 dev -Baseline verifier-replan -ExperimentId stage-d-train-dev-v3
.\run.ps1 pilot -Baseline verifier-replan -ExperimentId stage-d-pilot-v1
.\run.ps1 batch -Baseline verifier-replan -ExperimentId stage-d-full-v1 -Resume
.\run.ps1 compare `
  -StageCDir "$PWD/runs/experiments/stage-c-full-v1" `
  -StageDDir "$PWD/runs/experiments/stage-d-full-v1"
```

## Interpretation

The primary comparison is paired C/D. We report Delivery, constraint micro/macro pass,
Final Pass, C-fail→D-pass and C-pass→D-fail, costs, exact McNemar inference, and a paired
bootstrap confidence interval. Verifier accuracy and repair effects are computed only as
post-hoc diagnostics; evaluator outcomes never control generation or fallback.
