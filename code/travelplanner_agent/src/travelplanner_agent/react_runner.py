from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .baselines import ReactBaseline, build_react_prompt, react_protocol_hash
from .evidence_audit import AUDIT_VERSION, build_evidence_audit
from .official_adapter import load_query_sample, load_validation_sample, read_jsonl_row, validate_evaluator_format, validate_generated_submission
from .react_tools import OfficialToolbox, tool_schema_hash

_TOOLBOX_CACHE: dict[str, OfficialToolbox] = {}


def _shared_toolbox(repo: Path) -> OfficialToolbox:
    key = str(repo.resolve())
    if key not in _TOOLBOX_CACHE:
        _TOOLBOX_CACHE[key] = OfficialToolbox(repo)
    return _TOOLBOX_CACHE[key]


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_directory(runs_dir: Path, model: str, split: str, index: int) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", model).strip("-") or "model"
    path = runs_dir / f"{stamp}_{safe}_react_{split}_{index:03d}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def run_react(repo: Path, runs_dir: Path, index: int, *, model: str, base_url: str,
              timeout: float, max_retries: int, experiment_id: str | None = None,
              attempt: int = 1, canonical_query: str | None = None,
              max_tool_calls: int = 30, max_context_tokens: int = 56000,
              max_output_tokens: int = 8000, split: str = "validation") -> dict[str, Any]:
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is required for a real ReAct run; no model, dataset, or tool call was made.")
    sample = (load_validation_sample(repo, index, canonical_query=canonical_query)
              if split == "validation" else load_query_sample(split, index))
    task = {"idx": index if split == "train" else sample["index"], "query": sample["query"]}
    run_dir = _run_directory(runs_dir, model, split, index)
    prompt = build_react_prompt(task)
    config = {
        "baseline": "B_two_stage_react", "protocol_status": "candidate_pre_pilot",
        "split": split, "index": index,
        "model": model, "base_url": base_url, "temperature": 0.0,
        "timeout_seconds": timeout, "max_retries": max_retries,
        "max_tool_calls": max_tool_calls, "max_context_tokens": max_context_tokens,
        "max_output_tokens": max_output_tokens, "prompt_protocol_hash": react_protocol_hash(),
        "tool_schema_hash": tool_schema_hash(), "evidence_audit_version": AUDIT_VERSION,
        "experiment_id": experiment_id,
        "attempt": attempt, "api_key": "[provided via environment; never persisted]",
        "modules": {"tools": True, "react": True, "explicit_planner": False,
                    "verifier": False, "replan": False, "memory": False,
                    "reflection": False, "multi_agent": False},
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
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    try:
        baseline = ReactBaseline(toolbox=_shared_toolbox(repo), model=model, base_url=base_url,
                                 timeout=timeout, max_retries=max_retries,
                                 max_tool_calls=max_tool_calls, max_context_tokens=max_context_tokens,
                                 max_output_tokens=max_output_tokens)
        generation = baseline.generate(task)
    except Exception as exc:
        retryable = type(exc).__name__ in {"APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError", "ServiceUnavailableError"}
        status = {"status": "blocked", "stage": "agent_run", "error_type": type(exc).__name__,
                  "error": str(exc), "model_calls_attempted": 0 if isinstance(exc, ValueError) else 1,
                  "retryable": retryable, "experiment_id": experiment_id, "attempt": attempt}
        audit = build_evidence_audit(trajectory=[], submission=None,
                                     reference_information=audit_reference,
                                     terminal_reason="agent_run_error")
        _write_json(run_dir / "evidence_audit.json", audit)
        _write_json(run_dir / "status.json", status)
        return {"run_dir": str(run_dir), **status}
    (run_dir / "raw_response.txt").write_text(generation.raw_response, encoding="utf-8")
    _write_json(run_dir / "trajectory.json", generation.trajectory)
    if generation.parsed_response is not None:
        _write_json(run_dir / "parsed_response.json", generation.parsed_response)
    schema = validate_generated_submission(generation.parsed_response, expected_idx=task["idx"], expected_query=task["query"])
    fmt = validate_evaluator_format(generation.parsed_response)
    audit = build_evidence_audit(
        trajectory=generation.trajectory,
        submission=generation.parsed_response,
        reference_information=audit_reference,
        terminal_reason=generation.terminal_reason,
    )
    _write_json(run_dir / "evidence_audit.json", audit)
    _write_json(run_dir / "validation.json", {"schema": schema, "evaluator_format": fmt})
    ready = schema["valid"] and fmt["valid"] and generation.terminal_reason == "final_response"
    if ready:
        (run_dir / "submission.jsonl").write_text(json.dumps(generation.parsed_response, ensure_ascii=False) + "\n", encoding="utf-8")
    status = {"status": "completed" if ready else "invalid_output", "stage": generation.terminal_reason,
              "model_calls_attempted": generation.model_calls, "tool_calls": generation.tool_calls,
              "latency_seconds": generation.latency_seconds, "usage": generation.usage,
              "schema_valid": schema["valid"], "evaluator_format_valid": fmt["valid"],
              "retryable": False, "experiment_id": experiment_id, "attempt": attempt}
    _write_json(run_dir / "status.json", status)
    return {"run_dir": str(run_dir), **status}
