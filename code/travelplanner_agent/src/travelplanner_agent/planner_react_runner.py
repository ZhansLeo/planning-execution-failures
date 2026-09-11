from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .baselines import (PLANNER_MAX_OUTPUT_TOKENS, PLANNER_PROMPT_VERSION,
                        PlannerReactBaseline, build_planner_prompt,
                        planner_react_protocol_hash, planning_blueprint_shape)
from .evidence_audit import AUDIT_VERSION, build_evidence_audit
from .official_adapter import (load_query_sample, load_validation_sample, read_jsonl_row,
                               validate_evaluator_format, validate_generated_submission)
from .planner_audit import PLANNER_AUDIT_VERSION, build_planner_audit
from .react_runner import _shared_toolbox
from .react_tools import tool_schema_hash


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_directory(runs_dir: Path, model: str, split: str, index: int) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", model).strip("-") or "model"
    path = runs_dir / f"{stamp}_{safe}_planner-react_{split}_{index:03d}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def run_planner_react(repo: Path, runs_dir: Path, index: int, *, model: str, base_url: str,
                      timeout: float, max_retries: int, experiment_id: str | None = None,
                      attempt: int = 1, canonical_query: str | None = None,
                      max_tool_calls: int = 30, max_context_tokens: int = 56000,
                      max_output_tokens: int = 8000, split: str = "validation") -> dict[str, Any]:
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is required for a real Planner+ReAct run; no call was made.")
    sample = (load_validation_sample(repo, index, canonical_query=canonical_query)
              if split == "validation" else load_query_sample(split, index))
    task = {"idx": index if split == "train" else sample["index"], "query": sample["query"]}
    run_dir = _run_directory(runs_dir, model, split, index)
    config = {
        "baseline": "C_explicit_planner_react", "protocol_status": "candidate_train_only",
        "split": split, "index": index, "model": model, "base_url": base_url,
        "temperature": 0.0, "timeout_seconds": timeout, "max_retries": max_retries,
        "planner_prompt_version": PLANNER_PROMPT_VERSION,
        "planner_max_output_tokens": PLANNER_MAX_OUTPUT_TOKENS,
        "max_tool_calls": max_tool_calls, "max_context_tokens": max_context_tokens,
        "max_output_tokens": max_output_tokens,
        "prompt_protocol_hash": planner_react_protocol_hash(),
        "tool_schema_hash": tool_schema_hash(), "evidence_audit_version": AUDIT_VERSION,
        "planner_audit_version": PLANNER_AUDIT_VERSION, "experiment_id": experiment_id,
        "attempt": attempt, "api_key": "[provided via environment; never persisted]",
        "modules": {"tools": True, "react": True, "explicit_planner": True,
                    "verifier": False, "replan": False, "memory": False,
                    "reflection": False, "multi_agent": False,
                    "observation_compression": False, "scripted_retrieval": False},
    }
    _write_json(run_dir / "config.json", config)
    audit_reference = (sample["reference_information"] if split == "validation" else
                       read_jsonl_row(repo / "database/train_ref_info.jsonl", index - 1))
    _write_json(run_dir / "input.json", {
        "model_input": {"idx": task["idx"], "query": task["query"]},
        "model_sources": {"query_source": sample["sources"].get("query_source")},
        "posthoc_audit_source": str(repo / "database" / f"{split}_ref_info.jsonl"),
        "reference_information_exposed_to_model": False,
    })
    (run_dir / "planner_prompt.txt").write_text(build_planner_prompt(task), encoding="utf-8")
    _write_json(run_dir / "planner_schema.json", planning_blueprint_shape())
    try:
        baseline = PlannerReactBaseline(
            toolbox=_shared_toolbox(repo), model=model, base_url=base_url, timeout=timeout,
            max_retries=max_retries, max_tool_calls=max_tool_calls,
            max_context_tokens=max_context_tokens, max_output_tokens=max_output_tokens)
        generation = baseline.generate(task)
    except Exception as exc:
        retryable = type(exc).__name__ in {"APIConnectionError", "APITimeoutError", "RateLimitError",
                                           "InternalServerError", "ServiceUnavailableError"}
        status = {"status": "blocked", "stage": "planner_or_agent_run",
                  "error_type": type(exc).__name__, "error": str(exc),
                  "model_calls_attempted": 0 if isinstance(exc, ValueError) else 1,
                  "tool_calls": 0, "retryable": retryable,
                  "experiment_id": experiment_id, "attempt": attempt}
        audit = build_evidence_audit(trajectory=[], submission=None,
                                     reference_information=audit_reference,
                                     terminal_reason="planner_or_agent_run_error")
        _write_json(run_dir / "evidence_audit.json", audit)
        _write_json(run_dir / "planner_audit.json", {"audit_version": PLANNER_AUDIT_VERSION,
                    "reference_information_exposed_to_planner": False, "run_error": status})
        _write_json(run_dir / "status.json", status)
        return {"run_dir": str(run_dir), **status}

    (run_dir / "planner_raw_response.txt").write_text(generation.planner_raw_response, encoding="utf-8")
    if generation.planning_blueprint is not None:
        _write_json(run_dir / "planning_blueprint.json", generation.planning_blueprint)
    _write_json(run_dir / "planner_validation.json", generation.planner_validation)
    (run_dir / "raw_response.txt").write_text(generation.raw_response, encoding="utf-8")
    _write_json(run_dir / "trajectory.json", generation.trajectory)
    if generation.parsed_response is not None:
        _write_json(run_dir / "parsed_response.json", generation.parsed_response)
    schema = validate_generated_submission(generation.parsed_response,
                                           expected_idx=task["idx"], expected_query=task["query"])
    fmt = validate_evaluator_format(generation.parsed_response)
    evidence = build_evidence_audit(trajectory=generation.trajectory,
                                    submission=generation.parsed_response,
                                    reference_information=audit_reference,
                                    terminal_reason=generation.terminal_reason)
    planner_audit = build_planner_audit(
        query=task["query"], planner_raw_response=generation.planner_raw_response,
        blueprint=generation.planning_blueprint, validation=generation.planner_validation,
        planner_usage=generation.planner_usage,
        planner_latency_seconds=generation.planner_latency_seconds,
        planner_request_id=generation.planner_request_id, trajectory=generation.trajectory,
        submission=generation.parsed_response)
    _write_json(run_dir / "evidence_audit.json", evidence)
    _write_json(run_dir / "planner_audit.json", planner_audit)
    _write_json(run_dir / "validation.json", {"planner": generation.planner_validation,
                                               "schema": schema, "evaluator_format": fmt})
    ready = (generation.planner_validation["valid"] and schema["valid"] and fmt["valid"]
             and generation.terminal_reason == "final_response")
    if ready:
        (run_dir / "submission.jsonl").write_text(
            json.dumps(generation.parsed_response, ensure_ascii=False) + "\n", encoding="utf-8")
    status = {"status": "completed" if ready else "invalid_output",
              "stage": generation.terminal_reason,
              "model_calls_attempted": generation.model_calls,
              "planner_calls": 1, "execution_model_calls": max(0, generation.model_calls - 1),
              "tool_calls": generation.tool_calls, "latency_seconds": generation.latency_seconds,
              "planner_latency_seconds": generation.planner_latency_seconds,
              "usage": generation.usage, "planner_usage": generation.planner_usage,
              "schema_valid": schema["valid"], "evaluator_format_valid": fmt["valid"],
              "planner_valid": generation.planner_validation["valid"], "retryable": False,
              "experiment_id": experiment_id, "attempt": attempt}
    _write_json(run_dir / "status.json", status)
    return {"run_dir": str(run_dir), **status}
