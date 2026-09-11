from __future__ import annotations

import json
import os
import random
import ast
import math
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .baselines import (PLANNER_MAX_OUTPUT_TOKENS, PLANNER_PROMPT_VERSION, PROMPT_VERSION,
                        REACT_PROMPT_VERSION, planner_react_protocol_hash,
                        prompt_protocol_hash, react_protocol_hash)
from .direct_runner import run_direct
from .react_runner import run_react
from .planner_react_runner import run_planner_react
from .verifier_replan_runner import run_verifier_replan
from .verifier_replan import (EVIDENCE_CATALOG_VERSION, REPLAN_MAX_OUTPUT_TOKENS,
                              REPLAN_PROMPT_VERSION, VERIFIER_AUDIT_VERSION,
                              VERIFIER_MAX_OUTPUT_TOKENS, VERIFIER_PROMPT_VERSION,
                              verifier_replan_protocol_hash)
from .react_tools import tool_schema_hash
from .evaluation_runner import evaluate_single_run, evaluate_submission
from .evidence_audit import AUDIT_VERSION, finalize_evidence_audit
from .planner_audit import PLANNER_AUDIT_VERSION
from .official_adapter import load_validation_sample

SEED = 20260904
TERMINAL = {"completed", "invalid_output", "blocked"}


def _baseline_id(baseline: str) -> str:
    return {"direct": "A_sole_planning_direct", "react": "B_two_stage_react",
            "planner-react": "C_explicit_planner_react",
            "verifier-replan": "D_verifier_single_replan"}[baseline]


def _runner(baseline: str):
    return {"direct": run_direct, "react": run_react,
            "planner-react": run_planner_react,
            "verifier-replan": run_verifier_replan}[baseline]


def _protocol(baseline: str, *, model: str, base_url: str,
              timeout: float, max_retries: int) -> dict[str, Any]:
    if baseline == "direct":
        return {"model": model, "base_url": base_url, "temperature": 0.0,
                "timeout_seconds": timeout, "max_transport_retries": max_retries,
                "prompt_version": PROMPT_VERSION,
                "prompt_protocol_hash": prompt_protocol_hash()}
    protocol = {"model": model, "base_url": base_url, "temperature": 0.0,
                "timeout_seconds": timeout, "max_transport_retries": max_retries,
                "prompt_version": (REACT_PROMPT_VERSION if baseline == "react" else PLANNER_PROMPT_VERSION),
                "prompt_protocol_hash": (react_protocol_hash() if baseline == "react" else planner_react_protocol_hash()),
                "tool_schema_hash": tool_schema_hash(), "max_tool_calls": 30,
                "max_context_tokens": 56000, "max_output_tokens": 8000,
                "multi_tool_call_policy": "sequential_batch",
                "evidence_audit_version": AUDIT_VERSION}
    if baseline in {"planner-react", "verifier-replan"}:
        protocol.update({"planner_max_output_tokens": PLANNER_MAX_OUTPUT_TOKENS,
                         "planner_audit_version": PLANNER_AUDIT_VERSION,
                         "observation_compression": False,
                         "scripted_retrieval": False})
    if baseline == "verifier-replan":
        protocol.update({"stage_d_protocol_hash": verifier_replan_protocol_hash(),
                         "verifier_prompt_version": VERIFIER_PROMPT_VERSION,
                         "replan_prompt_version": REPLAN_PROMPT_VERSION,
                         "verifier_max_output_tokens": VERIFIER_MAX_OUTPUT_TOKENS,
                         "replan_max_output_tokens": REPLAN_MAX_OUTPUT_TOKENS,
                         "verifier_calls_max": 1, "replan_calls_max": 1,
                         "replan_tools": False, "fallback": "valid_replan_then_valid_original_then_empty",
                         "evidence_catalog_version": EVIDENCE_CATALOG_VERSION,
                         "verifier_audit_version": VERIFIER_AUDIT_VERSION})
    return protocol


