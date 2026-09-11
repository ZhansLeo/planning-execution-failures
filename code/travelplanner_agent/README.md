# TravelPlanner Agent Research Harness

This independent implementation lives at
`agent_baseline`, isolated
inside the official checkout root. It references official code and data by path;
it does not modify, vendor, or overwrite official files.

The harness now supports the complete A/B research path:

`sole-planning with supplied oracle evidence (A) -> autonomous information acquisition and planning (B)`

Both frozen 180-query validation experiments are complete. Their ordered JSONL,
per-sample evaluations, official aggregate output, trajectories, evidence audits,
and A/B paired comparison are retained under `runs/experiments/`.

## Layout

```text
travelplanner-agent/
  src/travelplanner_agent/
    __main__.py            unified CLI
    cli.py                 phase-1 orchestration and health checks
    official_adapter.py    path-based official-code/data adapter
    baselines.py           common interface and Stage-A sole-planning strategy
    direct_runner.py       immutable run capture and validation
  tests/test_direct.py     offline contract and failure tests
  artifacts/               reproducible JSON evidence (generated)
  experiments/phase1.md    findings, source evidence, and blockers
  .env.example             key-safe DeepSeek-compatible configuration
  run.ps1                  unified entry using Conda `llm-learning`
  pyproject.toml
```

## Run

No API key is needed for phase 1. From this directory, use the existing Conda
environment `llm-learning` (the source code remains here, not in that environment):

```powershell
.\run.ps1 phase1
```

Individual checks use `inspect`, `sample`, `tool`, or `contract` in place of
`phase1`, for example `.\run.ps1 inspect`. The script sets `PYTHONPATH` only for
the child process, so no package installation and no write to `llm-learning` is
needed. Generated evidence is intentionally ignored by Git; `.gitkeep` preserves
the directory.

## Stage A: official-style sole-planning with Direct strategy

Stage A is **not** a query-only or closed-book LLM baseline. It follows
TravelPlanner's sole-planning setting: the model receives the user query and the
aligned, complete official reference information, so information collection is
removed and the experiment focuses on planning over supplied evidence.

Copy `.env.example` to `.env` and fill a key only when a model run is required.
The defaults use DeepSeek's OpenAI-compatible endpoint. Never commit `.env`.

```powershell
.\run.ps1 direct -Index 1
```

The Direct strategy uses one planning-model call and must return evaluator JSON
directly. “One LLM call” describes the planning strategy, not the information
condition: every run still includes the official reference information. There
are no tools, ReAct steps, parser-model calls, repair calls, verifier, memory,
reflection, or multi-agent components. Use `-Start 1 -End 5` for a later explicit
batch. Each attempt gets a new ignored
`runs/<timestamp>_<model>_<split>_<index>/` directory; failed calls and invalid
outputs are retained rather than overwritten.

Evaluate one completed run with the unmodified official constraint functions:

```powershell
.\run.ps1 evaluate -RunDir "path/to/the/run"
```

This writes `official_evaluation.json` into the run. It reports a single-query
result and never presents it as the official 180-query aggregate score.

## Frozen Stage-A experiments

```powershell
# Balanced 18-query infrastructure pilot
.\run.ps1 pilot -ExperimentId stage-a-pilot-v1

# Complete validation baseline; resume never repeats terminal samples
.\run.ps1 batch -ExperimentId stage-a-full-v1 -Resume

# Rebuild statistics, then cross-check with the official aggregate evaluator
.\run.ps1 aggregate `
  -ExperimentDir "$PWD/runs/experiments/stage-a-full-v1" `
  -OfficialAggregate
```

Both experiments freeze the dataset fingerprint, selected indices, prompt hash,
model parameters, and retry policy in `manifest.json`. Invalid model output is
counted as non-delivery and is never repaired by another LLM call.

Run offline checks with:

```powershell
$env:PYTHONPATH="$PWD/src"
conda run -n llm-learning python -m unittest discover -s tests -v
```

## Evaluator contract

Each JSONL row must contain exactly `idx`, `query`, and `plan`. `plan` is a list
of daily objects with `days`, `current_city`, `transportation`, `breakfast`,
`attraction`, `lunch`, `dinner`, and `accommodation`. Official `combination.py`
creates this JSONL after parsing and element extraction. Official `eval.py`
then reads rows positionally against the entire validation split; for validation
that means 180 ordered rows.

See `experiments/phase1.md` and generated `artifacts/phase1_report.json` for the
evidence and exact limits of the current run.

See `experiments/research_protocol.md` for the authoritative terminology and
`experiments/stage_a_direct.md` for the first real Stage-A sole-planning result
and the evaluator-format failure found during prompt development.

## Stage B: autonomous information acquisition / Two-stage ReAct

Stage B is complete and frozen as `stage-b-full-v1`: all 180 validation samples
have terminal outcomes, and the official aggregate evaluator exactly matches the
local per-sample aggregation. Delivery is 35.00% and Final Pass is 15.56%.

The candidate B setting begins with the query and requires autonomous collection
through official tools before planning. This changes the information regime from
oracle reference information (A) to tool-mediated information acquisition (B).
Consequently, A/B is a comparison between TravelPlanner's sole-planning and
two-stage settings—not a causal ablation in which tools are the only changed
variable. Cleaner component comparisons will be made within the same two-stage
setting in later B/C/D designs.

