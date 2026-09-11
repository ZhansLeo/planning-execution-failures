from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from jsonschema import Draft7Validator
from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError


ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_ROOT = Path(os.environ.get("CHINATRAVEL_OFFICIAL_REPO", ROOT.parent / "ChinaTravel")).resolve()
DATA_ROOT = Path(os.environ.get("CHINATRAVEL_DATA_ROOT", ROOT / "data" / "source")).resolve()
RUNS_ROOT = Path(os.environ.get("CHINATRAVEL_RUNS_ROOT", ROOT / "runs")).resolve()
HIDDEN_QUERY_KEYS = {"hard_logic", "hard_logic_py", "hard_logic_nl"}
EXCLUDED_TOOLS = {
    "china_travel_world_command",
    "china_travel_list_splits",
    "china_travel_load_query",
}
MAX_TOOL_CALLS = 30
MAX_CONTEXT_TOKENS = 56_000
MAX_MODEL_ROUNDS = 31
PROTOCOL_VERSION = "ct-b-react-v1.0-pilot"
PILOT_ID = "ct-pilot-v1"
PILOT_SEED = 20260904
DEV_UIDS = {
    "e20241028160248698752",
    "e20241028160251109186",
    "e20241028160253742452",
}


def _ensure_official_import() -> None:
    value = str(OFFICIAL_ROOT)
    if value not in sys.path:
        sys.path.insert(0, value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def estimate_context_tokens(messages: list[dict[str, Any]]) -> int:
    """Stable conservative token estimate for a non-OpenAI tokenizer."""
    raw = json.dumps(messages, ensure_ascii=False, default=json_default)
    # Chinese characters are commonly close to one token; ASCII-heavy JSON is
    # closer to four characters per token. Counting UTF-8 bytes / 3 avoids the
    # previous overly aggressive two-characters-per-token cutoff.
    return max(len(raw.encode("utf-8")) // 3, len(raw) // 4)


def json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if hasattr(value, "to_dict"):
        return value.to_dict(orient="records")
    return str(value)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=OFFICIAL_ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def load_query(split: str, uid: str | None = None) -> tuple[str, dict[str, Any]]:
    path = DATA_ROOT / f"{split}.csv"
    if split not in {"easy", "medium", "human"} or not path.exists():
        raise ValueError(f"Unavailable local split: {split}")
    frame = pd.read_csv(path)
    if frame.empty:
        raise RuntimeError(f"Empty split: {split}")
    row = frame.iloc[0] if uid is None else frame.loc[frame["uid"] == uid].iloc[0]
    query: dict[str, Any] = {}
    for key, value in row.to_dict().items():
        if pd.isna(value):
            continue
        if hasattr(value, "item"):
            value = value.item()
        query[key] = value
    if isinstance(query.get("hard_logic_py"), str):
        query["hard_logic_py"] = ast.literal_eval(query["hard_logic_py"])
    return str(query["uid"]), query


def visible_query(query: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in query.items() if key not in HIDDEN_QUERY_KEYS}


def assert_oracle_absent(value: Any) -> None:
    serialized = json.dumps(value, ensure_ascii=False, default=json_default)
    found = [key for key in HIDDEN_QUERY_KEYS if key in serialized]
    if found:
        raise RuntimeError(f"Oracle leakage detected: {found}")


def output_schema() -> dict[str, Any]:
    return json.loads(
        (OFFICIAL_ROOT / "chinatravel" / "evaluation" / "output_schema.json").read_text(
            encoding="utf-8"
        )
    )


def exposed_tools(adapter: Any) -> list[dict[str, Any]]:
    tools = adapter.list_tools(format="openai")
    return [tool for tool in tools if tool["function"]["name"] not in EXCLUDED_TOOLS]


def build_executor_prompt(query: dict[str, Any], schema: dict[str, Any], blueprint: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    system = (
        "你是 ChinaTravel 基准中的旅行规划 Agent。你必须自主调用所给本地工具获取事实，"
        "不得使用模型记忆编造景点、餐厅、住宿、交通、价格、时间、距离、车次或航班。"
        "工具结果按官方顺序分页；需要更多结果时调用 next_page。你可以在一次响应中请求多个工具，"
        "系统会按你给出的顺序串行执行。整条任务最多允许30次工具调用，请主动管理预算并在耗尽前输出最终计划。"
        "当证据足够后，只输出一个严格 JSON 对象，不要 Markdown、解释或思考过程。"
        "输出必须匹配给定官方 schema，并完整满足用户的中文需求。"
    )
    payload: dict[str, Any] = {
        "visible_query": query,
        "official_output_schema": schema,
    }
    if blueprint is not None:
        payload["planning_blueprint"] = blueprint
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
    ]
    assert_oracle_absent(messages)
    return messages


PLANNER_SCHEMA = {
    "type": "object",
    "properties": {
        "trip_facts": {
            "type": "object",
            "properties": {
                "start_city": {"type": "string"},
                "target_city": {"type": "string"},
                "days": {"type": "integer", "minimum": 1},
                "people_number": {"type": "integer", "minimum": 1},
                "budget": {"type": ["number", "null"]},
                "additional_facts": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["start_city", "target_city", "days", "people_number", "budget", "additional_facts"],
            "additionalProperties": False,
        },
        "hard_constraints": {
            "type": "array",
            "items": {"$ref": "#/definitions/constraint"},
        },
        "soft_preferences": {
            "type": "array",
            "items": {"$ref": "#/definitions/preference"},
        },
        "retrieval_checklist": {
            "type": "array",
            "items": {"$ref": "#/definitions/retrieval"},
        },
        "planning_risks": {
            "type": "array",
            "items": {"$ref": "#/definitions/risk"},
        },
    },
    "required": [
        "trip_facts", "hard_constraints", "soft_preferences", "retrieval_checklist", "planning_risks"
    ],
    "additionalProperties": False,
    "definitions": {
        "constraint": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": "^HC-[0-9]+$"},
                "category": {"type": "string", "enum": ["trip_facts", "budget", "tickets", "transportation", "accommodation", "time", "meal", "attraction", "preference", "other"]},
                "requirement": {"type": "string"},
                "source_text": {"type": "string"},
            },
            "required": ["id", "category", "requirement", "source_text"],
            "additionalProperties": False,
        },
        "preference": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": "^SP-[0-9]+$"},
                "category": {"type": "string", "enum": ["attraction", "cuisine", "accommodation", "transportation", "pace", "location", "other"]},
                "preference": {"type": "string"},
                "source_text": {"type": "string"},
            },
            "required": ["id", "category", "preference", "source_text"],
            "additionalProperties": False,
        },
        "retrieval": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": "^RC-[0-9]+$"},
                "category": {"type": "string", "enum": ["intercity_transport", "attractions", "restaurants", "accommodations", "inner_city_transport"]},
                "city": {"type": ["string", "null"]},
                "route": {
                    "anyOf": [
                        {"type": "null"},
                        {"type": "object", "properties": {"start_city": {"type": "string"}, "end_city": {"type": "string"}}, "required": ["start_city", "end_city"], "additionalProperties": False},
                    ]
                },
                "purpose": {"type": "string"},
                "supports_constraint_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["id", "category", "city", "route", "purpose", "supports_constraint_ids"],
            "additionalProperties": False,
        },
        "risk": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": ["budget", "time", "transportation", "opening_hours", "accommodation", "preference_conflict", "long_horizon", "other"]},
                "description": {"type": "string"},
                "mitigation": {"type": "string"},
            },
            "required": ["category", "description", "mitigation"],
            "additionalProperties": False,
        },
    },
}


