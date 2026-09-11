from __future__ import annotations

import json
import random
import re
import time
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator
from openai import OpenAI

from .core import (
    DATA_ROOT,
    DEV_UIDS,
    MAX_CONTEXT_TOKENS,
    MAX_MODEL_ROUNDS,
    MAX_TOOL_CALLS,
    OFFICIAL_ROOT,
    PILOT_ID,
    PLANNER_SCHEMA,
    ROOT,
    RUNS_ROOT,
    ModelConfig,
    api_key,
    assert_oracle_absent,
    build_executor_prompt,
    build_planner_messages,
    call_model,
    create_pilot_manifest,
    exposed_tools,
    failed_evaluation,
    git_output,
    load_query,
    output_schema,
    parse_blueprint,
    pilot_root,
    run_ct_b,
    sha256_file,
    stable_hash,
    visible_query,
    write_json,
)


CT_C_PROTOCOL = "ct-c-structured-planner-v1.0-pilot"
EXPECTED_RESOLVED_MODEL = "deepseek-v4-flash"
PLANNER_MAX_TOKENS = 1500
PLANNER_PROMPT_VERSION = "ct-c-planner-zh-v1.0"


def _tools() -> list[dict[str, Any]]:
    import sys

    official = str(OFFICIAL_ROOT)
    if official not in sys.path:
        sys.path.insert(0, official)
    from agent_env.adapter import ChinaTravelEnvAdapter

    return exposed_tools(ChinaTravelEnvAdapter(lang="zh"))


def executor_invariant() -> dict[str, Any]:
    """Hashable protocol surface that must remain paired with frozen CT-B."""
    return {
        "tool_schema_hash": stable_hash(_tools()),
        "output_schema_sha256": sha256_file(OFFICIAL_ROOT / "chinatravel/evaluation/output_schema.json"),
        "max_tool_calls": MAX_TOOL_CALLS,
        "max_model_rounds": MAX_MODEL_ROUNDS,
        "context_limit": MAX_CONTEXT_TOKENS,
        "parallel_policy": "sequential_in_model_order",
        "finalization": "one_same-model_no-tools-json-turn",
        "thinking": "disabled",
        "response_format": "json_object",
        "parser": "strict-json-no-repair",
    }


def create_ct_c_manifest() -> dict[str, Any]:
    base = create_pilot_manifest()
    base_path = pilot_root() / "manifest.json"
    sample = base["samples"][0]
    _, query = load_query(sample["split"], sample["uid"])
    planner_messages = build_planner_messages(visible_query(query))
    manifest = {
        "experiment_id": PILOT_ID,
        "baseline": "CT-C_structured_planner_react",
        "protocol_version": CT_C_PROTOCOL,
        "status": "FROZEN",
        "base_ct_b_manifest_sha256": sha256_file(base_path),
        "samples": base["samples"],
        "sample_count": len(base["samples"]),
        "planner_prompt_version": PLANNER_PROMPT_VERSION,
        "planner_prompt_template_hash": stable_hash(planner_messages),
        "planner_schema_hash": stable_hash(PLANNER_SCHEMA),
        "planner_max_tokens": PLANNER_MAX_TOKENS,
        "requested_model": "deepseek-chat",
        "required_resolved_model": EXPECTED_RESOLVED_MODEL,
        "executor_invariant": executor_invariant(),
        "executor_invariant_hash": stable_hash(executor_invariant()),
        "official_commit": git_output("rev-parse", "HEAD"),
        "oracle_fields_hidden": base["oracle_fields_hidden"],
    }
    path = pilot_root() / "ct_c_manifest.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != manifest:
            raise RuntimeError("Frozen CT-C manifest differs from current protocol; refusing to mix runs.")
        return existing
    write_json(path, manifest)
    write_json(pilot_root() / "state_ct_c.json", {"completed": {}, "failures": {}})
    return manifest


