from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path
from typing import Any

_VALIDATION = None
_EVALUATORS = None


def _validation_dataset():
    global _VALIDATION
    if _VALIDATION is None:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
        from datasets import load_dataset
        _VALIDATION = load_dataset("osunlp/TravelPlanner", "validation")["validation"]
    return _VALIDATION


def _official_evaluators(repo: Path):
    global _EVALUATORS
    if _EVALUATORS is None:
        evaluation_dir = repo / "evaluation"
        repo_text = str(repo)
        evaluation_text = str(evaluation_dir)
        if repo_text not in sys.path:
            sys.path.insert(0, repo_text)
        if evaluation_text not in sys.path:
            sys.path.insert(0, evaluation_text)
        original_cwd = Path.cwd()
        try:
            os.chdir(evaluation_dir)
            from commonsense_constraint import evaluation as commonsense_eval
            from hard_constraint import evaluation as hard_eval
        finally:
            os.chdir(original_cwd)
        _EVALUATORS = (commonsense_eval, hard_eval)
    return _EVALUATORS


def evaluate_submission(repo: Path, submission: dict[str, Any]) -> dict[str, Any]:
    index = submission.get("idx")
    if not isinstance(index, int) or index < 1:
        raise ValueError("submission idx must be a positive integer")

    validation = _validation_dataset()
    query_data = dict(validation[index - 1])
    if query_data["query"] != submission.get("query"):
        raise ValueError("Submission query does not match the official validation row")
    if isinstance(query_data.get("local_constraint"), str):
        query_data["local_constraint"] = ast.literal_eval(query_data["local_constraint"])

    commonsense_eval, hard_eval = _official_evaluators(repo)

    commonsense = commonsense_eval(query_data, submission["plan"])
    sandbox_and_complete = (
        commonsense
        and commonsense["is_not_absent"][0]
        and commonsense["is_valid_information_in_sandbox"][0]
    )
    hard = hard_eval(query_data, submission["plan"]) if sandbox_and_complete else None

    def all_pass(result: dict[str, Any] | None) -> bool:
        if result is None:
            return False
        return all(value[0] is None or bool(value[0]) for value in result.values())

    report = {
        "scope": "single official validation query; not the 180-query aggregate score",
        "idx": index,
        "level": query_data["level"],
        "days": query_data["days"],
        "commonsense_constraint": commonsense,
        "hard_constraint": hard,
        "commonsense_pass": all_pass(commonsense),
        "hard_pass": all_pass(hard),
    }
    report["final_pass"] = report["commonsense_pass"] and report["hard_pass"]
    return report


def evaluate_single_run(repo: Path, run_dir: Path) -> dict[str, Any]:
    submission_path = run_dir / "submission.jsonl"
    if not submission_path.is_file():
        raise FileNotFoundError(f"No evaluator-ready submission: {submission_path}")
    lines = [line for line in submission_path.read_text(encoding="utf-8").splitlines() if line]
    if len(lines) != 1:
        raise ValueError("Single-run evaluation requires exactly one JSONL row")
    submission = json.loads(lines[0])
    report = evaluate_submission(repo, submission)
    output_path = run_dir / "official_evaluation.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    audit_path = run_dir / "evidence_audit.json"
    if audit_path.is_file():
        from .evidence_audit import finalize_evidence_audit
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        finalize_evidence_audit(audit, delivered=bool(submission.get("plan")), evaluation=report)
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"run_dir": str(run_dir), "output": str(output_path), **report}