def _atomic_json(path: Path, value: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_validation_metadata() -> tuple[list[dict[str, Any]], str]:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    from datasets import load_dataset

    data = load_dataset("osunlp/TravelPlanner", "validation")["validation"]
    rows = []
    for i in range(len(data)):
        local = data[i]["local_constraint"]
        if isinstance(local, str):
            local = ast.literal_eval(local)
        rows.append({
            "idx": i + 1, "level": data[i]["level"],
            "days": int(data[i]["days"]), "local_constraint": local,
            "query": data[i]["query"],
        })
    return rows, getattr(data, "_fingerprint", "unknown")


def pilot_indices(rows: list[dict[str, Any]], seed: int = SEED) -> list[int]:
    strata: dict[tuple[str, int], list[int]] = defaultdict(list)
    for row in rows:
        if row["idx"] != 1:
            strata[(row["level"], row["days"])].append(row["idx"])
    rng = random.Random(seed)
    selected: list[int] = []
    for level in ("easy", "medium", "hard"):
        for days in (3, 5, 7):
            selected.extend(rng.sample(strata[(level, days)], 2))
    return sorted(selected)


def development_indices(rows: list[dict[str, Any]], seed: int = SEED) -> list[int]:
    """One deterministic train example per difficulty x horizon cell."""
    strata: dict[tuple[str, int], list[int]] = defaultdict(list)
    for row in rows:
        strata[(row["level"], row["days"])].append(row["idx"])
    rng = random.Random(seed)
    return sorted(rng.choice(strata[(level, days)])
                  for level in ("easy", "medium", "hard") for days in (3, 5, 7))


def load_train_metadata() -> tuple[list[dict[str, Any]], str]:
    from datasets import load_dataset
    data = load_dataset("osunlp/TravelPlanner", "train")["train"]
    rows = [{"idx": i + 1, "level": data[i]["level"], "days": int(data[i]["days"]),
             "query": data[i]["query"]} for i in range(len(data))]
    return rows, getattr(data, "_fingerprint", "unknown")


def create_or_load_manifest(
    repo: Path,
    experiments_dir: Path,
    *,
    experiment_id: str,
    mode: str,
    model: str,
    base_url: str,
    timeout: float,
    max_retries: int,
    resume: bool,
    baseline: str = "direct",
) -> tuple[Path, dict[str, Any]]:
    experiment_dir = experiments_dir / experiment_id
    manifest_path = experiment_dir / "manifest.json"
    if manifest_path.exists():
        if not resume:
            raise FileExistsError(f"Experiment exists; use --resume: {experiment_dir}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        frozen = manifest["protocol"]
        expected = _protocol(baseline, model=model, base_url=base_url,
                             timeout=timeout, max_retries=max_retries)
        if frozen != expected:
            raise ValueError("Resume configuration differs from frozen manifest protocol")
        return experiment_dir, manifest

    rows, fingerprint = load_validation_metadata()
    indices = pilot_indices(rows) if mode == "pilot" else list(range(1, 181))
    git_commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    git_status = subprocess.run(
        ["git", "-C", str(repo), "status", "--short"], capture_output=True, text=True
    ).stdout.strip()
    experiment_dir.mkdir(parents=True, exist_ok=False)
    protocol = _protocol(baseline, model=model, base_url=base_url,
                         timeout=timeout, max_retries=max_retries)
    manifest = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "baseline": baseline,
        "mode": mode,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": SEED if mode == "pilot" else None,
        "excluded_development_indices": [1] if mode == "pilot" else [],
        "dataset": {"name": "osunlp/TravelPlanner", "config": "validation", "rows": 180, "fingerprint": fingerprint},
        "git_commit": git_commit,
        "git_status": git_status,
        "baseline_id": _baseline_id(baseline),
        "protocol": protocol,
        "indices": indices,
        "samples": {str(i): {"status": "pending", "attempts": []} for i in indices},
    }
    _atomic_json(manifest_path, manifest)
    return experiment_dir, manifest


def run_experiment(
    repo: Path,
    runs_dir: Path,
    *,
    experiment_id: str,
    mode: str,
    model: str,
    base_url: str,
    timeout: float,
    max_retries: int,
    resume: bool,
    baseline: str = "direct",
) -> dict[str, Any]:
    experiment_dir, manifest = create_or_load_manifest(
        repo, runs_dir / "experiments", experiment_id=experiment_id, mode=mode,
        model=model, base_url=base_url, timeout=timeout, max_retries=max_retries,
        resume=resume, baseline=baseline,
    )
    manifest_path = experiment_dir / "manifest.json"
    rows, _ = load_validation_metadata()
    canonical = {row["idx"]: row["query"] for row in rows}
    for index in manifest["indices"]:
        sample_state = manifest["samples"][str(index)]
        if (sample_state.get("status") == "blocked" and sample_state.get("attempts")
                and sample_state["attempts"][-1].get("retryable")):
            # A later --resume is a new transport opportunity, not a fabricated model retry.
            sample_state["status"] = "pending"
        selected_path = Path(sample_state["selected_run_dir"]) if sample_state.get("selected_run_dir") else None
        if selected_path and (selected_path / "submission.jsonl").is_file():
            prior = json.loads((selected_path / "submission.jsonl").read_text(encoding="utf-8"))
            if prior.get("query") != canonical[index]:
                sample_state.setdefault("superseded", []).append({
                    "run_dir": str(selected_path),
                    "reason": "query differs from canonical Hugging Face validation row",
                })
                sample_state["status"] = "pending"
                sample_state.pop("selected_run_dir", None)
        if sample_state["status"] in TERMINAL:
            continue
        for retry in range(max_retries + 1):
            attempt = len(sample_state["attempts"]) + 1
            runner = _runner(baseline)
            result = runner(
                repo, runs_dir, index, model=model, base_url=base_url,
                timeout=timeout, max_retries=0, experiment_id=experiment_id,
                attempt=attempt, canonical_query=canonical[index],
            )
            sample_state["attempts"].append(result)
            if result["status"] != "blocked" or not result.get("retryable"):
                break
            if retry == max_retries:
                break
        sample_state["status"] = sample_state["attempts"][-1]["status"]
        sample_state["selected_run_dir"] = sample_state["attempts"][-1]["run_dir"]
        _atomic_json(manifest_path, manifest)
    summary = aggregate_experiment(repo, experiment_dir, manifest)
    return {"experiment_dir": str(experiment_dir), **summary}


def run_train_development(repo: Path, runs_dir: Path, *, experiment_id: str, model: str,
                          base_url: str, timeout: float, max_retries: int,
                          resume: bool, baseline: str = "react") -> dict[str, Any]:
    experiment_dir = runs_dir / "experiments" / experiment_id
    manifest_path = experiment_dir / "manifest.json"
    rows, fingerprint = load_train_metadata()
    indices = development_indices(rows)
    if baseline not in {"react", "planner-react", "verifier-replan"}:
        raise ValueError("train development supports react, planner-react, or verifier-replan")
    protocol = _protocol(baseline, model=model, base_url=base_url,
                         timeout=timeout, max_retries=max_retries)
    if manifest_path.exists():
        if not resume:
            raise FileExistsError(f"Development experiment exists; use --resume: {experiment_dir}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["protocol"] != protocol or manifest["indices"] != indices:
            raise ValueError("Resume configuration differs from frozen development manifest")
    else:
        experiment_dir.mkdir(parents=True, exist_ok=False)
        git_commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                    capture_output=True, text=True).stdout.strip()
        git_status = subprocess.run(["git", "-C", str(repo), "status", "--short"],
                                    capture_output=True, text=True).stdout.strip()
        manifest = {"schema_version": 1, "experiment_id": experiment_id,
                    "mode": "train_development", "split": "train", "baseline": baseline,
                    "baseline_id": _baseline_id(baseline), "seed": SEED,
                    "dataset": {"name": "osunlp/TravelPlanner", "config": "train",
                                "rows": len(rows), "fingerprint": fingerprint},
                    "git_commit": git_commit, "git_status": git_status,
                    "protocol": protocol, "indices": indices,
                    "samples": {str(i): {"status": "pending", "attempts": []} for i in indices}}
        _atomic_json(manifest_path, manifest)
    canonical = {row["idx"]: row["query"] for row in rows}
    for index in indices:
        state = manifest["samples"][str(index)]
        if state["status"] in TERMINAL:
            continue
        for retry in range(max_retries + 1):
            result = _runner(baseline)(repo, runs_dir, index, model=model, base_url=base_url,
                                       timeout=timeout, max_retries=0,
                                       experiment_id=experiment_id,
                                       attempt=len(state["attempts"]) + 1,
                                       canonical_query=canonical[index], split="train")
            state["attempts"].append(result)
            if result["status"] != "blocked" or not result.get("retryable") or retry == max_retries:
                break
        state["status"] = state["attempts"][-1]["status"]
        state["selected_run_dir"] = state["attempts"][-1]["run_dir"]
        _atomic_json(manifest_path, manifest)
    summary = {"experiment_id": experiment_id, "split": "train", "indices": indices,
               "total": len(indices), "terminal_statuses": dict(Counter(
                   manifest["samples"][str(i)]["status"] for i in indices)),
               "note": "Engineering development only; no validation score or research conclusion."}
    _atomic_json(experiment_dir / "development_summary.json", summary)
    return {"experiment_dir": str(experiment_dir), **summary}


def _empty_submission(index: int, query: str) -> dict[str, Any]:
    return {"idx": index, "query": query, "plan": []}


def aggregate_experiment(
    repo: Path, experiment_dir: Path, manifest: dict[str, Any] | None = None
) -> dict[str, Any]:
    if manifest is None:
        manifest = json.loads((experiment_dir / "manifest.json").read_text(encoding="utf-8"))
    submissions: list[dict[str, Any]] = []
    per_sample: list[dict[str, Any]] = []
    usage = Counter()
    latencies: list[float] = []
    failures = Counter()
    failure_categories = Counter()
    constraint_pass = Counter()
    constraint_total = Counter()
    sensitivity_constraint_pass = Counter()
    rows, _ = load_validation_metadata()
    metadata = {row["idx"]: row for row in rows}
    groups: dict[str, Counter] = defaultdict(Counter)

    category_map = {
        "is_valid_accommodation": "minimum_nights",
        "valid_cost": "budget",
        "is_valid_information_in_sandbox": "invalid_entity_sandbox",
        "is_reasonable_visiting_city": "route_current_city",
        "is_valid_information_in_current_city": "route_current_city",
        "is_valid_transportation": "transportation",
        "valid_transportation": "transportation",
        "is_valid_restaurants": "restaurant_diversity",
        "is_valid_attractions": "attraction_diversity",
        "valid_room_rule": "room_house_rule",
        "valid_cuisine": "cuisine",
        "valid_room_type": "room_type",
        "is_not_absent": "incomplete",
    }
    for index in manifest["indices"]:
        state = manifest["samples"][str(index)]
        selected = Path(state["selected_run_dir"]) if state.get("selected_run_dir") else None
        submission = _empty_submission(index, metadata[index]["query"])
        if selected and (selected / "submission.jsonl").is_file():
            submission = json.loads((selected / "submission.jsonl").read_text(encoding="utf-8"))
            evaluation_path = selected / "official_evaluation.json"
            if evaluation_path.is_file():
                evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
            else:
                evaluation = evaluate_single_run(repo, selected)
        else:
            evaluation = {
                "idx": index, "commonsense_constraint": None,
                "hard_constraint": None, "commonsense_pass": False,
                "hard_pass": False, "final_pass": False,
            }
            failures["non_delivery"] += 1
            failure_categories["malformed_or_non_delivery"] += 1
        submissions.append(submission)
        result = state.get("attempts", [{}])[-1]
        for key, value in result.get("usage", {}).items():
            if value is not None:
                usage[key] += value
        if result.get("latency_seconds") is not None:
            latencies.append(result["latency_seconds"])
        for family in ("commonsense_constraint", "hard_constraint"):
            constraints = evaluation.get(family) or {}
            for name, value in constraints.items():
                if value[0] is not None:
                    constraint_total[name] += 1
                    if value[0] is True:
                        constraint_pass[name] += 1
                        if index != 1:
                            sensitivity_constraint_pass[name] += 1
                if value[0] is False:
                    failures[name] += 1
                    failure_categories[category_map.get(name, name)] += 1
        meta = metadata[index]
        group_keys = (
            "all", f"level:{meta['level']}", f"days:{meta['days']}",
            f"cell:{meta['level']}:{meta['days']}",
        )
        for group in group_keys:
            groups[group]["total"] += 1
            groups[group]["delivered"] += bool(submission["plan"])
            groups[group]["commonsense_pass"] += bool(evaluation["commonsense_pass"])
            groups[group]["hard_pass"] += bool(evaluation["hard_pass"])
            groups[group]["final_pass"] += bool(evaluation["final_pass"])
        per_sample.append({
            "idx": index, "status": state["status"],
            "commonsense_pass": evaluation["commonsense_pass"],
            "hard_pass": evaluation["hard_pass"], "final_pass": evaluation["final_pass"],
            "level": meta["level"], "days": meta["days"],
        })
        if manifest.get("baseline") == "verifier-replan" and selected and (selected / "verifier_audit.json").is_file():
            verifier_path = selected / "verifier_audit.json"
            verifier_audit = json.loads(verifier_path.read_text(encoding="utf-8"))
            candidate_eval = None
            if (selected / "candidate_submission.jsonl").is_file():
                candidate = json.loads((selected / "candidate_submission.jsonl").read_text(encoding="utf-8"))
                candidate_eval = evaluate_submission(repo, candidate)
                _atomic_json(selected / "candidate_official_evaluation.json", candidate_eval)
            candidate_pass = bool(candidate_eval and candidate_eval["final_pass"])
            verdict = (json.loads((selected / "verifier_report.json").read_text(encoding="utf-8")).get("verdict")
                       if (selected / "verifier_report.json").is_file() else None)
            predicted_failure = verdict == "repair"
            actual_failure = not candidate_pass
            confusion = ("TP" if predicted_failure and actual_failure else
                         "FP" if predicted_failure else "FN" if actual_failure else "TN") if verdict else None
            verifier_audit.update({"posthoc_candidate_evaluation": candidate_eval,
                                   "posthoc_verifier_confusion": confusion,
                                   "final_evaluation": evaluation,
                                   "final_pass_changed": bool(evaluation["final_pass"]) != candidate_pass})
            _atomic_json(verifier_path, verifier_audit)
            per_sample[-1]["candidate_final_pass"] = candidate_pass
            per_sample[-1]["verifier_confusion"] = confusion
            decision = verifier_audit.get("repair_decision", {})
            action, reason = decision.get("action"), decision.get("reason")
            upstream_reason = verifier_audit.get("upstream_terminal_reason")
            if upstream_reason != "final_response": primary_d = "upstream_agent_control_non_delivery"
            elif reason in {"verifier_invalid", "verifier_context_limit"}: primary_d = "verifier_context_or_format_failure"
            elif action == "non_delivery" and not verifier_audit.get("candidate_valid"): primary_d = "candidate_malformed_unrepaired"
            elif action == "fallback_original": primary_d = "replan_invalid_fallback_original"
            elif action == "non_delivery" and reason == "verifier_repair": primary_d = "replan_invalid_non_delivery"
            elif confusion == "FN": primary_d = "verifier_false_negative"
            elif action == "use_replan" and not evaluation["final_pass"]: primary_d = "replan_constraint_failure"
            elif action == "use_replan" and evaluation["final_pass"]: primary_d = "repair_success"
            elif evaluation["final_pass"]: primary_d = "unchanged_success"
            else: primary_d = "verifier_false_negative" if verdict == "pass" else "replan_constraint_failure"
            verifier_audit["primary_failure_category"] = primary_d
            _atomic_json(verifier_path, verifier_audit)
            per_sample[-1]["primary_failure_category"] = primary_d
            per_sample[-1]["stage_d_primary_failure_category"] = primary_d
        if manifest.get("baseline") in {"react", "planner-react", "verifier-replan"} and selected and (selected / "evidence_audit.json").is_file():
            audit_path = selected / "evidence_audit.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            finalize_evidence_audit(audit, delivered=bool(submission["plan"]), evaluation=evaluation)
            _atomic_json(audit_path, audit)
            per_sample[-1]["primary_failure_category"] = audit["primary_failure_category"]
            per_sample[-1]["failure_flags"] = audit["failure_flags"]
            per_sample[-1]["chosen_route_coverage_rate"] = audit["chosen_route_coverage"]["rate"]
            per_sample[-1]["evidence_grounding_rate"] = audit["plan_evidence_grounding"]["rate"]
            per_sample[-1]["oracle_alignment_rate"] = audit["oracle_alignment"]["rate"]
            if manifest.get("baseline") in {"planner-react", "verifier-replan"} and (selected / "planner_audit.json").is_file():
                planner_path = selected / "planner_audit.json"
                planner = json.loads(planner_path.read_text(encoding="utf-8"))
                planner_valid = bool((planner.get("planner_response") or {}).get("validation", {}).get("valid"))
                route_consistent = (planner.get("route_consistency") or {}).get("consistent")
                flags = {
                    "planner_non_delivery": not planner_valid,
                    "agent_control_non_delivery": planner_valid and not bool(submission["plan"]),
                    "tool_execution_failure": audit["tool_execution"]["errors"] > 0,
                    "evidence_insufficient": not audit["chosen_route_coverage"]["sufficient"],
                    "blueprint_execution_deviation": route_consistent is False,
                    "evidence_utilization_or_grounding_failure": not audit["plan_evidence_grounding"]["fully_grounded"],
                    "planning_constraint_failure": bool(submission["plan"] and not evaluation["final_pass"]),
                }
                if evaluation["final_pass"]:
                    primary = "success"
                else:
                    priority = ("planner_non_delivery", "agent_control_non_delivery",
                                "tool_execution_failure", "evidence_insufficient",
                                "blueprint_execution_deviation",
                                "evidence_utilization_or_grounding_failure",
                                "planning_constraint_failure")
                    primary = next((name for name in priority if flags[name]), "planning_constraint_failure")
                planner["failure_flags"] = flags
                planner["primary_failure_category"] = primary
                _atomic_json(planner_path, planner)
                per_sample[-1]["primary_failure_category"] = primary
                per_sample[-1]["failure_flags"] = flags
                per_sample[-1]["planner_constraint_coverage_rate"] = (planner.get("query_constraint_coverage") or {}).get("rate")
                per_sample[-1]["retrieval_checklist_completion_rate"] = (planner.get("retrieval_checklist") or {}).get("rate")
                per_sample[-1]["blueprint_route_consistent"] = route_consistent
                if manifest.get("baseline") == "verifier-replan" and per_sample[-1].get("stage_d_primary_failure_category"):
                    per_sample[-1]["primary_failure_category"] = per_sample[-1]["stage_d_primary_failure_category"]
    submissions.sort(key=lambda row: row["idx"])
    with (experiment_dir / "submission.jsonl").open("w", encoding="utf-8") as stream:
        for row in submissions:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    _atomic_json(experiment_dir / "per_sample.json", per_sample)
    delivered = sum(bool(row["plan"]) for row in submissions)
    total = len(submissions)
    commonsense_micro_denominator = 8 * total
    hard_micro_denominator = sum(
        1 + sum(value is not None for value in metadata[i]["local_constraint"].values())
        for i in manifest["indices"]
    )

    def group_rates(counter: Counter) -> dict[str, Any]:
        n = counter["total"]
        return {
            "total": n,
            "delivery_rate": counter["delivered"] / n,
            "commonsense_macro_pass_rate": counter["commonsense_pass"] / n,
            "hard_macro_pass_rate": counter["hard_pass"] / n,
            "final_pass_rate": counter["final_pass"] / n,
        }

    sensitivity_rows = [x for x in per_sample if x["idx"] != 1]
    sensitivity_total = len(sensitivity_rows)
    sensitivity_hard_denominator = sum(
        1 + sum(value is not None for value in metadata[i]["local_constraint"].values())
        for i in manifest["indices"] if i != 1
    )
    sensitivity = {
        "total": sensitivity_total,
        "delivery_rate": sum(x["status"] == "completed" for x in sensitivity_rows) / sensitivity_total if sensitivity_total else None,
        "commonsense_micro_pass_rate": sum(
            sensitivity_constraint_pass[name] for name in (
                "is_reasonable_visiting_city", "is_valid_restaurants",
                "is_valid_attractions", "is_valid_accommodation",
                "is_valid_transportation", "is_valid_information_in_current_city",
                "is_valid_information_in_sandbox", "is_not_absent",
            )
        ) / (8 * sensitivity_total) if sensitivity_total else None,
        "commonsense_macro_pass_rate": sum(x["commonsense_pass"] for x in sensitivity_rows) / sensitivity_total if sensitivity_total else None,
        "hard_micro_pass_rate": sum(
            sensitivity_constraint_pass[name] for name in (
                "valid_cost", "valid_room_rule", "valid_cuisine",
                "valid_room_type", "valid_transportation",
            )
        ) / sensitivity_hard_denominator if sensitivity_hard_denominator else None,
        "hard_macro_pass_rate": sum(x["hard_pass"] for x in sensitivity_rows) / sensitivity_total if sensitivity_total else None,
        "final_pass_rate": sum(x["final_pass"] for x in sensitivity_rows) / sensitivity_total if sensitivity_total else None,
    }
    summary = {
        "experiment_id": manifest["experiment_id"], "baseline": manifest.get("baseline", "direct"), "mode": manifest["mode"],
        "total": total, "delivered": delivered, "delivery_rate": delivered / total,
        "commonsense_macro_pass_rate": sum(x["commonsense_pass"] for x in per_sample) / total,
        "hard_macro_pass_rate": sum(x["hard_pass"] for x in per_sample) / total,
        "final_pass_rate": sum(x["final_pass"] for x in per_sample) / total,
        "commonsense_micro_pass_rate": sum(
            constraint_pass[name] for name in (
                "is_reasonable_visiting_city", "is_valid_restaurants",
                "is_valid_attractions", "is_valid_accommodation",
                "is_valid_transportation", "is_valid_information_in_current_city",
                "is_valid_information_in_sandbox", "is_not_absent",
            )
        ) / commonsense_micro_denominator,
        "hard_micro_pass_rate": sum(
            constraint_pass[name] for name in (
                "valid_cost", "valid_room_rule", "valid_cuisine",
                "valid_room_type", "valid_transportation",
            )
        ) / hard_micro_denominator,
        "constraint_pass": {
            name: {"pass": constraint_pass[name], "total": constraint_total[name],
                   "rate": constraint_pass[name] / constraint_total[name]}
            for name in constraint_total
        },
        "groups": {name: group_rates(counter) for name, counter in groups.items()},
        "sensitivity_excluding_validation_1": sensitivity,
        "usage": dict(usage),
        "latency_seconds": {"total": sum(latencies), "mean": sum(latencies) / len(latencies) if latencies else None},
        "failures": dict(failures),
        "failure_categories": dict(failure_categories),
        "terminal_statuses": dict(Counter(x["status"] for x in per_sample)),
        "total_attempts": sum(len(manifest["samples"][str(i)]["attempts"]) for i in manifest["indices"]),
    }
    if manifest.get("baseline") in {"react", "planner-react", "verifier-replan"}:
        react_rows = [manifest["samples"][str(i)].get("attempts", [{}])[-1] for i in manifest["indices"]]
        tool_counts = [int(row.get("tool_calls", 0)) for row in react_rows]
        model_counts = [int(row.get("model_calls_attempted", 0)) for row in react_rows]
        tool_frequency, tool_errors, empty_results, observation_bytes = Counter(), Counter(), 0, 0
        primary_failures, audit_rates = Counter(), defaultdict(list)
        for row in react_rows:
            run_dir = Path(row["run_dir"]) if row.get("run_dir") else None
            if run_dir and (run_dir / "trajectory.json").is_file():
                for step in json.loads((run_dir / "trajectory.json").read_text(encoding="utf-8")):
                    tool_frequency[step.get("tool", "unknown")] += 1
                    if step.get("status") == "error": tool_errors[step.get("tool", "unknown")] += 1
                    if step.get("observation", {}).get("empty"): empty_results += 1
                    observation_bytes += int(step.get("observation_bytes", 0))
            if run_dir and (run_dir / "evidence_audit.json").is_file():
                audit = json.loads((run_dir / "evidence_audit.json").read_text(encoding="utf-8"))
                primary_failures[audit.get("primary_failure_category", "unclassified")] += 1
                for name, section in (("chosen_route_coverage", "chosen_route_coverage"),
                                      ("plan_evidence_grounding", "plan_evidence_grounding"),
                                      ("oracle_alignment", "oracle_alignment")):
                    rate = audit[section].get("rate")
                    if rate is not None: audit_rates[name].append(rate)
        def distribution(values: list[int]) -> dict[str, Any]:
            ordered = sorted(values)
            def percentile(p: float) -> int | None:
                return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * p))] if ordered else None
            return {"mean": sum(values) / len(values) if values else None, "p50": percentile(.5), "p90": percentile(.9), "max": max(values) if values else None}
        summary["react"] = {"tool_calls": distribution(tool_counts), "model_calls": distribution(model_counts),
                            "tool_frequency": dict(tool_frequency), "tool_errors": dict(tool_errors),
                            "empty_results": empty_results, "observation_bytes": observation_bytes,
                            "terminal_reasons": dict(Counter(row.get("stage", "unknown") for row in react_rows)),
                            "acquisition_funnel": dict(primary_failures),
                            "mean_rates": {name: sum(values) / len(values) if values else None for name, values in audit_rates.items()},
                            "conditional_planning_success": (
                                sum(x.get("final_pass", False) for x in per_sample if x.get("primary_failure_category") in {"planning_constraint_failure", "success"}) /
                                sum(1 for x in per_sample if x.get("primary_failure_category") in {"planning_constraint_failure", "success"})
                                if any(x.get("primary_failure_category") in {"planning_constraint_failure", "success"} for x in per_sample) else None),
                            }
        if manifest.get("baseline") in {"planner-react", "verifier-replan"}:
            planner_usage, planner_latencies = Counter(), []
            planner_rates: dict[str, list[float]] = defaultdict(list)
            planner_primary = Counter()
            for row in react_rows:
                for key, value in row.get("planner_usage", {}).items():
                    if value is not None: planner_usage[key] += value
                if row.get("planner_latency_seconds") is not None:
                    planner_latencies.append(float(row["planner_latency_seconds"]))
                run_dir = Path(row["run_dir"]) if row.get("run_dir") else None
                if run_dir and (run_dir / "planner_audit.json").is_file():
                    planner = json.loads((run_dir / "planner_audit.json").read_text(encoding="utf-8"))
                    planner_primary[planner.get("primary_failure_category", "unclassified")] += 1
                    for name, section in (("constraint_coverage", "query_constraint_coverage"),
                                          ("checklist_completion", "retrieval_checklist"),
                                          ("unplanned_call_rate", "execution_deviation")):
                        key = "rate" if name != "unplanned_call_rate" else "unplanned_call_rate"
                        value = (planner.get(section) or {}).get(key)
                        if value is not None: planner_rates[name].append(float(value))
            summary["planner"] = {
                "prompt_version": PLANNER_PROMPT_VERSION,
                "usage": dict(planner_usage),
                "latency_seconds": {"total": sum(planner_latencies),
                                    "mean": sum(planner_latencies) / len(planner_latencies) if planner_latencies else None},
                "failure_funnel": dict(planner_primary),
                "mean_rates": {name: sum(values) / len(values) if values else None
                               for name, values in planner_rates.items()},
            }
        if manifest.get("baseline") == "verifier-replan":
            verifier_usage, replan_usage = Counter(), Counter()
            verifier_calls = replan_calls = fallback_count = repaired_count = 0
            decisions, upstream, confusion, d_failures = Counter(), Counter(), Counter(), Counter()
            verifier_latencies, replan_latencies = [], []
            for row in react_rows:
                verifier_calls += int(row.get("verifier_calls", 0)); replan_calls += int(row.get("replan_calls", 0))
                upstream[row.get("upstream_stage", "unknown")] += 1
                for key, value in row.get("verifier_usage", {}).items():
                    if value is not None: verifier_usage[key] += value
                for key, value in row.get("replan_usage", {}).items():
                    if value is not None: replan_usage[key] += value
                if row.get("verifier_latency_seconds") is not None: verifier_latencies.append(float(row["verifier_latency_seconds"]))
                if row.get("replan_latency_seconds") is not None: replan_latencies.append(float(row["replan_latency_seconds"]))
                run_dir = Path(row["run_dir"]) if row.get("run_dir") else None
                if run_dir and (run_dir / "repair_decision.json").is_file():
                    decision = json.loads((run_dir / "repair_decision.json").read_text(encoding="utf-8"))
                    action = decision.get("action", "unknown"); decisions[action] += 1
                    fallback_count += action == "fallback_original"; repaired_count += action == "use_replan"
                if run_dir and (run_dir / "verifier_audit.json").is_file():
                    va = json.loads((run_dir / "verifier_audit.json").read_text(encoding="utf-8"))
                    if va.get("posthoc_verifier_confusion"): confusion[va["posthoc_verifier_confusion"]] += 1
                    d_failures[va.get("primary_failure_category", "unclassified")] += 1
            summary["verifier_replan"] = {
                "verifier_calls": verifier_calls, "replan_calls": replan_calls,
                "replan_trigger_rate": replan_calls / total, "fallback_rate": fallback_count / total,
                "valid_replan_rate": repaired_count / replan_calls if replan_calls else None,
                "decisions": dict(decisions), "upstream_terminal_reasons": dict(upstream),
                "verifier_confusion": dict(confusion), "failure_funnel": dict(d_failures),
                "verifier_usage": dict(verifier_usage), "replan_usage": dict(replan_usage),
                "verifier_latency_seconds": {"total": sum(verifier_latencies), "mean": sum(verifier_latencies) / len(verifier_latencies) if verifier_latencies else None},
                "replan_latency_seconds": {"total": sum(replan_latencies), "mean": sum(replan_latencies) / len(replan_latencies) if replan_latencies else None},
            }
    _atomic_json(experiment_dir / "summary.json", summary)
    return summary