def _planner_usage(response: Any, latency: float, attempts: int) -> dict[str, Any]:
    usage = response.usage
    return {
        "model_calls": 1,
        "api_attempts": attempts,
        "prompt_tokens": (usage.prompt_tokens or 0) if usage else 0,
        "completion_tokens": (usage.completion_tokens or 0) if usage else 0,
        "total_tokens": (usage.total_tokens or 0) if usage else 0,
        "latency_seconds": latency,
        "resolved_model": str(response.model),
    }


def _tool_categories(trajectory: list[dict[str, Any]]) -> set[str]:
    categories: set[str] = set()
    for entry in trajectory:
        for call in entry.get("executed_tools", []):
            name = call.get("tool_name", "").lower()
            if "attraction" in name:
                categories.add("attractions")
            if "restaurant" in name or "food" in name:
                categories.add("restaurants")
            if "accommodation" in name or "hotel" in name:
                categories.add("accommodations")
            if "train" in name or "flight" in name or "intercity" in name:
                categories.add("intercity_transport")
            if any(token in name for token in ("walk", "subway", "taxi", "route", "coordinate")):
                categories.add("inner_city_transport")
    return categories


def _oracle_categories(query: dict[str, Any]) -> set[str]:
    raw = json.dumps(query.get("hard_logic_py", []), ensure_ascii=False).lower()
    rules = {
        "trip_facts": ("people", "person", "day_count", "days"),
        "budget": ("cost", "budget"),
        "tickets": ("ticket",),
        "transportation": ("train", "flight", "airplane", "transport", "taxi", "subway"),
        "accommodation": ("accommodation", "hotel", "room"),
        "time": ("time", "open"),
        "meal": ("meal", "restaurant", "cuisine"),
        "attraction": ("attraction", "poi"),
        "preference": ("prefer", "preference"),
    }
    return {category for category, needles in rules.items() if any(needle in raw for needle in needles)}


@lru_cache(maxsize=1)
def _sandbox_entity_names() -> tuple[str, ...]:
    names: set[str] = set()
    database = OFFICIAL_ROOT / "chinatravel/environment/database"
    for category in ("attractions", "restaurants", "accommodations"):
        for path in (database / category).rglob("*.csv"):
            try:
                import pandas as pd
                frame = pd.read_csv(path, usecols=lambda column: column == "name")
                names.update(str(value) for value in frame.get("name", []) if isinstance(value, str) and len(value) >= 3)
            except Exception:
                continue
    return tuple(sorted(names, key=len, reverse=True))


