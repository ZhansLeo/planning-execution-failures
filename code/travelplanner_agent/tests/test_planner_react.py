import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from travelplanner_agent.baselines import (PLANNER_MAX_OUTPUT_TOKENS,
    PlannerReactBaseline, build_planner_prompt, validate_planning_blueprint)
from travelplanner_agent.experiment_runner import _protocol
from travelplanner_agent.planner_audit import build_planner_audit


class FakeToolbox:
    def __init__(self): self.calls = []
    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return {"ok": True, "empty": False, "count": 1, "data": []}


def api_response(content=None, calls=None, tokens=10):
    tool_calls = [SimpleNamespace(id=f"call-{i}", function=SimpleNamespace(
        name=name, arguments=json.dumps(args))) for i, (name, args) in enumerate(calls or [])]
    return SimpleNamespace(id="request", choices=[SimpleNamespace(message=SimpleNamespace(
        content=content, tool_calls=tool_calls))], usage=SimpleNamespace(
        prompt_tokens=tokens, completion_tokens=2, total_tokens=tokens + 2))


def blueprint():
    return {
        "trip_facts": {"origin": "Boston", "destinations": ["Austin"],
                       "days": 3, "travelers": 2, "budget": "$2000"},
        "global_route": [{"city": "Austin", "arrival_day": 1,
                          "departure_day": 3, "nights": 2}],
        "constraint_ledger": [{"constraint": "budget", "requirement": "$2000",
                               "priority": "hard"}],
        "retrieval_checklist": [{"information_type": "restaurant", "city": "Austin",
                                 "origin": None, "destination": None, "date": None}],
        "planning_risks": ["budget"],
    }


class PlannerReactTests(unittest.TestCase):
    def baseline(self, responses):
        box = FakeToolbox()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}):
            with patch("openai.OpenAI") as client:
                client.return_value.chat.completions.create.side_effect = responses
                value = PlannerReactBaseline(toolbox=box)
        return value, box

    def test_blueprint_contract(self):
        self.assertTrue(validate_planning_blueprint(blueprint())["valid"])
        bad = blueprint(); bad["extra"] = True
        self.assertFalse(validate_planning_blueprint(bad)["valid"])
        bad = blueprint(); bad["global_route"][0]["nights"] = 9
        self.assertFalse(validate_planning_blueprint(bad)["valid"])

    def test_planner_prompt_excludes_oracle(self):
        prompt = build_planner_prompt({"idx": 1, "query": "q",
                                       "reference_information": {"SECRET": "leak"}})
        self.assertNotIn("SECRET", prompt)
        self.assertNotIn("leak", prompt)

    def test_valid_planner_tool_and_final(self):
        final = {"idx": 1, "query": "q", "plan": []}
        agent, box = self.baseline([
            api_response(content=json.dumps(blueprint())),
            api_response(calls=[("restaurant_search", {"city": "Austin"})]),
            api_response(content=json.dumps(final)),
        ])
        result = agent.generate({"idx": 1, "query": "q"})
        self.assertEqual(result.terminal_reason, "final_response")
        self.assertEqual(result.model_calls, 3)
        self.assertEqual(result.tool_calls, 1)
        self.assertEqual(box.calls, [("restaurant_search", {"city": "Austin"})])
        first = agent.client.chat.completions.create.call_args_list[0].kwargs
        self.assertEqual(first["max_tokens"], PLANNER_MAX_OUTPUT_TOKENS)
        self.assertNotIn("tools", first)

    def test_invalid_planner_stops_before_tools(self):
        agent, box = self.baseline([api_response(content='{"trip_facts": {}}')])
        result = agent.generate({"idx": 1, "query": "q"})
        self.assertEqual(result.terminal_reason, "planner_invalid")
        self.assertEqual(result.model_calls, 1)
        self.assertEqual(box.calls, [])

    def test_b_c_execution_limits_match(self):
        args = dict(model="deepseek-chat", base_url="https://api.deepseek.com",
                    timeout=120.0, max_retries=2)
        b, c = _protocol("react", **args), _protocol("planner-react", **args)
        for key in ("tool_schema_hash", "max_tool_calls", "max_context_tokens",
                    "max_output_tokens", "multi_tool_call_policy",
                    "evidence_audit_version"):
            self.assertEqual(b[key], c[key])
        self.assertFalse(c["observation_compression"])
        self.assertFalse(c["scripted_retrieval"])

    def test_planner_audit_checklist_and_route(self):
        plan = {"plan": [{"current_city": "from Boston to Austin"}]}
        trajectory = [{"tool": "restaurant_search", "arguments": {"city": "Austin"},
                       "status": "success", "observation": {"ok": True}}]
        audit = build_planner_audit(query="3 days budget $2000", planner_raw_response="{}",
            blueprint=blueprint(), validation={"valid": True, "errors": []},
            planner_usage={}, planner_latency_seconds=1.0, planner_request_id="r",
            trajectory=trajectory, submission=plan)
        self.assertEqual(audit["retrieval_checklist"]["rate"], 1.0)
        self.assertTrue(audit["route_consistency"]["consistent"])


if __name__ == "__main__":
    unittest.main()
