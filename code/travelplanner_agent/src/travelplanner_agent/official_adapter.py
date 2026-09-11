from __future__ import annotations

import importlib
import json
import re
import sys
import types
from pathlib import Path
from typing import Any


PLAN_FIELDS = (
    "days",
    "current_city",
    "transportation",
    "breakfast",
    "attraction",
    "lunch",
    "dinner",
    "accommodation",
)


def require_official_repo(path: Path) -> Path:
    path = path.expanduser().resolve()
    required = (
        "database/validation_ref_info.jsonl",
        "postprocess/example_evaluation.jsonl",
        "evaluation/eval.py",
        "tools/restaurants/apis.py",
    )
    missing = [item for item in required if not (path / item).is_file()]
    if missing:
        raise FileNotFoundError(f"Not an intact supported checkout; missing: {missing}")
    return path


def read_jsonl_row(path: Path, zero_based_index: int = 0) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            if index == zero_based_index:
                return json.loads(line)
    raise IndexError(f"No row {zero_based_index} in {path}")


def load_validation_sample(
    repo: Path, one_based_index: int = 1, canonical_query: str | None = None
) -> dict[str, Any]:
    """Load a query from the official evaluation example and matching ref-info row.

    The official example is validation index 1: its query and plan are used by the
    repository as the evaluator-format example. validation_ref_info line 1 contains
    the matching Myrtle Beach environment observations.
    """
    if one_based_index < 1:
        raise ValueError("Validation indices are one-based and must be positive")
    zero_based_index = one_based_index - 1
    submission = read_jsonl_row(repo / "postprocess/example_evaluation.jsonl", zero_based_index)
    reference = read_jsonl_row(repo / "database/validation_ref_info.jsonl", zero_based_index)
    return {
        "split": "validation",
        "index_base": 1,
        "index": submission["idx"],
        "query": canonical_query if canonical_query is not None else submission["query"],
        "example_plan": submission["plan"],
        "reference_information": reference,
        "sources": {
            "query_and_plan": str(repo / "postprocess/example_evaluation.jsonl"),
            "reference_information": str(repo / "database/validation_ref_info.jsonl"),
            "reference_line": one_based_index,
            "query_source": (
                "osunlp/TravelPlanner validation cache"
                if canonical_query is not None
                else str(repo / "postprocess/example_evaluation.jsonl")
            ),
        },
    }


def load_query_sample(split: str, one_based_index: int) -> dict[str, Any]:
    """Load a query-only development sample without reference information leakage."""
    if split not in {"train", "validation"} or one_based_index < 1:
        raise ValueError("split must be train or validation and index must be positive")
    import os
    if split == "validation":
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    from datasets import load_dataset
    data = load_dataset("osunlp/TravelPlanner", split)[split]
    if one_based_index > len(data):
        raise IndexError(f"No {split} row {one_based_index}")
    row = data[one_based_index - 1]
    return {"split": split, "index": one_based_index, "query": row["query"],
            "sources": {"query_source": f"osunlp/TravelPlanner {split}", "query_line": one_based_index}}


def run_official_restaurant_tool(repo: Path, sample: dict[str, Any]) -> dict[str, Any]:
    """Invoke the official Restaurants.run without copying or changing official code.

    The raw restaurant CSV is absent locally, so the adapter constructs the official
    class without its CSV-loading constructor and injects the equivalent official
    validation reference-info rows as a DataFrame.
    """
    import pandas as pd

    # The official API imports one helper from utils.func; that module also imports
    # Gradio for unrelated functions. Provide only the helper this API requests so
    # a read-only restaurant call does not falsely require the entire agent stack.
    if "utils.func" not in sys.modules:
        utils_package = types.ModuleType("utils")
        utils_package.__path__ = [str(repo / "utils")]
        func_module = types.ModuleType("utils.func")
        func_module.extract_before_parenthesis = lambda text: text.split("(", 1)[0].strip()
        sys.modules.setdefault("utils", utils_package)
        sys.modules["utils.func"] = func_module
    repo_text = str(repo)
    if repo_text not in sys.path:
        sys.path.insert(0, repo_text)
    module = importlib.import_module("tools.restaurants.apis")
    tool = module.Restaurants.__new__(module.Restaurants)
    key = "Restaurants in Myrtle Beach"
    tool.data = pd.DataFrame(sample["reference_information"][key])
    result = tool.run("Myrtle Beach")
    records = result.to_dict(orient="records")
    return {
        "tool": "official tools.restaurants.apis.Restaurants.run",
        "input": {"city": "Myrtle Beach"},
        "observation_count": len(records),
        "observation": records,
        "adapter_note": "Official run() invoked; data injected from official validation_ref_info row 1 because raw CSV database is absent.",
    }