def build_planner_audit(
    public_query: dict[str, Any], oracle_query: dict[str, Any], blueprint: dict[str, Any], run_dir: Path
) -> dict[str, Any]:
    text = str(public_query.get("nature_language", ""))
    facts = blueprint["trip_facts"]
    fact_checks = {
        key: facts.get(key) == public_query.get(key)
        for key in ("start_city", "target_city", "days", "people_number")
        if public_query.get(key) is not None
    }
    constraints = [*blueprint["hard_constraints"], *blueprint["soft_preferences"]]
    source_checks = [bool(item["source_text"]) and item["source_text"] in text for item in constraints]
    serialized = json.dumps(blueprint, ensure_ascii=False)
    forbidden_patterns = sorted(set(re.findall(r"(?:G|D|C)\d{1,5}|(?:MU|CA|CZ|HU|ZH|SC)\d{3,5}", serialized, re.I)))
    forbidden_entities = [name for name in _sandbox_entity_names() if name in serialized and name not in text]
    checklist_categories = {item["category"] for item in blueprint["retrieval_checklist"]}
    required = {"intercity_transport", "attractions", "restaurants", "inner_city_transport"}
    if int(public_query.get("days", 1)) > 1:
        required.add("accommodations")
    trajectory = []
    trajectory_path = run_dir / "trajectory.jsonl"
    if trajectory_path.exists():
        trajectory = [json.loads(line) for line in trajectory_path.read_text(encoding="utf-8").splitlines() if line]
    actual_categories = _tool_categories(trajectory)
    evaluator_ready = {}
    if (run_dir / "evaluator_ready.json").exists():
        evaluator_ready = json.loads((run_dir / "evaluator_ready.json").read_text(encoding="utf-8"))
    oracle_categories = _oracle_categories(oracle_query)
    blueprint_categories = {item["category"] for item in blueprint["hard_constraints"]}
    audit = {
        "trip_fact_consistency": fact_checks,
        "trip_fact_consistency_rate": sum(fact_checks.values()) / len(fact_checks) if fact_checks else 1.0,
        "hard_constraint_count": len(blueprint["hard_constraints"]),
        "soft_preference_count": len(blueprint["soft_preferences"]),
        "hard_constraint_categories": sorted(blueprint_categories),
        "source_text_checks": source_checks,
        "source_text_location_rate": sum(source_checks) / len(source_checks) if source_checks else 1.0,
        "checklist_categories": sorted(checklist_categories),
        "required_checklist_categories": sorted(required),
        "checklist_design_coverage": len(checklist_categories & required) / len(required),
        "actual_tool_categories": sorted(actual_categories),
        "executor_checklist_coverage": len(checklist_categories & actual_categories) / len(checklist_categories) if checklist_categories else 1.0,
        "unplanned_tool_category_rate": len(actual_categories - checklist_categories) / len(actual_categories) if actual_categories else 0.0,
        "forbidden_specific_transport_ids": forbidden_patterns,
        "forbidden_specific_sandbox_entities": forbidden_entities,
        "entity_isolation_pass": not forbidden_patterns and not forbidden_entities,
        "final_output_present": bool(evaluator_ready),
        "oracle_category_alignment": {
            "oracle_categories": sorted(oracle_categories),
            "covered_categories": sorted(oracle_categories & blueprint_categories),
            "coverage": len(oracle_categories & blueprint_categories) / len(oracle_categories) if oracle_categories else 1.0,
            "post_run_diagnostic_only": True,
        },
    }
    audit["audit_flags"] = [
        *(["planner_entity_violation"] if not audit["entity_isolation_pass"] else []),
        *(["planner_source_text_mismatch"] if audit["source_text_location_rate"] < 1 else []),
        *(["planner_trip_fact_mismatch"] if audit["trip_fact_consistency_rate"] < 1 else []),
        *(["retrieval_checklist_incomplete"] if audit["checklist_design_coverage"] < 1 else []),
        *(["blueprint_execution_deviation"] if audit["executor_checklist_coverage"] < 1 else []),
    ]
    audit["audit_pass"] = not audit["audit_flags"]
    assert_oracle_absent({"public_query": public_query, "blueprint": blueprint, "trajectory": trajectory})
    return audit


def _planner_failure_run(split: str, uid: str, public_query: dict[str, Any], messages: list[dict[str, Any]], raw: str, usage: dict[str, Any], reason: str) -> Path:
    now = datetime.now(timezone.utc)
    run_dir = RUNS_ROOT / f"ct-c-{now.strftime('%Y%m%dT%H%M%SZ')}-{uid}"
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "experiment": "CT-C_structured_planner_react", "protocol_version": CT_C_PROTOCOL,
        "run_id": run_dir.name, "split": split, "uid": uid, "terminal_status": "planner_non_delivery",
        "planner_failure_reason": reason, "resolved_response_models": [usage.get("resolved_model")],
        "official_commit": git_output("rev-parse", "HEAD"), "oracle_fields_hidden": ["hard_logic", "hard_logic_nl", "hard_logic_py"],
    }
    write_json(run_dir / "manifest.json", manifest)
    write_json(run_dir / "query_visible.json", public_query)
    write_json(run_dir / "planner_prompt.json", messages)
    (run_dir / "planner_raw_response.txt").write_text(raw, encoding="utf-8")
    write_json(run_dir / "planner_usage.json", usage)
    write_json(run_dir / "planner_audit.json", {"valid": False, "reason": reason})
    write_json(run_dir / "parse_result.json", {"parsed": False, "schema_errors": [reason]})
    write_json(run_dir / "evaluation.json", failed_evaluation(split, uid, reason))
    combined = {**usage, "tool_calls": 0, "termination": "planner_non_delivery", "max_bundle_size": 0}
    write_json(run_dir / "usage.json", combined)
    write_json(run_dir / "failure_audit.json", {"primary": "planner_non_delivery", "flags": ["planner_non_delivery"], "reason": reason})
    return run_dir


