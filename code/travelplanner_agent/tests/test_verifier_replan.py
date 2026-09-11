import unittest

from travelplanner_agent.experiment_runner import _protocol
from travelplanner_agent.verifier_replan import (build_evidence_catalog,
    build_verifier_prompt, select_replan_evidence, validate_verifier_report)


class VerifierReplanContractTests(unittest.TestCase):
    def setUp(self):
        self.catalog = build_evidence_catalog([{"step": 2, "tool": "restaurant_search",
            "arguments": {"city": "Austin"}, "observation": {"ok": True, "data": [
                {"Name": "Cafe One", "City": "Austin"},
                {"Name": "Cafe Two", "City": "Austin"}]}}])

    def test_catalog_ids_are_stable_and_ordered(self):
        self.assertEqual([x["id"] for x in self.catalog["entries"]],
                         ["tool-2-row-1", "tool-2-row-2"])

    def test_verifier_schema_and_grounding_audit(self):
        report = {"verdict": "repair", "candidate_parseable": True,
                  "issues": [{"category": "grounding", "severity": "error", "day": 1,
                              "field": "lunch", "description": "unsupported",
                              "evidence_refs": ["tool-2-row-1"]}],
                  "repair_instructions": ["Use Cafe One"]}
        valid = validate_verifier_report(report, {"tool-2-row-1", "tool-2-row-2"})
        self.assertTrue(valid["valid"]); self.assertTrue(valid["evidence_grounded"])
        report["issues"][0]["evidence_refs"] = ["made-up"]
        audit = validate_verifier_report(report, {"tool-2-row-1"})
        self.assertTrue(audit["valid"]); self.assertFalse(audit["evidence_grounded"])

    def test_invalid_verdict_and_pass_with_issues_fail(self):
        bad = {"verdict": "pass", "candidate_parseable": True,
               "issues": [{"category": "format", "severity": "error", "day": None,
                           "field": None, "description": "bad", "evidence_refs": []}],
               "repair_instructions": []}
        self.assertFalse(validate_verifier_report(bad, set())["valid"])

    def test_prompt_excludes_oracle(self):
        task = {"idx": 1, "query": "q", "reference_information": {"SECRET": "leak"}}
        prompt = build_verifier_prompt(task=task, blueprint={}, candidate_raw="{}",
                                       candidate_parsed={}, catalog=self.catalog)
        self.assertNotIn("SECRET", prompt); self.assertNotIn("leak", prompt)

    def test_replan_evidence_is_only_cited_or_already_used(self):
        report = {"issues": [{"evidence_refs": ["tool-2-row-2"]}]}
        selected = select_replan_evidence(self.catalog, report, "Cafe One, Austin")
        self.assertEqual({x["id"] for x in selected}, {"tool-2-row-1", "tool-2-row-2"})

    def test_c_d_frozen_execution_invariants(self):
        args = dict(model="deepseek-chat", base_url="https://api.deepseek.com",
                    timeout=120.0, max_retries=2)
        c, d = _protocol("planner-react", **args), _protocol("verifier-replan", **args)
        for key in ("tool_schema_hash", "max_tool_calls", "max_context_tokens",
                    "max_output_tokens", "multi_tool_call_policy", "planner_max_output_tokens",
                    "planner_audit_version", "observation_compression", "scripted_retrieval"):
            self.assertEqual(c[key], d[key])
        self.assertFalse(d["replan_tools"]); self.assertEqual(d["verifier_calls_max"], 1)
        self.assertEqual(d["replan_calls_max"], 1)


if __name__ == "__main__": unittest.main()