def run_official_aggregate(repo: Path, experiment_dir: Path) -> dict[str, Any]:
    submission = experiment_dir / "submission.jsonl"
    manifest = json.loads((experiment_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest["indices"] != list(range(1, 181)):
        raise ValueError("Official aggregate requires exactly validation indices 1..180")
    process_env = os.environ.copy()
    process_env.pop("HF_HUB_OFFLINE", None)
    process_env.pop("HF_DATASETS_OFFLINE", None)
    process = subprocess.run(
        [sys.executable, "eval.py", "--set_type", "validation",
         "--evaluation_file_path", str(submission)],
        cwd=repo / "evaluation", capture_output=True, text=True, env=process_env,
    )
    (experiment_dir / "official_aggregate_stdout.txt").write_text(
        process.stdout + ("\nSTDERR\n" + process.stderr if process.stderr else ""),
        encoding="utf-8",
    )
    parsed: dict[str, float] = {}
    for line in process.stdout.splitlines():
        match = re.match(r"^(.+): ([0-9.]+)%$", line.strip())
        if match:
            parsed[match.group(1)] = float(match.group(2)) / 100.0
    local = json.loads((experiment_dir / "summary.json").read_text(encoding="utf-8"))
    mapping = {
        "Delivery Rate": "delivery_rate",
        "Commonsense Constraint Micro Pass Rate": "commonsense_micro_pass_rate",
        "Commonsense Constraint Macro Pass Rate": "commonsense_macro_pass_rate",
        "Hard Constraint Micro Pass Rate": "hard_micro_pass_rate",
        "Hard Constraint Macro Pass Rate": "hard_macro_pass_rate",
        "Final Pass Rate": "final_pass_rate",
    }
    differences = {
        official: {"official": parsed.get(official), "local": local[key]}
        for official, key in mapping.items()
        if parsed.get(official) is None or abs(parsed[official] - local[key]) > 1e-9
    }
    report = {
        "returncode": process.returncode, "scores": parsed,
        "cross_check_pass": process.returncode == 0 and not differences,
        "differences": differences,
    }
    _atomic_json(experiment_dir / "official_aggregate.json", report)
    return report


def compare_experiments(stage_a_dir: Path, stage_b_dir: Path, output_dir: Path | None = None) -> dict[str, Any]:
    """Create the paired A/B research view from two complete per-sample reports."""
    a = json.loads((stage_a_dir / "per_sample.json").read_text(encoding="utf-8"))
    b = json.loads((stage_b_dir / "per_sample.json").read_text(encoding="utf-8"))
    a_by_idx, b_by_idx = ({row["idx"]: row for row in rows} for rows in (a, b))
    if set(a_by_idx) != set(b_by_idx):
        raise ValueError("A/B experiments must contain the same sample indices")
    paired = []
    transitions = Counter()
    groups: dict[str, Counter] = defaultdict(Counter)
    for idx in sorted(a_by_idx):
        left, right = a_by_idx[idx], b_by_idx[idx]
        if (left["level"], left["days"]) != (right["level"], right["days"]):
            raise ValueError(f"Metadata mismatch for idx {idx}")
        a_pass, b_pass = bool(left["final_pass"]), bool(right["final_pass"])
        transition = f"A_{'pass' if a_pass else 'fail'}_to_B_{'pass' if b_pass else 'fail'}"
        transitions[transition] += 1
        row = {"idx": idx, "level": left["level"], "days": left["days"],
               "a_final_pass": a_pass, "b_final_pass": b_pass, "transition": transition}
        paired.append(row)
        for key in ("all", f"level:{left['level']}", f"days:{left['days']}", f"cell:{left['level']}:{left['days']}"):
            groups[key]["total"] += 1; groups[key]["a_pass"] += a_pass; groups[key]["b_pass"] += b_pass
    a_summary = json.loads((stage_a_dir / "summary.json").read_text(encoding="utf-8"))
    b_summary = json.loads((stage_b_dir / "summary.json").read_text(encoding="utf-8"))
    metrics = ("delivery_rate", "commonsense_micro_pass_rate", "commonsense_macro_pass_rate",
               "hard_micro_pass_rate", "hard_macro_pass_rate", "final_pass_rate")
    constraint_names = sorted(set(a_summary.get("constraint_pass", {})) | set(b_summary.get("constraint_pass", {})))
    constraint_delta = {}
    for name in constraint_names:
        a_rate = a_summary.get("constraint_pass", {}).get(name, {}).get("rate")
        b_rate = b_summary.get("constraint_pass", {}).get(name, {}).get("rate")
        constraint_delta[name] = {"stage_a": a_rate, "stage_b": b_rate,
                                  "delta": b_rate - a_rate if a_rate is not None and b_rate is not None else None}
    usage_keys = sorted(set(a_summary.get("usage", {})) | set(b_summary.get("usage", {})))
    report = {
        "comparison_type": "sole-planning_to_two-stage_system_gap",
        "causal_tool_effect_claimed": False,
        "stage_a": str(stage_a_dir), "stage_b": str(stage_b_dir), "total": len(paired),
        "metric_delta_b_minus_a": {key: b_summary[key] - a_summary[key] for key in metrics},
        "constraint_rate_delta_b_minus_a": constraint_delta,
        "cost_delta_b_minus_a": {
            "usage": {key: b_summary.get("usage", {}).get(key, 0) - a_summary.get("usage", {}).get(key, 0)
                      for key in usage_keys},
            "mean_latency_seconds": (b_summary.get("latency_seconds", {}).get("mean") or 0) -
                                    (a_summary.get("latency_seconds", {}).get("mean") or 0),
            "stage_b_react": b_summary.get("react"),
        },
        "transitions": dict(transitions),
        "groups": {key: {"total": value["total"], "a_final_pass_rate": value["a_pass"] / value["total"],
                         "b_final_pass_rate": value["b_pass"] / value["total"],
                         "delta": (value["b_pass"] - value["a_pass"]) / value["total"]}
                   for key, value in groups.items()},
        "paired_samples": paired,
    }
    destination = output_dir or stage_b_dir
    _atomic_json(destination / "stage_a_b_comparison.json", report)
    return report


def compare_mechanism_experiments(stage_b_dir: Path, stage_c_dir: Path,
                                  output_dir: Path | None = None) -> dict[str, Any]:
    """Paired B/C comparison where explicit planning is the intended added mechanism."""
    b = json.loads((stage_b_dir / "per_sample.json").read_text(encoding="utf-8"))
    c = json.loads((stage_c_dir / "per_sample.json").read_text(encoding="utf-8"))
    b_by_idx, c_by_idx = ({row["idx"]: row for row in rows} for rows in (b, c))
    if set(b_by_idx) != set(c_by_idx):
        raise ValueError("B/C experiments must contain the same sample indices")
    paired, transitions = [], Counter()
    groups: dict[str, Counter] = defaultdict(Counter)
    for idx in sorted(b_by_idx):
        left, right = b_by_idx[idx], c_by_idx[idx]
        if (left["level"], left["days"]) != (right["level"], right["days"]):
            raise ValueError(f"Metadata mismatch for idx {idx}")
        b_pass, c_pass = bool(left["final_pass"]), bool(right["final_pass"])
        transition = f"B_{'pass' if b_pass else 'fail'}_to_C_{'pass' if c_pass else 'fail'}"
        transitions[transition] += 1
        paired.append({"idx": idx, "level": left["level"], "days": left["days"],
                       "b_final_pass": b_pass, "c_final_pass": c_pass,
                       "transition": transition})
        for key in ("all", f"level:{left['level']}", f"days:{left['days']}",
                    f"cell:{left['level']}:{left['days']}"):
            groups[key]["total"] += 1; groups[key]["b_pass"] += b_pass; groups[key]["c_pass"] += c_pass
    b_summary = json.loads((stage_b_dir / "summary.json").read_text(encoding="utf-8"))
    c_summary = json.loads((stage_c_dir / "summary.json").read_text(encoding="utf-8"))
    metrics = ("delivery_rate", "commonsense_micro_pass_rate", "commonsense_macro_pass_rate",
               "hard_micro_pass_rate", "hard_macro_pass_rate", "final_pass_rate")
    usage_keys = sorted(set(b_summary.get("usage", {})) | set(c_summary.get("usage", {})))
    added_passes = transitions["B_fail_to_C_pass"] - transitions["B_pass_to_C_fail"]
    token_delta = c_summary.get("usage", {}).get("total_tokens", 0) - b_summary.get("usage", {}).get("total_tokens", 0)
    report = {
        "comparison_type": "explicit_planner_mechanism_comparison",
        "intended_added_mechanism": "one pre-tool explicit global planner call",
        "stage_b": str(stage_b_dir), "stage_c": str(stage_c_dir), "total": len(paired),
        "metric_delta_c_minus_b": {key: c_summary[key] - b_summary[key] for key in metrics},
        "cost_delta_c_minus_b": {
            "usage": {key: c_summary.get("usage", {}).get(key, 0) - b_summary.get("usage", {}).get(key, 0)
                      for key in usage_keys},
            "mean_latency_seconds": (c_summary.get("latency_seconds", {}).get("mean") or 0) -
                                    (b_summary.get("latency_seconds", {}).get("mean") or 0),
            "mean_tool_calls": (c_summary.get("react", {}).get("tool_calls", {}).get("mean") or 0) -
                               (b_summary.get("react", {}).get("tool_calls", {}).get("mean") or 0),
            "mean_model_calls": (c_summary.get("react", {}).get("model_calls", {}).get("mean") or 0) -
                                (b_summary.get("react", {}).get("model_calls", {}).get("mean") or 0),
        },
        "efficiency": {"net_additional_final_passes": added_passes,
                       "token_delta_per_net_additional_pass": token_delta / added_passes if added_passes else None,
                       "final_pass_percentage_points_per_million_token_delta":
                           ((c_summary["final_pass_rate"] - b_summary["final_pass_rate"]) * 100 /
                            (token_delta / 1_000_000)) if token_delta else None},
        "transitions": dict(transitions),
        "groups": {key: {"total": value["total"],
                          "b_final_pass_rate": value["b_pass"] / value["total"],
                          "c_final_pass_rate": value["c_pass"] / value["total"],
                          "delta": (value["c_pass"] - value["b_pass"]) / value["total"]}
                   for key, value in groups.items()},
        "stage_c_planner": c_summary.get("planner"),
        "paired_samples": paired,
    }
    destination = output_dir or stage_c_dir
    _atomic_json(destination / "stage_b_c_comparison.json", report)
    return report


def compare_verifier_experiments(stage_c_dir: Path, stage_d_dir: Path,
                                 output_dir: Path | None = None) -> dict[str, Any]:
    """Paired C/D comparison with exact McNemar and deterministic paired bootstrap CI."""
    c_rows = json.loads((stage_c_dir / "per_sample.json").read_text(encoding="utf-8"))
    d_rows = json.loads((stage_d_dir / "per_sample.json").read_text(encoding="utf-8"))
    c_by, d_by = ({row["idx"]: row for row in rows} for rows in (c_rows, d_rows))
    if set(c_by) != set(d_by): raise ValueError("C/D experiments must contain identical indices")
    paired, transitions = [], Counter(); groups: dict[str, Counter] = defaultdict(Counter)
    differences = []
    for idx in sorted(c_by):
        left, right = c_by[idx], d_by[idx]
        if (left["level"], left["days"]) != (right["level"], right["days"]):
            raise ValueError(f"Metadata mismatch for idx {idx}")
        cp, dp = bool(left["final_pass"]), bool(right["final_pass"])
        transition = f"C_{'pass' if cp else 'fail'}_to_D_{'pass' if dp else 'fail'}"
        transitions[transition] += 1; differences.append(int(dp) - int(cp))
        paired.append({"idx": idx, "level": left["level"], "days": left["days"],
                       "c_final_pass": cp, "d_final_pass": dp, "transition": transition})
        for key in ("all", f"level:{left['level']}", f"days:{left['days']}", f"cell:{left['level']}:{left['days']}"):
            groups[key]["total"] += 1; groups[key]["c_pass"] += cp; groups[key]["d_pass"] += dp
    b = transitions["C_pass_to_D_fail"]; c = transitions["C_fail_to_D_pass"]; discordant = b + c
    p_value = (min(1.0, 2 * sum(math.comb(discordant, k) for k in range(min(b, c) + 1)) / (2 ** discordant))
               if discordant else 1.0)
    rng = random.Random(SEED); boot = []
    if differences:
        for _ in range(10000): boot.append(sum(rng.choice(differences) for _ in differences) / len(differences))
        boot.sort(); ci = [boot[int(.025 * (len(boot)-1))], boot[int(.975 * (len(boot)-1))]]
    else: ci = [None, None]
    cs = json.loads((stage_c_dir / "summary.json").read_text(encoding="utf-8")); ds = json.loads((stage_d_dir / "summary.json").read_text(encoding="utf-8"))
    metrics = ("delivery_rate", "commonsense_micro_pass_rate", "commonsense_macro_pass_rate",
               "hard_micro_pass_rate", "hard_macro_pass_rate", "final_pass_rate")
    token_delta = ds.get("usage", {}).get("total_tokens", 0) - cs.get("usage", {}).get("total_tokens", 0)
    net = c - b
    report = {"comparison_type": "verifier_single_replan_mechanism_comparison",
              "intended_added_mechanism": "one verifier and at most one no-tool replan",
              "stage_c": str(stage_c_dir), "stage_d": str(stage_d_dir), "total": len(paired),
              "metric_delta_d_minus_c": {key: ds[key] - cs[key] for key in metrics},
              "transitions": dict(transitions),
              "paired_inference": {"mcnemar_exact_two_sided_p": p_value,
                    "discordant_c_pass_d_fail": b, "discordant_c_fail_d_pass": c,
                    "bootstrap_seed": SEED, "bootstrap_samples": 10000,
                    "final_pass_rate_difference_95pct_ci": ci},
              "cost": {"total_token_delta": token_delta,
                       "token_delta_per_net_additional_final_pass": token_delta / net if net else None},
              "groups": {key: {"total": value["total"],
                    "c_final_pass_rate": value["c_pass"] / value["total"],
                    "d_final_pass_rate": value["d_pass"] / value["total"],
                    "delta": (value["d_pass"] - value["c_pass"]) / value["total"]}
                    for key, value in groups.items()},
              "stage_d_verifier_replan": ds.get("verifier_replan"), "paired_samples": paired}
    _atomic_json((output_dir or stage_d_dir) / "stage_c_d_comparison.json", report)
    return report