def run_ct_c(split: str, uid: str, *, milestone: str = "single_sample", experiment_id: str | None = None) -> Path:
    selected_uid, oracle_query = load_query(split, uid)
    public_query = visible_query(oracle_query)
    messages = build_planner_messages(public_query)
    assert_oracle_absent(messages)
    config = ModelConfig.from_env()
    client = OpenAI(api_key=api_key(), base_url=config.base_url, timeout=config.timeout, max_retries=0)
    response, latency, attempts = call_model(client, config, messages, None, max_tokens=PLANNER_MAX_TOKENS)
    raw = response.choices[0].message.content or ""
    planner_usage = _planner_usage(response, latency, attempts)
    if planner_usage["resolved_model"] != EXPECTED_RESOLVED_MODEL:
        return _planner_failure_run(split, selected_uid, public_query, messages, raw, planner_usage, f"resolved_model_mismatch: expected {EXPECTED_RESOLVED_MODEL}, got {planner_usage['resolved_model']}")
    try:
        blueprint = parse_blueprint(raw)
    except Exception as exc:
        return _planner_failure_run(split, selected_uid, public_query, messages, raw, planner_usage, f"{type(exc).__name__}: {exc}")
    manifest_extra = {
        "planner_prompt_version": PLANNER_PROMPT_VERSION,
        "planner_schema_hash": stable_hash(PLANNER_SCHEMA),
        "planner_prompt_hash": stable_hash(messages),
        "planner_max_tokens": PLANNER_MAX_TOKENS,
        "required_resolved_model": EXPECTED_RESOLVED_MODEL,
        "executor_invariant_hash": stable_hash(executor_invariant()),
    }
    run_dir = run_ct_b(
        split, selected_uid, milestone=milestone, experiment_id=experiment_id,
        blueprint=blueprint, run_prefix="ct-c", experiment_name="CT-C_structured_planner_react",
        protocol_version=CT_C_PROTOCOL, manifest_extra=manifest_extra,
    )
    executor_usage = json.loads((run_dir / "usage.json").read_text(encoding="utf-8"))
    write_json(run_dir / "executor_usage.json", executor_usage)
    write_json(run_dir / "planner_prompt.json", messages)
    (run_dir / "planner_raw_response.txt").write_text(raw, encoding="utf-8")
    write_json(run_dir / "planning_blueprint.json", blueprint)
    write_json(run_dir / "planner_usage.json", planner_usage)
    audit = build_planner_audit(public_query, oracle_query, blueprint, run_dir)
    total_tokens = planner_usage["total_tokens"] + executor_usage.get("total_tokens", 0)
    combined = {
        "planner": planner_usage, "executor": executor_usage,
        "model_calls": 1 + executor_usage.get("model_calls", 0),
        "api_attempts": planner_usage["api_attempts"] + executor_usage.get("api_attempts", 0),
        "prompt_tokens": planner_usage["prompt_tokens"] + executor_usage.get("prompt_tokens", 0),
        "completion_tokens": planner_usage["completion_tokens"] + executor_usage.get("completion_tokens", 0),
        "total_tokens": total_tokens, "tool_calls": executor_usage.get("tool_calls", 0),
        "latency_seconds": planner_usage["latency_seconds"] + executor_usage.get("latency_seconds", 0),
        "termination": executor_usage.get("termination"), "max_bundle_size": executor_usage.get("max_bundle_size", 0),
        "planner_cost_fraction_tokens": planner_usage["total_tokens"] / total_tokens if total_tokens else 0.0,
    }
    audit["planner_usage"] = planner_usage
    audit["planner_cost_fraction_tokens"] = combined["planner_cost_fraction_tokens"]
    write_json(run_dir / "planner_audit.json", audit)
    write_json(run_dir / "usage.json", combined)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    resolved = set(manifest.get("resolved_response_models", [])) | {planner_usage["resolved_model"]}
    manifest["resolved_response_models"] = sorted(resolved)
    if resolved != {EXPECTED_RESOLVED_MODEL}:
        manifest["terminal_status"] = "resolved_model_mismatch"
    write_json(run_dir / "manifest.json", manifest)
    evaluation = json.loads((run_dir / "evaluation.json").read_text(encoding="utf-8"))
    if evaluation.get("all_pass"):
        primary = "success"
    elif executor_usage.get("termination") in {"max_steps", "max_model_rounds", "repeated_call", "tool_budget_exceeded", "context_limit"}:
        primary = "agent_control_non_delivery"
    elif audit["executor_checklist_coverage"] < 1:
        primary = "information_acquisition_failure"
    elif audit["trip_fact_consistency_rate"] < 1:
        primary = "blueprint_execution_deviation"
    elif evaluation.get("schema_pass"):
        primary = "constraint_satisfaction_failure"
    else:
        primary = "execution_consistency_failure"
    write_json(run_dir / "failure_audit.json", {"primary": primary, "flags": list(dict.fromkeys([primary, *audit["audit_flags"]]))})
    return run_dir