def validate_submission_contract(sample: dict[str, Any]) -> dict[str, Any]:
    submission = {
        "idx": sample["index"],
        "query": sample["query"],
        "plan": sample["example_plan"],
    }
    row_keys_ok = set(submission) == {"idx", "query", "plan"}
    plan_errors: list[str] = []
    for index, day in enumerate(submission["plan"], start=1):
        missing = [field for field in PLAN_FIELDS if field not in day]
        extra = [field for field in day if field not in PLAN_FIELDS]
        if missing or extra:
            plan_errors.append(f"day {index}: missing={missing}, extra={extra}")
    return {
        "valid": row_keys_ok and not plan_errors,
        "top_level_fields": ["idx", "query", "plan"],
        "plan_fields": list(PLAN_FIELDS),
        "plan_length": len(submission["plan"]),
        "row_keys_ok": row_keys_ok,
        "plan_errors": plan_errors,
        "submission": submission,
    }


def direct_task(sample: dict[str, Any]) -> dict[str, Any]:
    """Return only model inputs; deliberately exclude the official example plan."""
    return {
        "idx": sample["index"],
        "query": sample["query"],
        "reference_information": sample["reference_information"],
    }


def expected_days(query: str) -> int | None:
    for pattern in (r"\b(\d+)[- ]day\b", r"\bspanning\s+(\d+)\s+days?\b"):
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def validate_generated_submission(
    submission: Any, *, expected_idx: int, expected_query: str
) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(submission, dict):
        return {"valid": False, "errors": ["response must be a JSON object"]}
    expected_keys = {"idx", "query", "plan"}
    if set(submission) != expected_keys:
        errors.append(
            f"top-level keys must be exactly {sorted(expected_keys)}; got {sorted(submission)}"
        )
    if submission.get("idx") != expected_idx:
        errors.append(f"idx must equal {expected_idx}")
    if submission.get("query") != expected_query:
        errors.append("query must repeat the input verbatim")
    plan = submission.get("plan")
    if not isinstance(plan, list) or not plan:
        errors.append("plan must be a non-empty list")
        return {"valid": not errors, "errors": errors}
    day_count = expected_days(expected_query)
    if day_count is not None and len(plan) != day_count:
        errors.append(f"plan must contain {day_count} days; got {len(plan)}")
    for position, day in enumerate(plan, start=1):
        if not isinstance(day, dict):
            errors.append(f"plan[{position}] must be an object")
            continue
        missing = sorted(set(PLAN_FIELDS) - set(day))
        extra = sorted(set(day) - set(PLAN_FIELDS))
        if missing or extra:
            errors.append(f"plan[{position}] fields: missing={missing}, extra={extra}")
        if day.get("days") != position:
            errors.append(f"plan[{position}].days must equal {position}")
        for field in PLAN_FIELDS[1:]:
            if field in day and not isinstance(day[field], str):
                errors.append(f"plan[{position}].{field} must be a string")
    return {"valid": not errors, "errors": errors}


