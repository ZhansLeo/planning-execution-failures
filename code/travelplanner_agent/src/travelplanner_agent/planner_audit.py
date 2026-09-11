"""Deterministic audits for the Stage-C explicit planning blueprint."""

from __future__ import annotations

import re
from typing import Any

PLANNER_AUDIT_VERSION = "planner-audit-v1.0"


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _successful_calls(trajectory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [x for x in trajectory if x.get("status") == "success" and x.get("observation", {}).get("ok")]


def _checklist_item_completed(item: dict[str, Any], calls: list[dict[str, Any]]) -> bool:
    kind = _norm(item.get("information_type"))
    aliases = {"flight": "flight_search", "restaurant": "restaurant_search",
               "attraction": "attraction_search", "accommodation": "accommodation_search",
               "distance": "distance_matrix", "ground_transportation": "distance_matrix"}
    tool = aliases.get(kind, kind)
    for call in calls:
        if call.get("tool") != tool:
            continue
        args = call.get("arguments") or {}
        compared = False
        matched = True
        for field in ("city", "origin", "destination"):
            expected = item.get(field)
            if expected not in (None, "", "-"):
                compared = True
                matched = matched and _norm(args.get(field)) == _norm(expected)
        expected_date = item.get("date")
        if expected_date not in (None, "", "-") and tool == "flight_search":
            compared = True
            matched = matched and _norm(args.get("departure_date")) == _norm(expected_date)
        if matched and (compared or call.get("tool") == tool):
            return True
    return False


def _planned_cities(blueprint: dict[str, Any] | None) -> list[str]:
    if not isinstance(blueprint, dict):
        return []
    return [str(x.get("city", "")).strip() for x in blueprint.get("global_route", [])
            if isinstance(x, dict) and str(x.get("city", "")).strip()]


def _final_cities(submission: dict[str, Any] | None) -> list[str]:
    cities: list[str] = []
    plan = submission.get("plan", []) if isinstance(submission, dict) else []
    for day in plan:
        if not isinstance(day, dict):
            continue
        value = str(day.get("current_city", "")).strip()
        match = re.match(r"^from .+? to (.+)$", value, re.IGNORECASE)
        city = match.group(1).strip() if match else value
        if city and city != "-" and (not cities or _norm(cities[-1]) != _norm(city)):
            cities.append(city)
    return cities


def build_planner_audit(*, query: str, planner_raw_response: str,
                        blueprint: dict[str, Any] | None, validation: dict[str, Any],
                        planner_usage: dict[str, Any], planner_latency_seconds: float,
                        planner_request_id: str | None, trajectory: list[dict[str, Any]],
                        submission: dict[str, Any] | None) -> dict[str, Any]:
    calls = _successful_calls(trajectory)
    checklist = blueprint.get("retrieval_checklist", []) if isinstance(blueprint, dict) else []
    checklist_rows = [{**item, "completed": _checklist_item_completed(item, calls)}
                      for item in checklist if isinstance(item, dict)]
    planned = _planned_cities(blueprint)
    final = _final_cities(submission)
    planned_set, final_set = {_norm(x) for x in planned}, {_norm(x) for x in final}
    route_consistent = bool(planned_set) and planned_set.issubset(final_set)

    query_lower = query.casefold()
    categories = {
        "budget": ("budget", "$"), "transportation": ("transportation", "flight", "drive", "taxi"),
        "cuisine": ("cuisine", "food"), "room_type": ("room",),
        "house_rule": ("smoking", "parties", "pets"),
    }
    required = [name for name, words in categories.items() if any(word in query_lower for word in words)]
    ledger = blueprint.get("constraint_ledger", []) if isinstance(blueprint, dict) else []
    ledger_text = " ".join(_norm(f"{x.get('constraint')} {x.get('requirement')}")
                           for x in ledger if isinstance(x, dict))
    constraint_rows = [{"category": name, "covered": name.replace("_", " ") in ledger_text or
                        any(word in ledger_text for word in categories[name])} for name in required]

    checklist_signatures = {(row.get("information_type"), _norm(row.get("city")),
                             _norm(row.get("origin")), _norm(row.get("destination"))) for row in checklist_rows}
    unplanned = 0
    for call in calls:
        args = call.get("arguments") or {}
        signature = (call.get("tool", "").replace("_search", ""), _norm(args.get("city")),
                     _norm(args.get("origin")), _norm(args.get("destination")))
        if signature not in checklist_signatures:
            unplanned += 1
    return {
        "audit_version": PLANNER_AUDIT_VERSION,
        "reference_information_exposed_to_planner": False,
        "planner_response": {"request_id": planner_request_id, "raw": planner_raw_response,
                             "validation": validation, "usage": planner_usage,
                             "latency_seconds": planner_latency_seconds},
        "query_constraint_coverage": {"requirements": constraint_rows,
                                      "covered": sum(x["covered"] for x in constraint_rows),
                                      "total": len(constraint_rows),
                                      "rate": (sum(x["covered"] for x in constraint_rows) / len(constraint_rows)
                                               if constraint_rows else None)},
        "route_consistency": {"blueprint_cities": planned, "final_cities": final,
                              "consistent": route_consistent if final else None},
        "retrieval_checklist": {"items": checklist_rows,
                                "completed": sum(x["completed"] for x in checklist_rows),
                                "total": len(checklist_rows),
                                "rate": (sum(x["completed"] for x in checklist_rows) / len(checklist_rows)
                                         if checklist_rows else None)},
        "execution_deviation": {"successful_calls": len(calls), "unplanned_calls": unplanned,
                                "unplanned_call_rate": unplanned / len(calls) if calls else None},
    }