def run_development_ct_c(*, resume: bool = True) -> dict[str, Any]:
    path = ROOT / "experiments" / "ct-c-development-state.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"completed": {}, "failures": {}}
    if state["completed"] and not resume:
        raise RuntimeError("Development already started; pass resume.")
    for uid in sorted(DEV_UIDS):
        if uid in state["completed"]:
            continue
        try:
            run_dir = run_ct_c("easy", uid, milestone="development", experiment_id="ct-c-development")
            state["completed"][uid] = run_dir.name
        except Exception as exc:
            state["failures"][uid] = {"type": type(exc).__name__, "message": str(exc)}
        write_json(path, state)
    return state


def run_pilot_ct_c(*, resume: bool) -> dict[str, Any]:
    manifest = create_ct_c_manifest()
    state_path = pilot_root() / "state_ct_c.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state["completed"] and not resume:
        raise RuntimeError("CT-C pilot already started; pass --resume.")
    for sample in manifest["samples"]:
        key = f"{sample['split']}:{sample['uid']}"
        if key in state["completed"]:
            continue
        try:
            run_dir = run_ct_c(sample["split"], sample["uid"], milestone="12_sample_pilot", experiment_id=PILOT_ID)
            state["completed"][key] = run_dir.name
            state["failures"].pop(key, None)
        except Exception as exc:
            state["failures"][key] = {"type": type(exc).__name__, "message": str(exc)}
        write_json(state_path, state)
    return state


