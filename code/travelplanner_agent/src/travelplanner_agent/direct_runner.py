from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .baselines import (
    DirectBaseline,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_direct_prompt,
    prompt_protocol_hash,
)
from .official_adapter import (
    direct_task,
    load_validation_sample,
    validate_generated_submission,
    validate_evaluator_format,
    validate_reference_entities,
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_directory(runs_dir: Path, model: str, index: int) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "-", model).strip("-") or "model"
    path = runs_dir / f"{timestamp}_{safe_model}_validation_{index:03d}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def run_direct(
    repo: Path,
    runs_dir: Path,
    index: int,
    *,
    model: str,
    base_url: str,
    timeout: float,
    max_retries: int,
    experiment_id: str | None = None,
    attempt: int = 1,
    canonical_query: str | None = None,
) -> dict[str, Any]:
    sample = load_validation_sample(repo, index, canonical_query=canonical_query)
    task = direct_task(sample)
    run_dir = _run_directory(runs_dir, model, index)
    prompt = build_direct_prompt(task)
    config = {
        "baseline": "A_sole_planning_direct",
        "split": "validation",
        "index": index,
        "model": model,
        "base_url": base_url,
        "temperature": 0.0,
        "timeout_seconds": timeout,
        "max_retries": max_retries,
        "response_format": "json_object",
        "prompt_version": PROMPT_VERSION,
        "prompt_protocol_hash": prompt_protocol_hash(),
        "experiment_id": experiment_id,
        "attempt": attempt,
        "api_key": "[provided via environment; never persisted]",
        "modules": {
            "tools": False,
            "react": False,
            "explicit_planner": False,
            "verifier": False,
            "replan": False,
            "memory": False,
            "reflection": False,
            "multi_agent": False,
        },
    }
    _write_json(run_dir / "config.json", config)
    _write_json(
        run_dir / "input.json",
        {
            "idx": task["idx"],
            "query": task["query"],
            "sources": sample["sources"],
            "reference_information": task["reference_information"],
        },
    )
    (run_dir / "prompt.txt").write_text(
        f"SYSTEM\n{SYSTEM_PROMPT}\n\nUSER\n{prompt}\n", encoding="utf-8"
    )
    try:
        baseline = DirectBaseline(
            model=model,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            temperature=0.0,
        )
        generation = baseline.generate(task)
    except Exception as exc:
        retryable_names = {
            "APIConnectionError", "APITimeoutError", "RateLimitError",
            "InternalServerError", "ServiceUnavailableError",
        }
        status = {
            "status": "blocked",
            "stage": "model_call",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "model_calls_attempted": 0 if isinstance(exc, ValueError) else 1,
            "retryable": type(exc).__name__ in retryable_names,
            "experiment_id": experiment_id,
            "attempt": attempt,
        }
        _write_json(run_dir / "status.json", status)
        return {"run_dir": str(run_dir), **status}

    (run_dir / "raw_response.txt").write_text(generation.raw_response, encoding="utf-8")
    schema = validate_generated_submission(
        generation.parsed_response,
        expected_idx=task["idx"],
        expected_query=task["query"],
    )
    entities = validate_reference_entities(
        generation.parsed_response, task["reference_information"]
    )
    evaluator_format = validate_evaluator_format(generation.parsed_response)
    if generation.parsed_response is not None:
        _write_json(run_dir / "parsed_response.json", generation.parsed_response)
    validation = {
        "schema": schema,
        "evaluator_format": evaluator_format,
        "reference_entities": entities,
    }
    _write_json(run_dir / "validation.json", validation)
    evaluator_ready = schema["valid"] and evaluator_format["valid"]
    if evaluator_ready:
        with (run_dir / "submission.jsonl").open("w", encoding="utf-8") as stream:
            stream.write(json.dumps(generation.parsed_response, ensure_ascii=False) + "\n")
    status = {
        "status": "completed" if evaluator_ready else "invalid_output",
        "stage": "complete",
        "model_calls_attempted": 1,
        "request_id": generation.request_id,
        "latency_seconds": generation.latency_seconds,
        "usage": generation.usage,
        "schema_valid": schema["valid"],
        "evaluator_format_valid": evaluator_format["valid"],
        "reference_entities_valid": entities["valid"],
        "retryable": False,
        "experiment_id": experiment_id,
        "attempt": attempt,
    }
    _write_json(run_dir / "status.json", status)
    return {"run_dir": str(run_dir), **status}