def parse_blueprint(text: str) -> dict[str, Any]:
    value = json.loads(text)
    Draft7Validator(PLANNER_SCHEMA).validate(value)
    return value


def build_planner_messages(query: dict[str, Any]) -> list[dict[str, Any]]:
    messages = [
        {
            "role": "system",
            "content": (
                "把中文旅行需求结构化为紧凑的全局规划蓝图。区分硬约束与软偏好，并设计必要而非穷举的检索清单。"
                "source_text 必须是原始中文需求中的短语。不要调用工具，也不要填写用户未明确指定的具体 POI、住宿、"
                "餐厅、车次或航班。只输出严格 JSON，不要 Markdown 或解释。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"visible_query": query, "blueprint_schema": PLANNER_SCHEMA},
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]
    assert_oracle_absent(messages)
    return messages


@dataclass
class ModelConfig:
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"
    temperature: float = 0
    timeout: float = 120
    retries: int = 2

    @classmethod
    def from_env(cls) -> "ModelConfig":
        return cls(
            model=os.getenv("MODEL_NAME", "deepseek-chat"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com"),
        )


def api_key() -> str:
    value = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not value:
        raise RuntimeError("Missing OPENAI_API_KEY or DEEPSEEK_API_KEY; no model call was made.")
    return value


def call_model(client: OpenAI, config: ModelConfig, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, *, max_tokens: int = 8000) -> tuple[Any, float, int]:
    retry_types = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)
    for attempt in range(config.retries + 1):
        started = time.perf_counter()
        try:
            kwargs: dict[str, Any] = {
                "model": config.model,
                "messages": messages,
                "temperature": config.temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "parallel_tool_calls": False,
                "extra_body": {"thinking": {"type": "disabled"}},
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            response = client.chat.completions.create(**kwargs)
            return response, time.perf_counter() - started, attempt + 1
        except retry_types:
            if attempt >= config.retries:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def finalization_message(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "user",
        "content": (
            "检索阶段已经结束。现在禁止继续调用工具。请仅根据上文真实 observations 输出最终计划。"
            "只返回一个严格 JSON 对象，不要解释、Markdown、草稿或第二个对象。再次遵守此官方 schema：\n"
            + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        ),
    }


def _assistant_message(message: Any) -> dict[str, Any]:
    value: dict[str, Any] = {"role": "assistant", "content": message.content}
    if message.tool_calls:
        value["tool_calls"] = [call.model_dump(exclude_none=True) for call in message.tool_calls]
    return value


def execute_tool_bundle(
    adapter: Any,
    tool_calls: list[Any],
    remaining_budget: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Execute a model-emitted bundle serially, preserving model order."""
    executed: list[dict[str, Any]] = []
    exceeded = len(tool_calls) > remaining_budget
    for call in tool_calls[:remaining_budget]:
        started = time.perf_counter()
        try:
            arguments = json.loads(call.function.arguments)
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be a JSON object")
        except Exception as exc:
            arguments = {}
            result = {
                "success": False,
                "error_type": "InvalidToolArguments",
                "error": str(exc),
            }
        else:
            result = adapter.call_tool(call.function.name, arguments)
        executed.append(
            {
                "tool_call_id": call.id,
                "tool_name": call.function.name,
                "tool_arguments": arguments,
                "tool_result": result,
                "tool_latency_seconds": time.perf_counter() - started,
            }
        )
    return executed, exceeded


def tool_bundle_signature(executed: list[dict[str, Any]]) -> str:
    return stable_hash([
        [item["tool_name"], item["tool_arguments"], item["tool_result"]]
        for item in executed
    ])


def strict_parse_plan(raw: str, schema: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        value = json.loads(raw)
    except Exception as exc:
        return None, [f"strict_json: {exc}"]
    if not isinstance(value, dict):
        return None, ["top-level output is not an object"]
    errors = [error.message for error in Draft7Validator(schema).iter_errors(value)]
    return value, errors


def evaluate_one(split: str, uid: str, query: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    _ensure_official_import()
    from agent_env.scripts.solve_script_with_harness import evaluate_one as official_evaluate_one

    result = official_evaluate_one(split, uid, query, plan, "zh")
    result["preference"] = {"status": "not_applicable", "reason": "easy/medium/human main split"}
    return result


def failed_evaluation(split: str, uid: str, reason: str) -> dict[str, Any]:
    return {
        "split": split, "uid": uid, "schema_pass": False, "commonsense_pass": False,
        "logical_pass": False, "all_pass": False, "parse_failure": True,
        "failure_reason": reason,
        "preference": {"status": "not_applicable", "reason": "easy/medium/human main split"},
    }


def classify_failure(termination: str, evaluation: dict[str, Any], trajectory: list[dict[str, Any]]) -> dict[str, Any]:
    flags: list[str] = []
    if any(item.get("tool_result", {}).get("success") is False for item in trajectory):
        flags.append("information_acquisition_failure")
    if termination in {"max_steps", "max_model_rounds", "repeated_call", "tool_budget_exceeded", "context_limit"}:
        flags.append("information_acquisition_failure")
    if evaluation.get("parse_failure") or (evaluation and not evaluation.get("all_pass")):
        flags.append("execution_consistency_failure")
    if evaluation.get("all_pass"):
        primary = "success"
    elif flags:
        primary = flags[0]
    else:
        primary = "execution_consistency_failure"
    return {
        "primary": primary,
        "flags": list(dict.fromkeys(flags)),
        "not_directly_observable": ["constraint_understanding_failure", "preference_optimization_failure"],
        "note": "Smoke attribution is evidence-based but intentionally conservative.",
    }


def run_ct_b(
    split: str,
    uid: str | None = None,
    *,
    milestone: str = "single_sample_smoke",
    experiment_id: str | None = None,
    blueprint: dict[str, Any] | None = None,
    run_prefix: str = "ct-b-smoke",
    experiment_name: str = "CT-B_query_only_react",
    protocol_version: str = PROTOCOL_VERSION,
    manifest_extra: dict[str, Any] | None = None,
) -> Path:
    selected_uid, oracle_query = load_query(split, uid)
    public_query = visible_query(oracle_query)
    assert_oracle_absent(public_query)
    schema = output_schema()
    _ensure_official_import()
    from agent_env.adapter import ChinaTravelEnvAdapter

    adapter = ChinaTravelEnvAdapter(lang="zh")
    tools = exposed_tools(adapter)
    messages = build_executor_prompt(public_query, schema, blueprint)
    config = ModelConfig.from_env()
    now = datetime.now(timezone.utc)
    run_id = f"{run_prefix}-{now.strftime('%Y%m%dT%H%M%SZ')}-{selected_uid}"
    run_dir = RUNS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    prompt_hash = stable_hash(messages)
    manifest = {
        "experiment": experiment_name,
        "protocol_version": protocol_version,
        "milestone": milestone,
        "experiment_id": experiment_id,
        "run_id": run_id,
        "created_at_utc": now.isoformat(),
        "split": split,
        "uid": selected_uid,
        "selection_rule": "first official CSV row" if uid is None else "explicit uid",
        "lang": "zh",
        "official_commit": git_output("rev-parse", "HEAD"),
        "official_dirty_before": git_output("status", "--short"),
        "query_file_sha256": sha256_file(DATA_ROOT / f"{split}.csv"),
        "sandbox_zip_sha256": "42d95ff7b8f96574d0ee972ca77599258e4854a219617868caeb462b79c715bd",
        "output_schema_sha256": sha256_file(OFFICIAL_ROOT / "chinatravel/evaluation/output_schema.json"),
        "prompt_hash": prompt_hash,
        "tool_schema_hash": stable_hash(tools),
        "model": config.model,
        "base_url": config.base_url,
        "temperature": config.temperature,
        "max_tool_calls": MAX_TOOL_CALLS,
        "max_model_rounds": MAX_MODEL_ROUNDS,
        "parallel_call_policy": "sequential_in_model_order",
        "parser": "strict-json-no-repair",
        "response_format": "json_object",
        "thinking_mode": "disabled",
        "finalization_policy": "one_same-model_no-tools-json-turn",
        "context_limit_tokens": MAX_CONTEXT_TOKENS,
        "context_token_estimator": "max(utf8_bytes/3,unicode_chars/4)",
        "oracle_fields_hidden": sorted(HIDDEN_QUERY_KEYS),
    }
    if manifest_extra:
        manifest.update(manifest_extra)
    write_json(run_dir / "manifest.json", manifest)
    write_json(run_dir / "query_visible.json", public_query)
    write_json(run_dir / "prompt.json", messages)
    write_json(run_dir / "tool_schemas.json", tools)

    client = OpenAI(api_key=api_key(), base_url=config.base_url, timeout=config.timeout, max_retries=0)
    trajectory: list[dict[str, Any]] = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "model_calls": 0, "api_attempts": 0}
    seen_bundles: list[str] = []
    total_tool_calls = 0
    resolved_models: set[str] = set()
    termination = "unknown"
    raw_final = ""
    started_all = time.perf_counter()
    try:
        for step in range(MAX_MODEL_ROUNDS):
            estimated_context_tokens = estimate_context_tokens(messages)
            if estimated_context_tokens > MAX_CONTEXT_TOKENS:
                termination = "context_limit"
                break
            response, latency, attempts = call_model(client, config, messages, tools)
            resolved_models.add(str(response.model))
            usage["model_calls"] += 1
            usage["api_attempts"] += attempts
            if response.usage:
                usage["prompt_tokens"] += response.usage.prompt_tokens or 0
                usage["completion_tokens"] += response.usage.completion_tokens or 0
                usage["total_tokens"] += response.usage.total_tokens or 0
            message = response.choices[0].message
            entry: dict[str, Any] = {
                "round_id": step,
                "llm_latency_seconds": latency,
                "estimated_context_tokens": estimated_context_tokens,
                "tool_calls_before_round": total_tool_calls,
                "tool_budget_remaining_before_round": MAX_TOOL_CALLS - total_tool_calls,
                "response_model": response.model,
            }
            if not message.tool_calls:
                entry["retrieval_stop_response"] = message.content or ""
                finalize_messages = [*messages, finalization_message(schema)]
                assert_oracle_absent(finalize_messages)
                final_response, final_latency, final_attempts = call_model(
                    client, config, finalize_messages, None
                )
                resolved_models.add(str(final_response.model))
                usage["model_calls"] += 1
                usage["api_attempts"] += final_attempts
                if final_response.usage:
                    usage["prompt_tokens"] += final_response.usage.prompt_tokens or 0
                    usage["completion_tokens"] += final_response.usage.completion_tokens or 0
                    usage["total_tokens"] += final_response.usage.total_tokens or 0
                raw_final = final_response.choices[0].message.content or ""
                entry["finalization_latency_seconds"] = final_latency
                entry["final_response"] = raw_final
                trajectory.append(entry)
                termination = "finalized_response"
                break
            messages.append(_assistant_message(message))
            if total_tool_calls >= MAX_TOOL_CALLS:
                termination = "max_steps"
                trajectory.append(entry)
                break
            raw_bundle = [call.model_dump(exclude_none=True) for call in message.tool_calls]
            executed, exceeded = execute_tool_bundle(
                adapter, message.tool_calls, MAX_TOOL_CALLS - total_tool_calls
            )
            bundle_signature = tool_bundle_signature(executed)
            seen_bundles.append(bundle_signature)
            for offset, item in enumerate(executed, start=1):
                item["tool_call_index"] = total_tool_calls + offset
                messages.append({
                    "role": "tool",
                    "tool_call_id": item["tool_call_id"],
                    "content": json.dumps(item["tool_result"], ensure_ascii=False, default=json_default),
                })
            total_tool_calls += len(executed)
            entry["tool_call_bundle"] = raw_bundle
            entry["executed_tools"] = executed
            entry["tool_calls_after_round"] = total_tool_calls
            entry["tool_budget_remaining_after_round"] = MAX_TOOL_CALLS - total_tool_calls
            entry["bundle_size"] = len(message.tool_calls)
            entry["budget_exceeded"] = exceeded
            trajectory.append(entry)
            if exceeded:
                termination = "tool_budget_exceeded"
                break
            if len(seen_bundles) >= 3 and len(set(seen_bundles[-3:])) == 1:
                termination = "repeated_call"
                break
        else:
            termination = "max_model_rounds"
    except Exception as exc:
        termination = "infrastructure_failure"
        write_json(run_dir / "infrastructure_error.json", {"type": type(exc).__name__, "message": str(exc)})

    total_latency = time.perf_counter() - started_all
    with (run_dir / "trajectory.jsonl").open("w", encoding="utf-8") as stream:
        for item in trajectory:
            stream.write(json.dumps(item, ensure_ascii=False, default=json_default) + "\n")
    (run_dir / "final_raw_response.txt").write_text(raw_final, encoding="utf-8")
    parsed, validation_errors = strict_parse_plan(raw_final, schema) if raw_final else (None, [f"no final response: {termination}"])
    write_json(run_dir / "parse_result.json", {"parsed": parsed is not None, "schema_errors": validation_errors})
    if parsed is not None:
        write_json(run_dir / "evaluator_ready.json", parsed)
        evaluation = evaluate_one(split, selected_uid, oracle_query, parsed)
    else:
        evaluation = failed_evaluation(split, selected_uid, validation_errors[0])
    write_json(run_dir / "evaluation.json", evaluation)
    usage.update({
        "tool_calls": total_tool_calls,
        "latency_seconds": total_latency,
        "termination": termination,
        "max_bundle_size": max((item.get("bundle_size", 0) for item in trajectory), default=0),
    })
    write_json(run_dir / "usage.json", usage)
    failure = classify_failure(termination, evaluation, trajectory)
    if termination == "infrastructure_failure":
        failure["primary"] = "infrastructure_failure"
    write_json(run_dir / "failure_audit.json", failure)
    manifest["official_dirty_after"] = git_output("status", "--short")
    manifest["terminal_status"] = termination
    manifest["resolved_response_models"] = sorted(resolved_models)
    write_json(run_dir / "manifest.json", manifest)
    return run_dir


def reevaluate(run_id: str) -> Path:
    run_dir = RUNS_ROOT / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((run_dir / "evaluator_ready.json").read_text(encoding="utf-8"))
    uid, query = load_query(manifest["split"], manifest["uid"])
    result = evaluate_one(manifest["split"], uid, query, plan)
    write_json(run_dir / "evaluation_rerun.json", result)
    return run_dir / "evaluation_rerun.json"


def inspect_environment() -> dict[str, Any]:
    _ensure_official_import()
    from agent_env.adapter import ChinaTravelEnvAdapter

    adapter = ChinaTravelEnvAdapter(lang="zh")
    tools = exposed_tools(adapter)
    split_info = {}
    for split in ("easy", "medium", "human"):
        frame = pd.read_csv(DATA_ROOT / f"{split}.csv")
        split_info[split] = {"count": len(frame), "first_uid": str(frame.iloc[0]["uid"]), "sha256": sha256_file(DATA_ROOT / f"{split}.csv")}
    db_files = sorted((OFFICIAL_ROOT / "chinatravel/environment/database").rglob("*"))
    report = {
        "status": "ok",
        "official_root": str(OFFICIAL_ROOT),
        "official_commit": git_output("rev-parse", "HEAD"),
        "official_git_status": git_output("status", "--short"),
        "python": platform.python_version(),
        "database_file_count": len([p for p in db_files if p.is_file()]),
        "splits": split_info,
        "exposed_tool_names": [item["function"]["name"] for item in tools],
        "excluded_tool_names": sorted(EXCLUDED_TOOLS),
        "output_schema_sha256": sha256_file(OFFICIAL_ROOT / "chinatravel/evaluation/output_schema.json"),
        "runtime_data_source": "local fixed ChinaTravel sandbox",
    }
    write_json(ROOT / "environment_report.json", report)
    return report


def validate_ct_c_offline(split: str, uid: str | None = None) -> dict[str, Any]:
    """Validate the CT-C boundary without making a model or tool call."""
    selected_uid, oracle_query = load_query(split, uid)
    public_query = visible_query(oracle_query)
    mock_blueprint = {
        "trip_facts": {
            "start_city": public_query.get("start_city"),
            "target_city": public_query.get("target_city"),
            "days": public_query.get("days"),
            "people_number": public_query.get("people_number"),
            "budget": None,
            "additional_facts": [],
        },
        "hard_constraints": [{"id": "HC-1", "category": "trip_facts", "requirement": "遵守人数和天数", "source_text": str(public_query.get("nature_language", ""))[:20]}],
        "soft_preferences": [],
        "retrieval_checklist": [{"id": "RC-1", "category": "intercity_transport", "city": None, "route": {"start_city": public_query.get("start_city"), "end_city": public_query.get("target_city")}, "purpose": "查询城际交通", "supports_constraint_ids": ["HC-1"]}],
        "planning_risks": [{"category": "transportation", "description": "交通需有工具证据", "mitigation": "检索后再填写"}],
    }
    parsed = parse_blueprint(json.dumps(mock_blueprint, ensure_ascii=False))
    planner_messages = build_planner_messages(public_query)
    executor_messages = build_executor_prompt(public_query, output_schema(), parsed)
    assert_oracle_absent([planner_messages, executor_messages])
    return {
        "status": "offline_contract_pass",
        "real_model_calls": 0,
        "real_tool_calls": 0,
        "split": split,
        "uid": selected_uid,
        "planner_schema_hash": stable_hash(PLANNER_SCHEMA),
        "planner_prompt_hash": stable_hash(planner_messages),
        "executor_prompt_hash": stable_hash(executor_messages),
    }


def pilot_root() -> Path:
    return ROOT / "experiments" / PILOT_ID


def create_pilot_manifest() -> dict[str, Any]:
    rng = random.Random(PILOT_SEED)
    samples = []
    for split in ("easy", "medium", "human"):
        frame = pd.read_csv(DATA_ROOT / f"{split}.csv")
        candidates = [str(uid) for uid in frame["uid"].tolist() if str(uid) not in DEV_UIDS]
        chosen = rng.sample(candidates, 4)
        samples.extend({"split": split, "uid": uid} for uid in chosen)
    _ensure_official_import()
    from agent_env.adapter import ChinaTravelEnvAdapter

    tools = exposed_tools(ChinaTravelEnvAdapter(lang="zh"))
    manifest = {
        "experiment_id": PILOT_ID,
        "purpose": "paired CT-B/CT-C cross-benchmark pilot",
        "seed": PILOT_SEED,
        "protocol_version": PROTOCOL_VERSION,
        "baseline": "CT-B_query_only_react",
        "status": "FROZEN",
        "sample_count": len(samples),
        "samples": samples,
        "excluded_development_uids": sorted(DEV_UIDS),
        "official_commit": git_output("rev-parse", "HEAD"),
        "output_schema_sha256": sha256_file(OFFICIAL_ROOT / "chinatravel/evaluation/output_schema.json"),
        "tool_schema_hash": stable_hash(tools),
        "max_total_tool_calls": MAX_TOOL_CALLS,
        "parallel_call_policy": "sequential_in_model_order",
        "thinking_mode": "disabled",
        "response_format": "json_object",
        "finalization_policy": "one_same-model_no-tools-json-turn",
        "parser": "strict-json-no-repair",
        "oracle_fields_hidden": sorted(HIDDEN_QUERY_KEYS),
    }
    root = pilot_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "manifest.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != manifest:
            raise RuntimeError("Frozen pilot manifest differs from regenerated protocol; refusing overwrite.")
        return existing
    write_json(path, manifest)
    write_json(root / "state.json", {"completed": {}, "failures": {}})
    return manifest


def run_pilot_ct_b(*, resume: bool) -> dict[str, Any]:
    manifest = create_pilot_manifest()
    state_path = pilot_root() / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state["completed"] and not resume:
        raise RuntimeError("Pilot already has completed samples; pass --resume to continue safely.")
    for sample in manifest["samples"]:
        key = f"{sample['split']}:{sample['uid']}"
        if key in state["completed"]:
            continue
        try:
            run_dir = run_ct_b(
                sample["split"], sample["uid"], milestone="12_sample_pilot", experiment_id=PILOT_ID
            )
            state["completed"][key] = run_dir.name
            state["failures"].pop(key, None)
        except Exception as exc:
            state["failures"][key] = {"type": type(exc).__name__, "message": str(exc)}
        write_json(state_path, state)
    return state


def aggregate_pilot_ct_b() -> dict[str, Any]:
    manifest = create_pilot_manifest()
    state = json.loads((pilot_root() / "state.json").read_text(encoding="utf-8"))
    rows = []
    for sample in manifest["samples"]:
        key = f"{sample['split']}:{sample['uid']}"
        run_name = state["completed"].get(key)
        if not run_name:
            rows.append({**sample, "delivery": False, "terminal": "not_completed"})
            continue
        run_dir = RUNS_ROOT / run_name
        usage = json.loads((run_dir / "usage.json").read_text(encoding="utf-8"))
        evaluation = json.loads((run_dir / "evaluation.json").read_text(encoding="utf-8"))
        rows.append({
            **sample,
            "run_id": run_name,
            "delivery": bool(evaluation.get("schema_pass")),
            "schema_pass": bool(evaluation.get("schema_pass")),
            "environment_pass": bool(evaluation.get("commonsense_pass")),
            "logical_pass": bool(evaluation.get("logical_pass")),
            "all_pass": bool(evaluation.get("all_pass")),
            "environment_micro": evaluation.get("commonsense_micro", 0),
            "environment_macro": evaluation.get("commonsense_macro", 0),
            "logical_micro": evaluation.get("logical_micro", 0),
            "logical_macro": evaluation.get("logical_macro", 0),
            "conditional_logical_micro": evaluation.get("conditional_logical_micro", 0),
            "conditional_logical_macro": evaluation.get("conditional_logical_macro", 0),
            "model_calls": usage.get("model_calls", 0),
            "tool_calls": usage.get("tool_calls", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "latency_seconds": usage.get("latency_seconds", 0),
            "terminal": usage.get("termination"),
            "max_bundle_size": usage.get("max_bundle_size", 0),
        })
    completed = [row for row in rows if row.get("run_id")]
    def rate(field: str) -> float:
        return sum(bool(row.get(field)) for row in completed) / len(completed) if completed else 0.0
    split_summaries = {}
    for split in ("easy", "medium", "human"):
        subset = [row for row in completed if row["split"] == split]
        split_summaries[split] = {
            "count": len(subset),
            "delivery_rate": sum(row["delivery"] for row in subset) / len(subset) if subset else 0,
            "environment_pass_rate": sum(row["environment_pass"] for row in subset) / len(subset) if subset else 0,
            "logical_pass_rate": sum(row["logical_pass"] for row in subset) / len(subset) if subset else 0,
            "all_pass_rate": sum(row["all_pass"] for row in subset) / len(subset) if subset else 0,
            "mean_tokens": sum(row["total_tokens"] for row in subset) / len(subset) if subset else 0,
            "mean_tool_calls": sum(row["tool_calls"] for row in subset) / len(subset) if subset else 0,
            "mean_latency_seconds": sum(row["latency_seconds"] for row in subset) / len(subset) if subset else 0,
        }
    delivered = [row for row in completed if row["delivery"]]
    terminal_counts: dict[str, int] = {}
    for row in completed:
        terminal_counts[row["terminal"]] = terminal_counts.get(row["terminal"], 0) + 1
    summary = {
        "experiment_id": PILOT_ID,
        "protocol_version": PROTOCOL_VERSION,
        "planned": len(rows),
        "completed": len(completed),
        "delivery_rate": rate("delivery"),
        "environment_pass_rate": rate("environment_pass"),
        "logical_pass_rate": rate("logical_pass"),
        "all_pass_rate": rate("all_pass"),
        "total_tokens": sum(row.get("total_tokens", 0) for row in completed),
        "mean_tokens": sum(row.get("total_tokens", 0) for row in completed) / len(completed) if completed else 0,
        "mean_tool_calls": sum(row.get("tool_calls", 0) for row in completed) / len(completed) if completed else 0,
        "mean_latency_seconds": sum(row.get("latency_seconds", 0) for row in completed) / len(completed) if completed else 0,
        "delivered_only_mean_environment_micro": sum(row["environment_micro"] for row in delivered) / len(delivered) if delivered else 0,
        "delivered_only_mean_logical_micro": sum(row["logical_micro"] for row in delivered) / len(delivered) if delivered else 0,
        "terminal_counts": terminal_counts,
        "by_split": split_summaries,
        "rows": rows,
    }
    write_json(pilot_root() / "ct_b_summary.json", summary)
    return summary