def _row(sample: dict[str, str], run_name: str | None) -> dict[str, Any]:
    if not run_name:
        return {**sample, "delivery": False, "terminal": "not_completed"}
    run_dir = RUNS_ROOT / run_name
    usage = json.loads((run_dir / "usage.json").read_text(encoding="utf-8"))
    evaluation = json.loads((run_dir / "evaluation.json").read_text(encoding="utf-8"))
    audit = json.loads((run_dir / "planner_audit.json").read_text(encoding="utf-8"))
    return {
        **sample, "run_id": run_name, "delivery": bool(evaluation.get("schema_pass")),
        "environment_pass": bool(evaluation.get("commonsense_pass")), "logical_pass": bool(evaluation.get("logical_pass")),
        "all_pass": bool(evaluation.get("all_pass")), "environment_micro": evaluation.get("commonsense_micro", 0),
        "environment_macro": evaluation.get("commonsense_macro", 0), "logical_micro": evaluation.get("logical_micro", 0),
        "logical_macro": evaluation.get("logical_macro", 0), "conditional_logical_micro": evaluation.get("conditional_logical_micro", 0),
        "conditional_logical_macro": evaluation.get("conditional_logical_macro", 0), "model_calls": usage.get("model_calls", 0),
        "tool_calls": usage.get("tool_calls", 0), "total_tokens": usage.get("total_tokens", 0), "latency_seconds": usage.get("latency_seconds", 0),
        "planner_tokens": usage.get("planner", {}).get("total_tokens", usage.get("total_tokens", 0) if usage.get("termination") == "planner_non_delivery" else 0),
        "executor_tokens": usage.get("executor", {}).get("total_tokens", 0), "terminal": usage.get("termination"),
        "max_bundle_size": usage.get("max_bundle_size", 0), "checklist_coverage": audit.get("executor_checklist_coverage", 0),
        "oracle_category_alignment": audit.get("oracle_category_alignment", {}).get("coverage", 0),
    }


def aggregate_pilot_ct_c() -> dict[str, Any]:
    manifest = create_ct_c_manifest()
    state = json.loads((pilot_root() / "state_ct_c.json").read_text(encoding="utf-8"))
    rows = [_row(sample, state["completed"].get(f"{sample['split']}:{sample['uid']}")) for sample in manifest["samples"]]
    completed = [row for row in rows if row.get("run_id")]
    def mean(field: str, subset: list[dict[str, Any]] = completed) -> float:
        return sum(float(row.get(field, 0) or 0) for row in subset) / len(subset) if subset else 0.0
    def rate(field: str, subset: list[dict[str, Any]] = completed) -> float:
        return sum(bool(row.get(field)) for row in subset) / len(subset) if subset else 0.0
    by_split = {}
    for split in ("easy", "medium", "human"):
        subset = [row for row in completed if row["split"] == split]
        by_split[split] = {"count": len(subset), "delivery_rate": rate("delivery", subset), "environment_pass_rate": rate("environment_pass", subset), "logical_pass_rate": rate("logical_pass", subset), "all_pass_rate": rate("all_pass", subset), "mean_tokens": mean("total_tokens", subset), "mean_tool_calls": mean("tool_calls", subset), "mean_latency_seconds": mean("latency_seconds", subset)}
    terminals: dict[str, int] = {}
    failure_categories: dict[str, int] = {}
    for row in completed:
        terminals[row["terminal"]] = terminals.get(row["terminal"], 0) + 1
        failure = json.loads((RUNS_ROOT / row["run_id"] / "failure_audit.json").read_text(encoding="utf-8"))
        primary = failure.get("primary", "unknown")
        failure_categories[primary] = failure_categories.get(primary, 0) + 1
    summary = {
        "experiment_id": PILOT_ID, "protocol_version": CT_C_PROTOCOL, "planned": len(rows), "completed": len(completed),
        "delivery_rate": rate("delivery"), "environment_pass_rate": rate("environment_pass"), "logical_pass_rate": rate("logical_pass"),
        "all_pass_rate": rate("all_pass"), "total_tokens": sum(row.get("total_tokens", 0) for row in completed),
        "mean_tokens": mean("total_tokens"), "mean_planner_tokens": mean("planner_tokens"), "mean_executor_tokens": mean("executor_tokens"),
        "mean_tool_calls": mean("tool_calls"), "mean_latency_seconds": mean("latency_seconds"), "mean_checklist_coverage": mean("checklist_coverage"),
        "mean_oracle_category_alignment": mean("oracle_category_alignment"), "terminal_counts": terminals,
        "failure_category_counts": failure_categories, "by_split": by_split, "rows": rows,
    }
    write_json(pilot_root() / "ct_c_summary.json", summary)
    return summary


