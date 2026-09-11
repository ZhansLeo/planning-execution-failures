"""Deterministic post-hoc evidence audits for the Stage-B two-stage baseline."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

AUDIT_VERSION = "evidence-audit-v1.1"


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def _route(value: Any) -> tuple[str, str] | None:
    match = re.match(r"^from (.+?) to (.+)$", str(value).strip(), re.IGNORECASE)
    return (match.group(1).strip(), match.group(2).strip()) if match else None


def _venue_name(value: str) -> str:
    return value.rsplit(", ", 1)[0].strip()


def _successful_calls(trajectory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [step for step in trajectory if step.get("status") == "success" and step.get("observation", {}).get("ok")]


def _call_signatures(trajectory: list[dict[str, Any]]) -> set[tuple[str, ...]]:
    signatures: set[tuple[str, ...]] = set()
    for step in _successful_calls(trajectory):
        name, args = step.get("tool"), step.get("arguments") or {}
        if name in {"restaurant_search", "attraction_search", "accommodation_search"}:
            signatures.add((name, _norm(args.get("city", ""))))
        elif name == "flight_search":
            signatures.add((name, _norm(args.get("origin", "")), _norm(args.get("destination", "")), _norm(args.get("departure_date", ""))))
        elif name == "distance_matrix":
            signatures.add((name, _norm(args.get("origin", "")), _norm(args.get("destination", "")), _norm(args.get("mode", ""))))
        elif name == "city_search":
            signatures.add((name, _norm(args.get("state", ""))))
    return signatures


def _oracle_requirements(reference: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = []
    patterns = (
        (r"^Restaurants in (.+)$", "restaurant_search"),
        (r"^Attractions in (.+)$", "attraction_search"),
        (r"^Accommodations in (.+)$", "accommodation_search"),
    )
    for key in reference:
        for pattern, tool in patterns:
            match = re.match(pattern, key)
            if match:
                requirements.append({"oracle_key": key, "signature": (tool, _norm(match.group(1)))})
                break
        else:
            match = re.match(r"^Flight from (.+) to (.+) on (\d{4}-\d{2}-\d{2})$", key)
            if match:
                requirements.append({"oracle_key": key, "signature": ("flight_search", _norm(match.group(1)), _norm(match.group(2)), match.group(3))})
                continue
            match = re.match(r"^(Self-driving|Taxi) from (.+) to (.+)$", key, re.IGNORECASE)
            if match:
                requirements.append({"oracle_key": key, "signature": ("distance_matrix", _norm(match.group(2)), _norm(match.group(3)), _norm(match.group(1)))})
    return requirements


def _observed_entities(trajectory: list[dict[str, Any]]) -> dict[str, set[str]]:
    entities: dict[str, set[str]] = defaultdict(set)
    for step in _successful_calls(trajectory):
        name = step.get("tool")
        data = step.get("observation", {}).get("data")
        rows = data if isinstance(data, list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if name == "restaurant_search" and row.get("Name"):
                entities["restaurant"].add(_norm(row["Name"]))
            elif name == "attraction_search" and row.get("Name"):
                entities["attraction"].add(_norm(row["Name"]))
            elif name == "accommodation_search" and row.get("NAME"):
                entities["accommodation"].add(_norm(row["NAME"]))
            elif name == "flight_search" and row.get("Flight Number"):
                entities["flight"].add(_norm(row["Flight Number"]))
    return entities


def _plan_items(plan: list[dict[str, Any]]) -> list[dict[str, str]]:
    items = []
    for day_no, day in enumerate(plan, 1):
        for field in ("breakfast", "lunch", "dinner"):
            value = day.get(field)
            if isinstance(value, str) and value not in {"", "-"}:
                items.append({"day": day_no, "field": field, "kind": "restaurant", "value": value, "entity": _venue_name(value)})
        value = day.get("attraction")
        if isinstance(value, str) and value not in {"", "-"}:
            for part in value.split(";"):
                if part.strip():
                    items.append({"day": day_no, "field": "attraction", "kind": "attraction", "value": part.strip(), "entity": _venue_name(part.strip())})
        value = day.get("accommodation")
        if isinstance(value, str) and value not in {"", "-"}:
            items.append({"day": day_no, "field": "accommodation", "kind": "accommodation", "value": value, "entity": _venue_name(value)})
        value = day.get("transportation", "")
        flight = re.search(r"\bF\d+\b", value) if isinstance(value, str) else None
        if flight:
            items.append({"day": day_no, "field": "transportation", "kind": "flight", "value": value, "entity": flight.group(0)})
    return items


def build_evidence_audit(*, trajectory: list[dict[str, Any]], submission: dict[str, Any] | None,
                         reference_information: dict[str, Any], terminal_reason: str) -> dict[str, Any]:
    plan = submission.get("plan", []) if isinstance(submission, dict) else []
    calls = Counter(step.get("tool", "unknown") for step in trajectory)
    errors = [step for step in trajectory if step.get("status") in {"error", "repeated_three_times"}]
    empty = [step for step in trajectory if step.get("observation", {}).get("empty")]
    signatures = _call_signatures(trajectory)

    routes = sorted({_route(day.get("current_city")) for day in plan if isinstance(day, dict)} - {None})
    home = routes[0][0] if routes else None
    stay_cities: set[str] = set()
    for day in plan:
        if not isinstance(day, dict):
            continue
        route = _route(day.get("current_city"))
        city = route[1] if route else str(day.get("current_city", "")).strip()
        if city and city != "-" and (not home or _norm(city) != _norm(home)):
            stay_cities.add(city)
    requirements = []
    for city in sorted(stay_cities):
        for tool in ("restaurant_search", "attraction_search", "accommodation_search"):
            requirements.append({"type": tool, "city": city, "covered": (tool, _norm(city)) in signatures})
    for origin, destination in routes:
        covered = any(sig[:3] == (tool, _norm(origin), _norm(destination)) for sig in signatures for tool in ("flight_search", "distance_matrix"))
        requirements.append({"type": "transportation_search", "origin": origin, "destination": destination, "covered": covered})

    entities = _observed_entities(trajectory)
    grounding_items = []
    for item in _plan_items(plan):
        supported = _norm(item["entity"]) in entities[item["kind"]]
        grounding_items.append({**item, "supported": supported})
    for day_no, day in enumerate(plan, 1):
        if not isinstance(day, dict):
            continue
        route = _route(day.get("current_city"))
        transportation = str(day.get("transportation", ""))
        if route and not re.search(r"\bF\d+\b", transportation) and transportation not in {"", "-"}:
            mode = "taxi" if "taxi" in transportation.casefold() else "self-driving" if "driving" in transportation.casefold() else None
            supported = bool(mode and ("distance_matrix", _norm(route[0]), _norm(route[1]), mode) in signatures)
            grounding_items.append({"day": day_no, "field": "transportation", "kind": "ground_transportation",
                                    "value": transportation, "entity": f"{route[0]}->{route[1]}:{mode}", "supported": supported})
    oracle = _oracle_requirements(reference_information)
    oracle_items = [{"oracle_key": item["oracle_key"], "covered": item["signature"] in signatures} for item in oracle]
    covered = sum(item["covered"] for item in requirements)
    grounded = sum(item["supported"] for item in grounding_items)
    return {
        "audit_version": AUDIT_VERSION,
        "model_context_excludes_reference_information": True,
        "terminal_reason": terminal_reason,
        "tool_execution": {"total": len(trajectory), "by_tool": dict(calls), "errors": len(errors),
                           "empty_results": len(empty), "latency_seconds": sum(float(x.get("tool_latency_seconds", 0)) for x in trajectory),
                           "error_steps": [x.get("step") for x in errors]},
        "chosen_route_coverage": {"requirements": requirements, "covered": covered, "total": len(requirements),
                                  "rate": covered / len(requirements) if requirements else None,
                                  "sufficient": bool(requirements) and covered == len(requirements)},
        "plan_evidence_grounding": {"items": grounding_items, "supported": grounded, "total": len(grounding_items),
                                    "rate": grounded / len(grounding_items) if grounding_items else None,
                                    "fully_grounded": bool(grounding_items) and grounded == len(grounding_items)},
        "oracle_alignment": {"diagnostic_only": True, "items": oracle_items,
                             "covered": sum(x["covered"] for x in oracle_items), "total": len(oracle_items),
                             "rate": sum(x["covered"] for x in oracle_items) / len(oracle_items) if oracle_items else None},
        "environment_validity": None,
        "failure_flags": {},
        "primary_failure_category": None,
    }


def finalize_evidence_audit(audit: dict[str, Any], *, delivered: bool,
                            evaluation: dict[str, Any] | None) -> dict[str, Any]:
    sandbox = None
    if evaluation:
        value = (evaluation.get("commonsense_constraint") or {}).get("is_valid_information_in_sandbox")
        sandbox = value[0] if isinstance(value, (list, tuple)) and value else None
    final_pass = bool(evaluation and evaluation.get("final_pass"))
    flags = {
        "non_delivery_or_agent_control": not delivered,
        "tool_execution_failure": audit["tool_execution"]["errors"] > 0,
        "evidence_insufficient_for_chosen_plan": not audit["chosen_route_coverage"]["sufficient"],
        "evidence_utilization_or_grounding_failure": not audit["plan_evidence_grounding"]["fully_grounded"],
        "planning_constraint_failure": bool(delivered and audit["chosen_route_coverage"]["sufficient"] and
                                             audit["plan_evidence_grounding"]["fully_grounded"] and not final_pass),
    }
    if final_pass:
        primary = "success"
    else:
        primary = next((name for name in ("non_delivery_or_agent_control", "tool_execution_failure",
                       "evidence_insufficient_for_chosen_plan", "evidence_utilization_or_grounding_failure",
                       "planning_constraint_failure") if flags[name]), "planning_constraint_failure")
    audit["environment_validity"] = {"official_sandbox_pass": sandbox}
    audit["failure_flags"] = flags
    audit["primary_failure_category"] = primary
    return audit
