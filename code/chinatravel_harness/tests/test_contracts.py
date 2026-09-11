import json

import pytest
from types import SimpleNamespace

from ct_harness.core import (
    HIDDEN_QUERY_KEYS,
    PLANNER_SCHEMA,
    assert_oracle_absent,
    build_executor_prompt,
    build_planner_messages,
    execute_tool_bundle,
    estimate_context_tokens,
    finalization_message,
    output_schema,
    parse_blueprint,
    strict_parse_plan,
    tool_bundle_signature,
    visible_query,
    create_pilot_manifest,
    DEV_UIDS,
)


def valid_blueprint():
    return {
        "trip_facts": {"start_city": "上海", "target_city": "杭州", "days": 1, "people_number": 1, "budget": 1500, "additional_facts": []},
        "hard_constraints": [{"id": "HC-1", "category": "budget", "requirement": "预算不超过1500元", "source_text": "预算不超过1500元"}],
        "soft_preferences": [],
        "retrieval_checklist": [{"id": "RC-1", "category": "intercity_transport", "city": None, "route": {"start_city": "上海", "end_city": "杭州"}, "purpose": "查询交通", "supports_constraint_ids": ["HC-1"]}],
        "planning_risks": [{"category": "budget", "description": "总费用", "mitigation": "记录费用"}],
    }


def test_oracle_is_removed_from_both_prompt_paths():
    query = {"uid": "x", "nature_language": "测试", "hard_logic_py": ["secret"]}
    public = visible_query(query)
    assert not HIDDEN_QUERY_KEYS & public.keys()
    assert_oracle_absent(build_executor_prompt(public, output_schema()))
    assert_oracle_absent(build_planner_messages(public))


def test_oracle_scanner_rejects_leakage():
    with pytest.raises(RuntimeError):
        assert_oracle_absent({"hard_logic_nl": "secret"})


def test_blueprint_contract_accepts_valid_and_rejects_extra():
    assert parse_blueprint(json.dumps(valid_blueprint(), ensure_ascii=False)) == valid_blueprint()
    bad = valid_blueprint() | {"specific_hotel": "编造酒店"}
    with pytest.raises(Exception):
        parse_blueprint(json.dumps(bad, ensure_ascii=False))


@pytest.mark.parametrize("raw", ["not json", "```json\n{}\n```", "{}"])
def test_blueprint_contract_rejects_non_json_markdown_and_missing_fields(raw):
    with pytest.raises(Exception):
        parse_blueprint(raw)


def test_blueprint_contract_rejects_nested_extra_field():
    bad = valid_blueprint()
    bad["trip_facts"]["invented"] = True
    with pytest.raises(Exception):
        parse_blueprint(json.dumps(bad, ensure_ascii=False))


def test_strict_output_rejects_markdown_and_non_json():
    plan, errors = strict_parse_plan("```json\n{}\n```", output_schema())
    assert plan is None and errors
    plan, errors = strict_parse_plan("not json", output_schema())
    assert plan is None and errors


def test_output_schema_reports_missing_fields():
    plan, errors = strict_parse_plan("{}", output_schema())
    assert plan == {}
    assert errors


def _call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def test_parallel_bundle_executes_serially_in_model_order():
    class Adapter:
        def __init__(self):
            self.names = []

        def call_tool(self, name, arguments):
            self.names.append(name)
            return {"success": True, "name": name, "arguments": arguments}

    adapter = Adapter()
    bundle = [_call("1", "first", {"x": 1}), _call("2", "second", {"x": 2})]
    executed, exceeded = execute_tool_bundle(adapter, bundle, 2)
    assert not exceeded
    assert adapter.names == ["first", "second"]
    assert [item["tool_call_id"] for item in executed] == ["1", "2"]


def test_bundle_budget_is_total_tool_call_budget():
    class Adapter:
        def call_tool(self, name, arguments):
            return {"success": True}

    bundle = [_call("1", "first", {}), _call("2", "second", {})]
    executed, exceeded = execute_tool_bundle(Adapter(), bundle, 1)
    assert exceeded
    assert len(executed) == 1


def test_context_estimator_handles_chinese_and_ascii_deterministically():
    messages = [{"role": "user", "content": "杭州 abc 123"}]
    assert estimate_context_tokens(messages) == estimate_context_tokens(messages)
    assert estimate_context_tokens(messages) > 0


def test_repeat_signature_changes_when_next_page_observation_changes():
    first = [{"tool_name": "next_page", "tool_arguments": {}, "tool_result": {"rows": [1]}}]
    second = [{"tool_name": "next_page", "tool_arguments": {}, "tool_result": {"rows": [2]}}]
    assert tool_bundle_signature(first) != tool_bundle_signature(second)


def test_finalization_turn_disables_tools_by_contract_and_requests_one_json():
    message = finalization_message(output_schema())
    assert message["role"] == "user"
    assert "禁止继续调用工具" in message["content"]
    assert "严格 JSON" in message["content"]


def test_pilot_manifest_is_balanced_and_excludes_development_uids():
    manifest = create_pilot_manifest()
    assert len(manifest["samples"]) == 12
    for split in ("easy", "medium", "human"):
        assert sum(sample["split"] == split for sample in manifest["samples"]) == 4
    assert not DEV_UIDS & {sample["uid"] for sample in manifest["samples"]}