def _bootstrap_delta(pairs: list[tuple[float, float]], seed: int = 20260904, iterations: int = 10000) -> dict[str, float]:
    if not pairs:
        return {"estimate": 0.0, "low": 0.0, "high": 0.0}
    rng = random.Random(seed)
    deltas = []
    for _ in range(iterations):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        deltas.append(sum(c - b for b, c in sample) / len(sample))
    deltas.sort()
    return {"estimate": sum(c - b for b, c in pairs) / len(pairs), "low": deltas[int(iterations * .025)], "high": deltas[int(iterations * .975)]}


def compare_pilot() -> dict[str, Any]:
    b = json.loads((pilot_root() / "ct_b_summary.json").read_text(encoding="utf-8"))
    c = aggregate_pilot_ct_c()
    b_rows = {(row["split"], row["uid"]): row for row in b["rows"]}
    c_rows = {(row["split"], row["uid"]): row for row in c["rows"]}
    keys = [(sample["split"], sample["uid"]) for sample in create_pilot_manifest()["samples"]]
    if set(b_rows) != set(c_rows) or len(keys) != 12:
        raise RuntimeError("CT-B/CT-C paired sample mismatch.")
    transitions = {}
    for metric in ("delivery", "all_pass"):
        counts = {"fail_to_fail": 0, "fail_to_pass": 0, "pass_to_fail": 0, "pass_to_pass": 0}
        for key in keys:
            before, after = bool(b_rows[key].get(metric)), bool(c_rows[key].get(metric))
            counts[("pass" if before else "fail") + "_to_" + ("pass" if after else "fail")] += 1
        transitions[metric] = counts
    deltas = {}
    for field in ("total_tokens", "tool_calls", "latency_seconds"):
        pairs = [(float(b_rows[key].get(field, 0)), float(c_rows[key].get(field, 0))) for key in keys]
        deltas[field] = _bootstrap_delta(pairs)
    result = {
        "comparison": "CT-B_query_only_react -> CT-C_structured_planner_react",
        "paired_n": 12, "samples_identical": True, "transitions": transitions,
        "delivery_delta_bootstrap_95ci": _bootstrap_delta([(float(b_rows[key]["delivery"]), float(c_rows[key]["delivery"])) for key in keys]),
        "all_pass_delta_bootstrap_95ci": _bootstrap_delta([(float(b_rows[key]["all_pass"]), float(c_rows[key]["all_pass"])) for key in keys]),
        "mean_cost_deltas_bootstrap_95ci": deltas,
        "token_cost_per_net_new_delivery": "not_defined" if transitions["delivery"]["fail_to_pass"] <= transitions["delivery"]["pass_to_fail"] else (c["total_tokens"] - b["total_tokens"]) / (transitions["delivery"]["fail_to_pass"] - transitions["delivery"]["pass_to_fail"]),
        "token_cost_per_net_new_all_pass": "not_defined" if transitions["all_pass"]["fail_to_pass"] <= transitions["all_pass"]["pass_to_fail"] else (c["total_tokens"] - b["total_tokens"]) / (transitions["all_pass"]["fail_to_pass"] - transitions["all_pass"]["pass_to_fail"]),
        "ct_b": {key: b[key] for key in ("delivery_rate", "environment_pass_rate", "logical_pass_rate", "all_pass_rate", "mean_tokens", "mean_tool_calls", "mean_latency_seconds")},
        "ct_c": {key: c[key] for key in ("delivery_rate", "environment_pass_rate", "logical_pass_rate", "all_pass_rate", "mean_tokens", "mean_tool_calls", "mean_latency_seconds")},
        "interpretation_limit": "n=12; descriptive paired evidence only. CT-C changes only the added pre-tool structured Planner.",
    }
    write_json(pilot_root() / "ct_b_c_comparison.json", result)
    return result