def validate_evaluator_format(submission: Any) -> dict[str, Any]:
    """Check literal formats consumed by official evaluator string parsers."""
    errors: list[str] = []
    if not isinstance(submission, dict) or not isinstance(submission.get("plan"), list):
        return {"valid": False, "errors": ["no parseable plan"]}
    flight_pattern = re.compile(
        r"^Flight Number: F\d+, from .+ to .+, Departure Time: \d{2}:\d{2}, Arrival Time: \d{2}:\d{2}(?:, Cost: .+)?$"
    )
    for position, day in enumerate(submission["plan"], start=1):
        if not isinstance(day, dict):
            continue
        current_city = day.get("current_city", "")
        transportation = day.get("transportation", "")
        if transportation not in ("", "-") and not str(current_city).startswith("from "):
            errors.append(f"plan[{position}].current_city must use 'from A to B' on a travel day")
        if isinstance(transportation, str) and "flight" in transportation.lower():
            if not flight_pattern.match(transportation):
                errors.append(f"plan[{position}].transportation is not official flight syntax")
        for field in ("breakfast", "lunch", "dinner", "accommodation"):
            value = day.get(field)
            if isinstance(value, str) and value != "-" and ", " not in value:
                errors.append(f"plan[{position}].{field} must use 'Name, City'")
        value = day.get("attraction")
        if isinstance(value, str) and value != "-":
            for part in value.split(";"):
                if part.strip() and ", " not in part:
                    errors.append(f"plan[{position}].attraction item must use 'Name, City'")
    return {"valid": not errors, "errors": errors}


def validate_reference_entities(
    submission: Any, reference_information: dict[str, Any]
) -> dict[str, Any]:
    """Conservatively flag named entities absent from official reference data."""
    restaurants: set[str] = set()
    attractions: set[str] = set()
    accommodations: set[str] = set()
    flights: set[str] = set()
    for key, value in reference_information.items():
        if not isinstance(value, list):
            continue
        for row in value:
            if not isinstance(row, dict):
                continue
            if key.startswith("Restaurants in ") and row.get("Name"):
                restaurants.add(str(row["Name"]))
            elif key.startswith("Attractions in ") and row.get("Name"):
                attractions.add(str(row["Name"]))
            elif key.startswith("Accommodations in ") and row.get("NAME"):
                accommodations.add(str(row["NAME"]))
            elif key.startswith("Flight from ") and row.get("Flight Number"):
                flights.add(str(row["Flight Number"]))

    violations: list[dict[str, Any]] = []

    def match_name(value: str, candidates: set[str]) -> str | None:
        cleaned = value.split("; Cost:", 1)[0].rstrip(".").strip()
        matches = [
            name for name in candidates
            if cleaned == name or cleaned.startswith(name + ", ")
        ]
        return max(matches, key=len) if matches else None

    if not isinstance(submission, dict) or not isinstance(submission.get("plan"), list):
        return {"valid": False, "violations": [{"reason": "no parseable plan"}]}
    for position, day in enumerate(submission["plan"], start=1):
        if not isinstance(day, dict):
            continue
        for field in ("breakfast", "lunch", "dinner"):
            value = day.get(field)
            if isinstance(value, str) and value != "-":
                if match_name(value, restaurants) is None:
                    violations.append({"day": position, "field": field, "value": value})
        value = day.get("attraction")
        if isinstance(value, str) and value != "-":
            for part in value.split(";"):
                if part.strip() and match_name(part, attractions) is None:
                    violations.append({"day": position, "field": "attraction", "value": part.strip()})
        value = day.get("accommodation")
        if isinstance(value, str) and value != "-":
            if match_name(value, accommodations) is None:
                violations.append({"day": position, "field": "accommodation", "value": value})
        value = day.get("transportation")
        if isinstance(value, str):
            match = re.search(r"\bF\d+\b", value)
            if match and match.group(0) not in flights:
                violations.append({"day": position, "field": "transportation", "value": match.group(0)})
    return {"valid": not violations, "violations": violations}
