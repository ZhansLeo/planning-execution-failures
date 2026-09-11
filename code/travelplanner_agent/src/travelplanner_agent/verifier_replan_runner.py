"""Run one independent Stage-D Planner -> ReAct -> Verifier -> optional Replan sample."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .baselines import VerifierReplanBaseline, build_planner_prompt, planning_blueprint_shape
from .evidence_audit import AUDIT_VERSION, build_evidence_audit
from .official_adapter import (load_query_sample, load_validation_sample, read_jsonl_row,
                               validate_evaluator_format, validate_generated_submission)
from .planner_audit import PLANNER_AUDIT_VERSION, build_planner_audit
from .react_runner import _shared_toolbox
from .react_tools import tool_schema_hash
from .verifier_replan import (EVIDENCE_CATALOG_VERSION, REPLAN_MAX_OUTPUT_TOKENS,
                              REPLAN_PROMPT_VERSION, VERIFIER_AUDIT_VERSION,
                              VERIFIER_MAX_OUTPUT_TOKENS, VERIFIER_PROMPT_VERSION,
                              verifier_replan_protocol_hash, verifier_report_shape)


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_dir(root: Path, model: str, split: str, index: int) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", model).strip("-") or "model"
    path = root / f"{stamp}_{safe}_verifier-replan_{split}_{index:03d}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def run_verifier_replan(repo: Path, runs_dir: Path, index: int, *, model: str,
                        base_url: str, timeout: float, max_retries: int,
                        experiment_id: str | None = None, attempt: int = 1,
                        canonical_query: str | None = None, max_tool_calls: int = 30,
                        max_context_tokens: int = 56000, max_output_tokens: int = 8000,
                        split: str = "validation") -> dict[str, Any]:
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is required for a real Stage-D run; no call was made.")
    sample = (load_validation_sample(repo, index, canonical_query=canonical_query)
              if split == "validation" else load_query_sample(split, index))
    task = {"idx": index if split == "train" else sample["index"], "query": sample["query"]}
    run_dir = _run_dir(runs_dir, model, split, index)
    reference = (sample["reference_information"] if split == "validation" else
                 read_jsonl_row(repo / "database/train_ref_info.jsonl", index - 1))
    config = {"baseline": "D_verifier_single_replan", "protocol_status": "candidate_train_only",
              "split": split, "index": index, "model": model, "base_url": base_url,
              "temperature": 0.0, "timeout_seconds": timeout, "max_retries": max_retries,
              "max_tool_calls": max_tool_calls, "max_context_tokens": max_context_tokens,
              "max_output_tokens": max_output_tokens,
              "verifier_prompt_version": VERIFIER_PROMPT_VERSION,
              "replan_prompt_version": REPLAN_PROMPT_VERSION,
              "verifier_max_output_tokens": VERIFIER_MAX_OUTPUT_TOKENS,
              "replan_max_output_tokens": REPLAN_MAX_OUTPUT_TOKENS,
              "protocol_hash": verifier_replan_protocol_hash(),
              "tool_schema_hash": tool_schema_hash(), "evidence_audit_version": AUDIT_VERSION,
              "planner_audit_version": PLANNER_AUDIT_VERSION,
              "verifier_audit_version": VERIFIER_AUDIT_VERSION,
              "evidence_catalog_version": EVIDENCE_CATALOG_VERSION,
              "experiment_id": experiment_id, "attempt": attempt,
              "api_key": "[provided via environment; never persisted]",
              "modules": {"tools": True, "react": True, "explicit_planner": True,
                          "verifier": True, "single_replan": True, "memory": False,
                          "reflection": False, "multi_agent": False,
                          "observation_compression": False, "scripted_retrieval": False}}
    _json(run_dir / "config.json", config)
    _json(run_dir / "input.json", {"model_input": task,
          "posthoc_audit_source": str(repo / "database" / f"{split}_ref_info.jsonl"),
          "reference_information_exposed_to_model": False,
          "official_evaluator_exposed_to_model": False})
    (run_dir / "planner_prompt.txt").write_text(build_planner_prompt(task), encoding="utf-8")
    _json(run_dir / "planner_schema.json", planning_blueprint_shape())
    _json(run_dir / "verifier_schema.json", verifier_report_shape())
    try:
        result = VerifierReplanBaseline(toolbox=_shared_toolbox(repo), model=model,
            base_url=base_url, timeout=timeout, max_retries=max_retries,
            max_tool_calls=max_tool_calls, max_context_tokens=max_context_tokens,
            max_output_tokens=max_output_tokens).generate(task)
    except Exception as exc:
        retryable = type(exc).__name__ in {"APIConnectionError", "APITimeoutError", "RateLimitError",
                                           "InternalServerError", "ServiceUnavailableError"}
        status = {"status": "blocked", "stage": "stage_d_run", "error_type": type(exc).__name__,
                  "error": str(exc), "retryable": retryable, "experiment_id": experiment_id,
                  "attempt": attempt, "tool_calls": 0, "model_calls_attempted": 0}
        _json(run_dir / "status.json", status)
        return {"run_dir": str(run_dir), **status}

    text_files = {"planner_raw_response.txt": result.planner_raw_response,
                  "candidate_raw_response.txt": result.candidate_raw_response,
                  "raw_response.txt": result.raw_response,
                  "verifier_raw_response.txt": result.verifier_raw_response}
    if result.verifier_prompt is not None: text_files["verifier_prompt.txt"] = result.verifier_prompt
    if result.replan_prompt is not None: text_files["replan_prompt.txt"] = result.replan_prompt
    if result.replan_raw_response: text_files["replan_raw_response.txt"] = result.replan_raw_response
    for name, value in text_files.items(): (run_dir / name).write_text(value, encoding="utf-8")
    for name, value in {"planning_blueprint.json": result.planning_blueprint,
                        "planner_validation.json": result.planner_validation,
                        "trajectory.json": result.trajectory,
                        "candidate_parsed_response.json": result.candidate_parsed_response,
                        "parsed_response.json": result.parsed_response,
                        "evidence_catalog.json": result.evidence_catalog,
                        "verifier_report.json": result.verifier_report,
                        "repair_decision.json": result.repair_decision}.items():
        if value is not None: _json(run_dir / name, value)
    schema = validate_generated_submission(result.parsed_response, expected_idx=task["idx"], expected_query=task["query"])
    fmt = validate_evaluator_format(result.parsed_response)
    ready = bool(schema["valid"] and fmt["valid"] and result.terminal_reason == "final_response")
    if ready:
        (run_dir / "submission.jsonl").write_text(json.dumps(result.parsed_response, ensure_ascii=False) + "\n", encoding="utf-8")
    candidate_schema = validate_generated_submission(result.candidate_parsed_response,
                        expected_idx=task["idx"], expected_query=task["query"])
    candidate_fmt = validate_evaluator_format(result.candidate_parsed_response)
    if candidate_schema["valid"] and candidate_fmt["valid"]:
        (run_dir / "candidate_submission.jsonl").write_text(json.dumps(result.candidate_parsed_response, ensure_ascii=False) + "\n", encoding="utf-8")
    _json(run_dir / "validation.json", {"planner": result.planner_validation, "schema": schema,
                                         "evaluator_format": fmt, "candidate_schema": candidate_schema,
                                         "candidate_evaluator_format": candidate_fmt,
                                         "verifier": result.verifier_validation})
    _json(run_dir / "evidence_audit.json", build_evidence_audit(trajectory=result.trajectory,
          submission=result.parsed_response, reference_information=reference,
          terminal_reason=result.terminal_reason))
    _json(run_dir / "planner_audit.json", build_planner_audit(query=task["query"],
          planner_raw_response=result.planner_raw_response, blueprint=result.planning_blueprint,
          validation=result.planner_validation, planner_usage=result.planner_usage,
          planner_latency_seconds=result.planner_latency_seconds,
          planner_request_id=result.planner_request_id, trajectory=result.trajectory,
          submission=result.candidate_parsed_response))
    verifier_audit = {"audit_version": VERIFIER_AUDIT_VERSION,
          "reference_information_exposed_to_model": False, "evaluator_exposed_to_model": False,
          "upstream_terminal_reason": result.upstream_terminal_reason,
          "candidate_valid": bool(candidate_schema["valid"] and candidate_fmt["valid"]),
          "verifier_called": result.verifier_prompt is not None,
          "verifier_validation": result.verifier_validation,
          "verifier_grounding_errors": result.verifier_validation.get("invalid_evidence_refs", []),
          "replan_called": result.replan_prompt is not None, "repair_decision": result.repair_decision}
    _json(run_dir / "verifier_audit.json", verifier_audit)
    status = {"status": "completed" if ready else "invalid_output", "stage": result.terminal_reason,
              "upstream_stage": result.upstream_terminal_reason,
              "model_calls_attempted": result.model_calls, "tool_calls": result.tool_calls,
              "planner_calls": 1, "verifier_calls": int(result.verifier_prompt is not None),
              "replan_calls": int(result.replan_prompt is not None),
              "latency_seconds": result.latency_seconds,
              "planner_latency_seconds": result.planner_latency_seconds,
              "verifier_latency_seconds": result.verifier_latency_seconds,
              "replan_latency_seconds": result.replan_latency_seconds,
              "usage": result.usage, "planner_usage": result.planner_usage,
              "verifier_usage": result.verifier_usage, "replan_usage": result.replan_usage,
              "schema_valid": schema["valid"], "evaluator_format_valid": fmt["valid"],
              "planner_valid": result.planner_validation["valid"], "retryable": False,
              "experiment_id": experiment_id, "attempt": attempt}
    _json(run_dir / "status.json", status)
    return {"run_dir": str(run_dir), **status}
