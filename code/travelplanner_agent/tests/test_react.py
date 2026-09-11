import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from travelplanner_agent.baselines import ReactBaseline, build_react_prompt
from travelplanner_agent.react_tools import TOOL_SCHEMAS, tool_schema_hash


class FakeToolbox:
    def __init__(self): self.calls = []
    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return {"ok": True, "empty": False, "count": 1, "data": [{"Name": "Cafe"}]}


def response(*, content=None, calls=None, tokens=10):
    tool_calls = []
    for i, (name, arguments) in enumerate(calls or []):
        tool_calls.append(SimpleNamespace(id=f"call-{i}", function=SimpleNamespace(name=name, arguments=json.dumps(arguments))))
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    usage = SimpleNamespace(prompt_tokens=tokens, completion_tokens=2, total_tokens=tokens + 2)
    return SimpleNamespace(id="request", choices=[SimpleNamespace(message=message)], usage=usage)


class ReactTests(unittest.TestCase):
    def baseline(self, responses, **kwargs):
        box = FakeToolbox()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}):
            with patch("openai.OpenAI") as client:
                client.return_value.chat.completions.create.side_effect = responses
                value = ReactBaseline(toolbox=box, **kwargs)
        return value, box

    def test_tool_schema_hash_is_deterministic_and_six_tools(self):
        self.assertEqual(len(TOOL_SCHEMAS), 6)
        self.assertEqual(tool_schema_hash(), tool_schema_hash())

    def test_model_prompt_cannot_include_oracle_reference(self):
        task = {"idx": 1, "query": "q", "reference_information": {"SECRET_ORACLE": "leak"}}
        prompt = build_react_prompt(task)
        self.assertNotIn("SECRET_ORACLE", prompt)
        self.assertNotIn("leak", prompt)

    def test_tool_then_final_json(self):
        final = {"idx": 1, "query": "q", "plan": []}
        agent, box = self.baseline([
            response(calls=[("restaurant_search", {"city": "Boston"})]),
            response(content=json.dumps(final)),
        ])
        result = agent.generate({"idx": 1, "query": "q"})
        self.assertEqual(result.parsed_response, final)
        self.assertEqual(result.terminal_reason, "final_response")
        self.assertEqual(result.model_calls, 2)
        self.assertEqual(result.tool_calls, 1)
        self.assertEqual(box.calls, [("restaurant_search", {"city": "Boston"})])

    def test_api_disables_parallel_tool_calls(self):
        final = {"idx": 1, "query": "q", "plan": []}
        agent, _ = self.baseline([response(content=json.dumps(final))])
        agent.generate({"idx": 1, "query": "q"})
        kwargs = agent.client.chat.completions.create.call_args.kwargs
        self.assertIs(kwargs["parallel_tool_calls"], False)

    def test_three_identical_calls_terminate_without_third_execution(self):
        repeated = response(calls=[("city_search", {"state": "Texas"})])
        agent, box = self.baseline([repeated, repeated, repeated])
        result = agent.generate({"idx": 1, "query": "q"})
        self.assertEqual(result.terminal_reason, "repeated_tool_call")
        self.assertEqual(len(box.calls), 2)

    def test_multiple_tool_calls_are_executed_in_recorded_order(self):
        final = {"idx": 1, "query": "q", "plan": []}
        agent, box = self.baseline([response(calls=[
            ("city_search", {"state": "Texas"}),
            ("city_search", {"state": "Ohio"}),
        ]), response(content=json.dumps(final))])
        result = agent.generate({"idx": 1, "query": "q"})
        self.assertEqual(result.terminal_reason, "final_response")
        self.assertEqual(result.tool_calls, 2)
        self.assertEqual([args["state"] for _, args in box.calls], ["Texas", "Ohio"])
        self.assertEqual([step["batch_position"] for step in result.trajectory], [1, 2])

    def test_context_limit_before_model_call(self):
        agent, _ = self.baseline([], max_context_tokens=1)
        result = agent.generate({"idx": 1, "query": "q"})
        self.assertEqual(result.terminal_reason, "context_limit")
        self.assertEqual(result.model_calls, 0)

    def test_missing_key_fails_before_model_or_tool_call(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                ReactBaseline(toolbox=FakeToolbox())


if __name__ == "__main__":
    unittest.main()