```powershell
# Fixed train development suite: one item per difficulty x horizon cell
.\run.ps1 dev -ExperimentId stage-b-train-dev-v1

# Optional single train diagnosis
.\run.ps1 react -Split train -Index 1

# Frozen validation pilot and full experiment
.\run.ps1 pilot -Baseline react -ExperimentId stage-b-pilot-v1
.\run.ps1 batch -Baseline react -ExperimentId stage-b-full-v1 -Resume

# Paired A/B report after both full experiments exist
.\run.ps1 compare `
  -StageADir "$PWD/runs/experiments/stage-a-full-v1" `
  -StageBDir "$PWD/runs/experiments/stage-b-full-v1"
```

Each B run stores `trajectory.json` with observable calls, arguments, complete
observations, tool latency, and status, plus `evidence_audit.json` for acquisition,
grounding, diagnostic oracle alignment, environment validity, and failure
classification. Oracle reference information is loaded only after the model input
is fixed and is never placed in the prompt or messages. No hidden chain-of-thought
is requested or saved. A malformed final answer, repeated call loop, 30-call
exhaustion, or context-limit termination is retained as model/agent failure and
is never repaired. Multiple independent calls returned in one model turn are
executed sequentially in their returned order under the same call budget.

A query-only, no-reference, no-tool “closed-book Direct” condition is outside the
current experimental program and is not Stage A.

See `experiments/stage_b_full_results.md` for the complete Stage-B and paired A/B
results. The main finding is not a simple score gain: B raises Final Pass by 1.67
percentage points while delivery falls by 60 points and total token use increases
by 8.41 million. This is a sole-planning-to-two-stage system gap, not the causal
effect of adding tools alone.

## Stage C: explicit global Planner + ReAct

Stage C keeps B's query-only information condition, six official tools, complete
observations, 30-call limit, model, temperature, output contract, and evaluator.
Its only intended added mechanism is one pre-tool structured global Planner call.
The Planner produces trip facts, a city/day/night route, a constraint ledger, a
minimal retrieval checklist, and planning risks; it cannot use tools or name
unobserved travel entities. There is no verifier, repair, replan, compression,
scripted retrieval, or multi-agent component.

```powershell
.\run.ps1 planner-react -Split train -Index 1
.\run.ps1 dev -Baseline planner-react -ExperimentId stage-c-train-dev-v1
.\run.ps1 pilot -Baseline planner-react -ExperimentId stage-c-pilot-v1
.\run.ps1 batch -Baseline planner-react -ExperimentId stage-c-full-v1 -Resume
.\run.ps1 compare `
  -StageBDir "$PWD/runs/experiments/stage-b-full-v1" `
  -StageCDir "$PWD/runs/experiments/stage-c-full-v1"
```

The frozen pilot completed all 18 matched samples with 33.33% delivery and
16.67% Final Pass. Relative to B's pilot it used 449,941 fewer tokens and 2.67
fewer tool calls per sample, while Delivery fell 5.56 points and Final Pass rose
5.56 points. Pilot scores are engineering signals only; the frozen 180-query
experiment is the formal result.

The full `stage-c-full-v1` result is now complete: 40.00% Delivery and 16.11%
Final Pass. Compared with B, C improves Delivery by 5.00 points and Final Pass by
0.56 points while using 300,056 fewer tokens and 1.60 fewer tool calls per sample;
mean latency increases by 0.83 seconds. See
`experiments/stage_c_full_results.md` for the formal B/C analysis.

## Stage D: Verifier + one evidence-grounded Replan

Stage D independently reruns the complete frozen Stage C chain. If that chain emits a
final response, one Verifier checks its format, grounding, route, budget, nights, diversity,
and user constraints against the existing blueprint and a stable catalog of already observed
tool evidence. Only a `repair` verdict triggers one no-tool Replan. A valid repair is used;
otherwise a valid original candidate is retained. Upstream Agent-control failures without a
candidate remain failures, so D does not conceal C's `max_steps` problem.

```powershell
.\run.ps1 dev -Baseline verifier-replan -ExperimentId stage-d-train-dev-v3
.\run.ps1 pilot -Baseline verifier-replan -ExperimentId stage-d-pilot-v1
.\run.ps1 batch -Baseline verifier-replan -ExperimentId stage-d-full-v1 -Resume
.\run.ps1 compare `
  -StageCDir "$PWD/runs/experiments/stage-c-full-v1" `
  -StageDDir "$PWD/runs/experiments/stage-d-full-v1"
```

Each run preserves the upstream candidate, evidence catalog, Verifier prompt/report,
optional Replan prompt/response, deterministic repair decision, and component-level usage
and latency. See `experiments/stage_d_verifier_replan.md` for the protocol and interpretation.

The full `stage-d-full-v1` experiment is complete. Official and local aggregation
match exactly: Delivery is 41.67% and Final Pass is 16.11%. Relative to C, D gains
1.67 Delivery points and small constraint-rate improvements, but Final Pass is
unchanged while total use rises by 1,263,248 tokens and mean latency by 4.85 seconds.
The paired comparison contains 17 gains and 17 regressions (exact McNemar p=1.0).
Under this protocol, Verifier + Single Replan is therefore not an effective overall
Final Pass mechanism. See `experiments/stage_d_full_results.md` and
`experiments/stage_abcd_summary.md` for the formal interpretation.

## Frozen analysis release

TravelPlanner A/B/C/D is now frozen: no further model generation, prompt/tool
changes, or evaluator changes belong to these four formal baselines. The offline
entrypoint `analysis/build_analysis.py` reads only the frozen experiment artifacts
and validates their hashes, row order, selected runs, and official/local agreement.

The complete Chinese synthesis is `experiments/abcd_failure_analysis.md`.
Reproducible tables, paired statistics, the unified failure taxonomy, freeze manifest,
and deterministic case selection live under `analysis/`. Ten PPT-ready figures are
available as editable SVG, 3200×1800 PNG, and one backing CSV per figure in
`analysis/figures/`.
