from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from .direct_runner import run_direct
from .react_runner import run_react
from .planner_react_runner import run_planner_react
from .verifier_replan_runner import run_verifier_replan
from .evaluation_runner import evaluate_single_run
from .experiment_runner import (aggregate_experiment, compare_experiments,
                                compare_mechanism_experiments, compare_verifier_experiments, run_experiment,
                                run_official_aggregate, run_train_development)
from .official_adapter import (
    load_validation_sample,
    require_official_repo,
    run_official_restaurant_tool,
    validate_submission_contract,
)


def default_repo() -> str:
    return os.environ.get(
        "TRAVELPLANNER_OFFICIAL_REPO",
        "../TravelPlanner",
    )


def inspect(repo: Path) -> dict:
    csv_dirs = ["attractions", "restaurants", "accommodations", "flights", "background", "googleDistanceMatrix"]
    dependencies = {}
    for name in ("pandas", "datasets", "openai", "langchain", "dotenv", "func_timeout"):
        try:
            module = __import__(name)
            dependencies[name] = getattr(module, "__version__", "installed")
        except Exception as exc:  # diagnostic boundary
            dependencies[name] = f"missing/unusable: {type(exc).__name__}: {exc}"
    git = subprocess.run(
        ["git", "-C", str(repo), "status", "--short", "--branch"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "official_repo": str(repo),
        "python": sys.version,
        "git_status": git.stdout.strip(),
        "git_status_stderr": git.stderr.strip(),
        "raw_database_directories": {name: (repo / "database" / name).is_dir() for name in csv_dirs},
        "reference_info_files": {
            split: (repo / "database" / f"{split}_ref_info.jsonl").is_file()
            for split in ("train", "validation", "test")
        },
        "dependencies": dependencies,
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def run_phase1(repo: Path, artifacts: Path) -> dict:
    health = inspect(repo)
    sample = load_validation_sample(repo)
    tool_trace = {
        "query": sample["query"],
        **run_official_restaurant_tool(repo, sample),
    }
    contract = validate_submission_contract(sample)
    evaluator_reasons = []
    if not all(health["raw_database_directories"].values()):
        evaluator_reasons.append(
            "The local checkout lacks raw CSV database directories required at evaluator module import."
        )
    datasets_status = health["dependencies"].get("datasets", "")
    if datasets_status.startswith("missing/unusable"):
        evaluator_reasons.append("The active Python environment cannot import datasets.")
    evaluator_reasons.append(
        "eval.py is corpus-level: it requires 180 ordered submission rows; Stage A currently evaluates one row with the same official constraint functions."
    )
    report = {
        "health": health,
        "sample": {key: value for key, value in sample.items() if key != "reference_information"},
        "tool_trace": tool_trace,
        "evaluator_contract": contract,
        "full_official_evaluator": {
            "status": "blocked",
            "reasons": evaluator_reasons,
        },
    }
    write_json(artifacts / "health.json", health)
    write_json(artifacts / "validation_sample_001.json", report["sample"])
    write_json(artifacts / "query_tool_observation.json", tool_trace)
    write_json(artifacts / "evaluator_contract.json", contract)
    write_json(artifacts / "phase1_report.json", report)
    return report


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)
    parser = argparse.ArgumentParser(description="TravelPlanner independent research harness")
    parser.add_argument("command", choices=("inspect", "sample", "tool", "contract", "phase1", "direct", "react", "planner-react", "verifier-replan", "dev", "evaluate", "pilot", "batch", "aggregate", "compare"), nargs="?", default="phase1")
    parser.add_argument("--official-repo", default=default_repo())
    parser.add_argument("--artifacts", default="artifacts")
    parser.add_argument("--runs-dir", default=str(project_root / "runs"))
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--index", type=int, default=None)
    parser.add_argument("--start", type=int, default=None)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--model", default=os.environ.get("MODEL_NAME", "deepseek-chat"))
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com"))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--experiment-id", default=None)
    parser.add_argument("--experiment-dir", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--official-aggregate", action="store_true")
    parser.add_argument("--baseline", choices=("direct", "react", "planner-react", "verifier-replan"), default="direct")
    parser.add_argument("--split", choices=("train", "validation"), default="validation")
    parser.add_argument("--stage-a-dir", default=None)
    parser.add_argument("--stage-b-dir", default=None)
    parser.add_argument("--stage-c-dir", default=None)
    parser.add_argument("--stage-d-dir", default=None)
    args = parser.parse_args()
    repo = require_official_repo(Path(args.official_repo))
    if args.command == "dev":
        if not os.environ.get("OPENAI_API_KEY"):
            parser.error("OPENAI_API_KEY is required; no development run was started")
        dev_baseline = "react" if args.baseline == "direct" else args.baseline
        result = run_train_development(repo, Path(args.runs_dir).resolve(),
                                       experiment_id=args.experiment_id or ({"planner-react": "stage-c-train-dev-v1", "verifier-replan": "stage-d-train-dev-v1"}.get(dev_baseline, "stage-b-train-dev-v1")),
                                       model=args.model, base_url=args.base_url, timeout=args.timeout,
                                       max_retries=args.max_retries, resume=args.resume,
                                       baseline=dev_baseline)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if sum(result["terminal_statuses"].values()) == result["total"] else 2
    if args.command == "compare":
        if args.stage_c_dir and args.stage_d_dir:
            result = compare_verifier_experiments(Path(args.stage_c_dir).resolve(), Path(args.stage_d_dir).resolve())
        elif args.stage_b_dir and args.stage_c_dir:
            result = compare_mechanism_experiments(Path(args.stage_b_dir).resolve(), Path(args.stage_c_dir).resolve())
        elif args.stage_a_dir and args.stage_b_dir:
            result = compare_experiments(Path(args.stage_a_dir).resolve(), Path(args.stage_b_dir).resolve())
        else:
            parser.error("compare requires A+B, B+C, or C+D experiment directories")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command in ("pilot", "batch"):
        if args.baseline in {"react", "planner-react", "verifier-replan"} and not os.environ.get("OPENAI_API_KEY"):
            parser.error("OPENAI_API_KEY is required; no experiment, model, dataset, or tool call was started")
        mode = args.command
        stage = {"direct": "a", "react": "b", "planner-react": "c", "verifier-replan": "d"}[args.baseline]
        experiment_id = args.experiment_id or f"stage-{stage}-{mode}-v1"
        result = run_experiment(
            repo, Path(args.runs_dir).resolve(), experiment_id=experiment_id,
            mode=mode, model=args.model, base_url=args.base_url,
            timeout=args.timeout, max_retries=args.max_retries, resume=args.resume,
            baseline=args.baseline,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["delivered"] == result["total"] else 2
    if args.command == "aggregate":
        if not args.experiment_dir:
            parser.error("aggregate requires --experiment-dir")
        experiment_dir = Path(args.experiment_dir).resolve()
        result = aggregate_experiment(repo, experiment_dir)
        if args.official_aggregate:
            result["official_aggregate"] = run_official_aggregate(repo, experiment_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("official_aggregate", {}).get("cross_check_pass", True) else 3
    if args.command == "evaluate":
        if not args.run_dir:
            parser.error("evaluate requires --run-dir")
        result = evaluate_single_run(repo, Path(args.run_dir).resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command in ("direct", "react", "planner-react", "verifier-replan"):
        if args.command in {"react", "planner-react", "verifier-replan"} and not os.environ.get("OPENAI_API_KEY"):
            parser.error("OPENAI_API_KEY is required; no model, dataset, or tool call was made")
        if args.command == "direct" and args.split != "validation":
            parser.error("direct currently supports validation only")
        if args.index is not None and (args.start is not None or args.end is not None):
            parser.error("use either --index or --start/--end, not both")
        if (args.start is None) != (args.end is None):
            parser.error("--start and --end must be provided together")
        if args.start is not None:
            if args.start < 1 or args.end < args.start:
                parser.error("require 1 <= --start <= --end")
            indices = range(args.start, args.end + 1)
        else:
            indices = [args.index or 1]
        runner = {"direct": run_direct, "react": run_react,
                  "planner-react": run_planner_react,
                  "verifier-replan": run_verifier_replan}[args.command]
        results = [
            runner(
                repo,
                Path(args.runs_dir).resolve(),
                index,
                model=args.model,
                base_url=args.base_url,
                timeout=args.timeout,
                max_retries=args.max_retries,
                **({"split": args.split} if args.command in {"react", "planner-react", "verifier-replan"} else {}),
            )
            for index in indices
        ]
        labels = {"direct": "A_sole_planning_direct", "react": "B_two_stage_react",
                  "planner-react": "C_explicit_planner_react",
                  "verifier-replan": "D_verifier_single_replan"}
        print(json.dumps({"baseline": labels[args.command], "runs": results}, ensure_ascii=False, indent=2))
        return 0 if all(result["status"] == "completed" for result in results) else 2
    sample = load_validation_sample(repo, args.index or 1)
    if args.command == "inspect":
        result = inspect(repo)
    elif args.command == "sample":
        result = {key: value for key, value in sample.items() if key != "reference_information"}
    elif args.command == "tool":
        result = {"query": sample["query"], **run_official_restaurant_tool(repo, sample)}
    elif args.command == "contract":
        result = validate_submission_contract(sample)
    else:
        result = run_phase1(repo, Path(args.artifacts).resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
