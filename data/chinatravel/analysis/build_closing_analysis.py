from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
RUNS = ROOT / "runs"
PILOT = ROOT / "experiments" / "ct-pilot-v1"
OUT = ROOT / "analysis"
GROUNDING_DIR = OUT / "grounding"
OFFICIAL_DB = WORKSPACE / "ChinaTravel" / "chinatravel" / "environment" / "database"
TP_SUMMARY = WORKSPACE / "TravelPlanner" / "agent_baseline" / "analysis" / "analysis_summary.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def numeric_equal(left: Any, right: Any, tolerance: float = 0.02) -> bool:
    try:
        return math.isclose(float(left), float(right), abs_tol=tolerance)
    except (TypeError, ValueError):
        return False


def is_generic_position(value: Any) -> bool:
    text = str(value or "").strip()
    return (
        not text
        or text.endswith("附近")
        or text in {"酒店", "市区酒店", "武汉市区酒店", "酒店餐厅", "当地餐厅", "火车站", "机场"}
        or ("市区" in text and text.endswith("酒店"))
    )


def rows_from_data(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        return [row for row in data["rows"] if isinstance(row, dict)]
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def load_trajectory(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def observed_catalog(trajectory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    catalog = []
    for turn in trajectory:
        for call in turn.get("executed_tools", []):
            result = call.get("tool_result", {})
            for row_id, row in enumerate(rows_from_data(result.get("data"))):
                catalog.append({
                    "ref": f"tool-{call.get('tool_call_index')}-row-{row_id}",
                    "tool_name": call.get("tool_name"),
                    "tool_arguments": call.get("tool_arguments", {}),
                    "row": row,
                })
    return catalog


def load_sandbox_catalog() -> dict[str, list[dict[str, Any]]]:
    catalog: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for category in ("attractions", "restaurants", "accommodations"):
        for path in (OFFICIAL_DB / category).rglob("*.csv"):
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    if row.get("name"):
                        catalog[category].append(row)
    airplane = OFFICIAL_DB / "intercity_transport" / "airplane.jsonl"
    for line in airplane.read_text(encoding="utf-8").splitlines():
        if line.strip():
            catalog["intercity"].append(json.loads(line))
    for path in (OFFICIAL_DB / "intercity_transport" / "train").rglob("*.json"):
        value = read_json(path)
        if isinstance(value, list):
            catalog["intercity"].extend(row for row in value if isinstance(row, dict))
    return catalog


def row_value(row: dict[str, Any], *names: str) -> Any:
    lowered = {str(key).casefold(): value for key, value in row.items()}
    for name in names:
        if name.casefold() in lowered:
            return lowered[name.casefold()]
    return None


def find_observed_activity(activity: dict[str, Any], catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kind = activity.get("type")
    if kind in {"train", "airplane"}:
        key = "TrainID" if kind == "train" else "FlightID"
        identifier = norm(activity.get(key))
        return [item for item in catalog if norm(row_value(item["row"], key)) == identifier and identifier]
    position = norm(activity.get("position"))
    return [item for item in catalog if norm(row_value(item["row"], "name")) == position and position]


def sandbox_candidates(activity: dict[str, Any], sandbox: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    kind = activity.get("type")
    if kind in {"train", "airplane"}:
        key = "TrainID" if kind == "train" else "FlightID"
        identifier = norm(activity.get(key))
        return [row for row in sandbox["intercity"] if norm(row_value(row, key)) == identifier and identifier]
    category = {
        "attraction": "attractions", "accommodation": "accommodations",
        "breakfast": "restaurants", "lunch": "restaurants", "dinner": "restaurants",
    }.get(kind)
    position = norm(activity.get("position"))
    return [row for row in sandbox.get(category or "", []) if norm(row_value(row, "name")) == position and position]


def activity_field_checks(activity: dict[str, Any], evidence: dict[str, Any]) -> dict[str, bool]:
    row = evidence["row"]
    kind = activity.get("type")
    checks: dict[str, bool] = {}
    if kind in {"train", "airplane"}:
        checks["start"] = norm(activity.get("start")) == norm(row_value(row, "From", "start"))
        checks["end"] = norm(activity.get("end")) == norm(row_value(row, "To", "end"))
        checks["start_time"] = norm(activity.get("start_time")) == norm(row_value(row, "BeginTime", "start_time"))
        checks["end_time"] = norm(activity.get("end_time")) == norm(row_value(row, "EndTime", "end_time"))
        checks["price"] = numeric_equal(activity.get("price"), row_value(row, "Cost", "price"))
    else:
        checks["price"] = numeric_equal(activity.get("price"), row_value(row, "price"))
        if kind == "accommodation" and activity.get("room_type") is not None:
            checks["room_type"] = numeric_equal(activity.get("room_type"), row_value(row, "numbed"), 0)
    return checks


def audit_transport(day: int, activity_index: int, transport_index: int, transport: dict[str, Any], catalog: list[dict[str, Any]]) -> dict[str, Any]:
    matches = []
    for item in catalog:
        row = item["row"]
        if (
            norm(row_value(row, "start")) == norm(transport.get("start"))
            and norm(row_value(row, "end")) == norm(transport.get("end"))
            and norm(row_value(row, "mode")) == norm(transport.get("mode"))
        ):
            matches.append(item)
    if not matches:
        status = "not_retrieved_or_fabricated"
        checks = {}
        ref = None
    else:
        chosen = matches[0]
        row = chosen["row"]
        checks = {
            "start_time": norm(transport.get("start_time")) == norm(row_value(row, "start_time")),
            "end_time": norm(transport.get("end_time")) == norm(row_value(row, "end_time")),
            "cost": numeric_equal(transport.get("cost"), row_value(row, "cost")),
            "distance": numeric_equal(transport.get("distance"), row_value(row, "distance")),
        }
        status = "retrieved_and_used_consistently" if all(checks.values()) else "retrieved_but_used_inconsistently"
        ref = chosen["ref"]
    return {
        "day": day, "activity_index": activity_index, "transport_index": transport_index,
        "start": transport.get("start"), "end": transport.get("end"), "mode": transport.get("mode"),
        "status": status, "evidence_ref": ref, "field_checks": checks,
    }


def audit_run(label: str, key: str, run_name: str, sandbox: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    run_dir = RUNS / run_name
    usage = read_json(run_dir / "usage.json")
    evaluation = read_json(run_dir / "evaluation.json")
    parse = read_json(run_dir / "parse_result.json")
    trajectory = load_trajectory(run_dir / "trajectory.jsonl")
    catalog = observed_catalog(trajectory)
    plan_path = run_dir / "evaluator_ready.json"
    plan = read_json(plan_path) if plan_path.exists() else None
    activities = []
    transports = []
    if plan:
        for day_obj in plan.get("itinerary", []):
            day = day_obj.get("day")
            for activity_index, activity in enumerate(day_obj.get("activities", [])):
                observed = find_observed_activity(activity, catalog)
                sandbox_rows = sandbox_candidates(activity, sandbox)
                if observed:
                    checks = activity_field_checks(activity, observed[0])
                    status = "retrieved_and_used_consistently" if all(checks.values()) else "retrieved_but_used_inconsistently"
                    ref = observed[0]["ref"]
                elif sandbox_rows:
                    checks = {}
                    status = "not_retrieved_but_exists_in_sandbox"
                    ref = None
                else:
                    checks = {}
                    status = "generic_placeholder" if is_generic_position(activity.get("position")) else "fabricated_or_invalid"
                    ref = None
                activities.append({
                    "day": day, "activity_index": activity_index, "type": activity.get("type"),
                    "entity": activity.get("TrainID") or activity.get("FlightID") or activity.get("position"),
                    "status": status, "evidence_ref": ref, "field_checks": checks,
                })
                for transport_index, transport in enumerate(activity.get("transports", [])):
                    transports.append(audit_transport(day, activity_index, transport_index, transport, catalog))
    status_counts = Counter(item["status"] for item in activities)
    transport_counts = Counter(item["status"] for item in transports)
    retrieved = sum(value for key_name, value in status_counts.items() if key_name.startswith("retrieved_"))
    consistent = status_counts["retrieved_and_used_consistently"]
    grounded_micro = retrieved / len(activities) if activities else 0.0
    consistent_micro = consistent / len(activities) if activities else 0.0
    transport_grounded = sum(value for key_name, value in transport_counts.items() if key_name.startswith("retrieved_"))
    transport_micro = transport_grounded / len(transports) if transports else (1.0 if activities else 0.0)
    full_grounding = bool(activities) and retrieved == len(activities) and transport_grounded == len(transports)
    final_response = usage.get("termination") == "finalized_response"
    schema_delivery = bool(evaluation.get("schema_pass"))
    if not final_response:
        primary = "agent_control_exhaustion"
    elif usage.get("tool_calls", 0) == 0:
        primary = "evidence_free_false_stop"
    elif not schema_delivery:
        primary = "output_contract_failure"
    elif status_counts["fabricated_or_invalid"] or status_counts["generic_placeholder"]:
        primary = "direct_fabrication_or_generic_entity"
    elif status_counts["not_retrieved_but_exists_in_sandbox"]:
        primary = "information_acquisition_missing"
    elif status_counts["retrieved_but_used_inconsistently"] or transport_counts["retrieved_but_used_inconsistently"]:
        primary = "evidence_utilization_failure"
    elif not evaluation.get("all_pass"):
        primary = "execution_consistency_or_constraint_failure"
    else:
        primary = "success"
    planner_flags = []
    planner_audit = run_dir / "planner_audit.json"
    if planner_audit.exists():
        planner_flags = read_json(planner_audit).get("audit_flags", [])
    return {
        "baseline": label, "sample_key": key, "run_id": run_name,
        "split": key.split(":", 1)[0], "uid": key.split(":", 1)[1],
        "termination": usage.get("termination"), "model_calls": usage.get("model_calls", 0),
        "tool_calls": usage.get("tool_calls", 0), "total_tokens": usage.get("total_tokens", 0),
        "latency_seconds": usage.get("latency_seconds", 0), "final_response": final_response,
        "schema_delivery": schema_delivery, "environment_pass": bool(evaluation.get("commonsense_pass")),
        "logical_pass": bool(evaluation.get("logical_pass")), "all_pass": bool(evaluation.get("all_pass")),
        "schema_errors": parse.get("schema_errors", []), "planner_flags": planner_flags,
        "observed_row_count": len(catalog), "activity_count": len(activities),
        "activity_status_counts": dict(status_counts), "activity_grounding_micro": grounded_micro,
        "activity_consistency_micro": consistent_micro, "transport_count": len(transports),
        "transport_status_counts": dict(transport_counts), "transport_grounding_micro": transport_micro,
        "fully_grounded_plan": full_grounding, "any_observation_delivery": schema_delivery and usage.get("tool_calls", 0) > 0,
        "primary_failure": primary, "activities": activities, "transports": transports,
    }


def mean(rows: list[dict[str, Any]], field: str) -> float:
    return sum(float(row.get(field, 0) or 0) for row in rows) / len(rows) if rows else 0.0


def layer_metrics(label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    count = lambda field: sum(bool(row.get(field)) for row in rows)
    return {
        "baseline": label, "n": n,
        "layer_1_agent_control": {"final_response_count": count("final_response"), "final_response_rate": count("final_response") / n},
        "layer_2_output_contract": {"schema_delivery_count": count("schema_delivery"), "schema_delivery_rate": count("schema_delivery") / n},
        "layer_3_evidence_grounding": {
            "any_observation_delivery_count": count("any_observation_delivery"),
            "fully_grounded_plan_count": count("fully_grounded_plan"),
            "activity_grounding_micro": sum(r["activity_status_counts"].get("retrieved_and_used_consistently", 0) + r["activity_status_counts"].get("retrieved_but_used_inconsistently", 0) for r in rows) / max(1, sum(r["activity_count"] for r in rows)),
            "activity_consistency_micro": sum(r["activity_status_counts"].get("retrieved_and_used_consistently", 0) for r in rows) / max(1, sum(r["activity_count"] for r in rows)),
            "transport_grounding_micro": sum(r["transport_status_counts"].get("retrieved_and_used_consistently", 0) + r["transport_status_counts"].get("retrieved_but_used_inconsistently", 0) for r in rows) / max(1, sum(r["transport_count"] for r in rows)),
        },
        "layer_4_official_correctness": {
            "environment_pass_count": count("environment_pass"), "logical_pass_count": count("logical_pass"),
            "schema_and_environment_pass_count": sum(r["schema_delivery"] and r["environment_pass"] for r in rows),
            "schema_and_logical_pass_count": sum(r["schema_delivery"] and r["logical_pass"] for r in rows),
            "all_pass_count": count("all_pass"), "all_pass_rate": count("all_pass") / n,
        },
        "cost": {"mean_tokens": mean(rows, "total_tokens"), "mean_tool_calls": mean(rows, "tool_calls"), "mean_latency_seconds": mean(rows, "latency_seconds")},
    }


CASE_KEYS = [
    ("C", "medium:e20241028161334777418", "零工具伪 Delivery"),
    ("C", "human:h20241029143736524841", "Planner 实体注入与零工具生成"),
    ("C", "easy:m20241028164815894420", "及时停止但约束仍失败"),
    ("C", "medium:e20241028161327496043", "检索后证据利用/全局一致性失败"),
    ("C", "easy:m20241028164642633824", "航班字段输出契约回归"),
    ("C", "human:h20241029143832205713", "逻辑通过但 taxi schema near-miss"),
    ("C", "human:h20241029143648613072", "Planner 预填实体且 Executor 耗尽预算"),
    ("B", "human:h20241029143451793119", "无 Planner 条件下持续 Agent-control failure"),
]


def case_cards(audits: dict[str, dict[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    cards = []
    for label, key, title in CASE_KEYS:
        row = audits[label][key]
        peer = audits["C" if label == "B" else "B"][key]
        cards.append({
            "title": title, "baseline": label, "sample_key": key, "run_id": row["run_id"],
            "primary_failure": row["primary_failure"], "planner_flags": row["planner_flags"],
            "terminal": row["termination"], "tool_calls": row["tool_calls"], "tokens": row["total_tokens"],
            "schema_delivery": row["schema_delivery"], "environment_pass": row["environment_pass"],
            "logical_pass": row["logical_pass"], "all_pass": row["all_pass"],
            "activity_status_counts": row["activity_status_counts"], "transport_status_counts": row["transport_status_counts"],
            "paired_peer": {"baseline": peer["baseline"], "run_id": peer["run_id"], "terminal": peer["termination"], "tool_calls": peer["tool_calls"], "tokens": peer["total_tokens"], "schema_delivery": peer["schema_delivery"], "all_pass": peer["all_pass"]},
            "review_files": ["query_visible.json", "planning_blueprint.json" if label == "C" else None, "trajectory.jsonl", "final_raw_response.txt", "parse_result.json", "evaluation.json"],
        })
    for card in cards:
        card["review_files"] = [item for item in card["review_files"] if item]
    return cards


def render_case_cards(cards: list[dict[str, Any]]) -> str:
    lines = ["# CT-B / CT-C 代表性案例卡", "", "所有卡片由冻结 run 的只读审计生成；案例用于解释机制，不替代频率统计。", ""]
    for index, card in enumerate(cards, 1):
        lines.extend([
            f"## {index}. {card['title']}", "",
            f"- 样本：`{card['sample_key']}`；条件：{card['baseline']}；run：`{card['run_id']}`",
            f"- 主失败：`{card['primary_failure']}`；终态：`{card['terminal']}`",
            f"- 工具/Token：{card['tool_calls']} / {card['tokens']:,}",
            f"- Schema / Environment / Logical / All：{card['schema_delivery']} / {card['environment_pass']} / {card['logical_pass']} / {card['all_pass']}",
            f"- 主实体 grounding：`{card['activity_status_counts']}`",
            f"- 市内交通 grounding：`{card['transport_status_counts']}`",
            f"- Planner flags：`{card['planner_flags']}`",
            f"- 对照条件：{card['paired_peer']['baseline']}，terminal={card['paired_peer']['terminal']}，tools={card['paired_peer']['tool_calls']}，tokens={card['paired_peer']['tokens']:,}，schema={card['paired_peer']['schema_delivery']}",
            f"- 复核文件：{', '.join('`' + name + '`' for name in card['review_files'])}", "",
        ])
    return "\n".join(lines)


def build_cross_benchmark(ct_layers: dict[str, Any]) -> dict[str, Any]:
    tp = read_json(TP_SUMMARY)
    metrics = {row["stage"]: row for row in tp["main_metrics"]}
    tp_b, tp_c = metrics["B"], metrics["C"]
    ct_b, ct_c = ct_layers["B"], ct_layers["C"]
    return {
        "comparison_scope": {"TravelPlanner": "180 validation samples, official evaluator", "ChinaTravel": "12-query paired pilot, official evaluator"},
        "not_directly_comparable": ["absolute metric values", "evaluator semantics", "sample size", "task distribution"],
        "travelplanner_b_to_c": {
            "delivery_delta_pp": (tp_c["delivery_rate"] - tp_b["delivery_rate"]) * 100,
            "final_pass_delta_pp": (tp_c["final_pass"] - tp_b["final_pass"]) * 100,
            "tokens_per_sample_delta_percent": (tp_c["tokens_per_sample"] / tp_b["tokens_per_sample"] - 1) * 100,
            "tool_calls_delta_percent": (tp_c["mean_tool_calls"] / tp_b["mean_tool_calls"] - 1) * 100,
        },
        "chinatravel_b_to_c": {
            "final_response_delta_pp": (ct_c["layer_1_agent_control"]["final_response_rate"] - ct_b["layer_1_agent_control"]["final_response_rate"]) * 100,
            "schema_delivery_delta_pp": (ct_c["layer_2_output_contract"]["schema_delivery_rate"] - ct_b["layer_2_output_contract"]["schema_delivery_rate"]) * 100,
            "all_pass_delta_pp": (ct_c["layer_4_official_correctness"]["all_pass_rate"] - ct_b["layer_4_official_correctness"]["all_pass_rate"]) * 100,
            "overall_tokens_delta_percent": (ct_c["cost"]["mean_tokens"] / ct_b["cost"]["mean_tokens"] - 1) * 100,
            "overall_tool_calls_delta_percent": (ct_c["cost"]["mean_tool_calls"] / ct_b["cost"]["mean_tool_calls"] - 1) * 100,
            "tool_positive_sensitivity": {"tokens_delta_percent": 2.92, "tool_calls_delta_percent": -1.38, "latency_delta_percent": 11.75},
        },
        "shared_findings": [
            "Explicit Planner modestly improves agent-control/termination but does not materially improve final correctness.",
            "Blueprint creation does not guarantee Executor adherence.",
            "Information acquisition and evidence utilization remain bottlenecks after adding Planner.",
            "Efficiency conclusions are sensitive to failure behavior and must not be inferred from aggregate token means alone.",
        ],
        "chinatravel_specific_findings": [
            "Natural-language constraint representation adds source fidelity, hard/soft classification, and entity-injection failures.",
            "JSON-mode blank responses plus the no-tool termination rule can create evidence-free false delivery.",
            "Output-schema failures exactly offset additional final responses in the 12-query pilot.",
        ],
        "conclusion": "Across both benchmarks, Planner is better supported as a control/representation aid than as a correctness mechanism. ChinaTravel adds natural-language and protocol-grounding failure layers, but n=12 is not sufficient for strong prevalence claims.",
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sandbox = load_sandbox_catalog()
    states = {
        "B": read_json(PILOT / "state.json")["completed"],
        "C": read_json(PILOT / "state_ct_c.json")["completed"],
    }
    audits: dict[str, dict[str, dict[str, Any]]] = {"B": {}, "C": {}}
    flat = []
    for label, state in states.items():
        for key, run_name in state.items():
            audit = audit_run(label, key, run_name, sandbox)
            audits[label][key] = audit
            flat.append(audit)
            write_json(GROUNDING_DIR / label / f"{key.replace(':', '__')}.json", audit)
    write_json(OUT / "grounding_audit.json", {"version": "ct-grounding-v1.0", "rows": flat})
    with (OUT / "grounding_entities.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["baseline", "sample_key", "run_id", "day", "activity_index", "type", "entity", "status", "evidence_ref", "field_checks"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in flat:
            for item in row["activities"]:
                writer.writerow({"baseline": row["baseline"], "sample_key": row["sample_key"], "run_id": row["run_id"], **item, "field_checks": json.dumps(item["field_checks"], ensure_ascii=False)})
    layers = {label: layer_metrics(label, list(audits[label].values())) for label in ("B", "C")}
    write_json(OUT / "four_layer_metrics.json", layers)
    with (OUT / "four_layer_metrics.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["baseline", "final_response", "schema_delivery", "any_observation_delivery", "fully_grounded_plan", "activity_grounding_micro", "activity_consistency_micro", "transport_grounding_micro", "environment_pass", "logical_pass", "schema_and_environment_pass", "schema_and_logical_pass", "all_pass", "mean_tokens", "mean_tools", "mean_latency"])
        for label, item in layers.items():
            writer.writerow([label, item["layer_1_agent_control"]["final_response_count"], item["layer_2_output_contract"]["schema_delivery_count"], item["layer_3_evidence_grounding"]["any_observation_delivery_count"], item["layer_3_evidence_grounding"]["fully_grounded_plan_count"], item["layer_3_evidence_grounding"]["activity_grounding_micro"], item["layer_3_evidence_grounding"]["activity_consistency_micro"], item["layer_3_evidence_grounding"]["transport_grounding_micro"], item["layer_4_official_correctness"]["environment_pass_count"], item["layer_4_official_correctness"]["logical_pass_count"], item["layer_4_official_correctness"]["schema_and_environment_pass_count"], item["layer_4_official_correctness"]["schema_and_logical_pass_count"], item["layer_4_official_correctness"]["all_pass_count"], item["cost"]["mean_tokens"], item["cost"]["mean_tool_calls"], item["cost"]["mean_latency_seconds"]])
    taxonomy = []
    for label in ("B", "C"):
        counts = Counter(row["primary_failure"] for row in audits[label].values())
        for category, count in sorted(counts.items()):
            taxonomy.append({"baseline": label, "category": category, "count": count, "rate": count / 12})
    write_json(OUT / "failure_taxonomy.json", {"priority": ["agent_control_exhaustion", "evidence_free_false_stop", "output_contract_failure", "direct_fabrication_or_generic_entity", "information_acquisition_missing", "evidence_utilization_failure", "execution_consistency_or_constraint_failure", "success"], "rows": taxonomy})
    with (OUT / "failure_taxonomy.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["baseline", "category", "count", "rate"])
        writer.writeheader(); writer.writerows(taxonomy)
    cards = case_cards(audits)
    write_json(OUT / "case_cards.json", cards)
    (OUT / "case_cards.md").write_text(render_case_cards(cards), encoding="utf-8")
    cross = build_cross_benchmark(layers)
    write_json(OUT / "cross_benchmark_comparison.json", cross)
    integrity = {
        "paired_keys_equal": set(audits["B"]) == set(audits["C"]),
        "b_count": len(audits["B"]), "c_count": len(audits["C"]),
        "taxonomy_b_total": sum(row["count"] for row in taxonomy if row["baseline"] == "B"),
        "taxonomy_c_total": sum(row["count"] for row in taxonomy if row["baseline"] == "C"),
        "case_card_count": len(cards), "model_calls_made": 0, "tool_calls_made": 0,
    }
    write_json(OUT / "closing_integrity.json", integrity)
    if not all([integrity["paired_keys_equal"], integrity["b_count"] == 12, integrity["c_count"] == 12, integrity["taxonomy_b_total"] == 12, integrity["taxonomy_c_total"] == 12, integrity["case_card_count"] == 8]):
        raise RuntimeError(f"Closing analysis integrity failure: {integrity}")
    print(json.dumps({"status": "ok", **integrity}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
