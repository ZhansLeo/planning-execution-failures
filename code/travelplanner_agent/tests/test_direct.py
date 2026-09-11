import json
import os
import unittest
from collections import Counter
from unittest.mock import patch

from travelplanner_agent.baselines import DirectBaseline, build_direct_prompt, parse_json_object
from travelplanner_agent.official_adapter import (
    PLAN_FIELDS,
    validate_generated_submission,
    validate_evaluator_format,
    validate_reference_entities,
)
from travelplanner_agent.experiment_runner import development_indices, pilot_indices


QUERY = "Please plan a 3-day trip from A to B."


def day(number: int) -> dict:
    value = {field: "-" for field in PLAN_FIELDS}
    value["days"] = number
    value["current_city"] = "B"
    return value


def submission() -> dict:
    return {"idx": 1, "query": QUERY, "plan": [day(1), day(2), day(3)]}


class DirectContractTests(unittest.TestCase):
    def test_valid_submission(self):
        result = validate_generated_submission(
            submission(), expected_idx=1, expected_query=QUERY
        )
        self.assertTrue(result["valid"])

    def test_missing_and_extra_fields(self):
        value = submission()
        del value["plan"][0]["lunch"]
        value["plan"][0]["note"] = "extra"
        result = validate_generated_submission(value, expected_idx=1, expected_query=QUERY)
        self.assertFalse(result["valid"])
        self.assertIn("missing=['lunch']", result["errors"][0])
        self.assertIn("extra=['note']", result["errors"][0])

    def test_wrong_day_count_and_sequence(self):
        value = submission()
        value["plan"].pop()
        value["plan"][1]["days"] = 7
        result = validate_generated_submission(value, expected_idx=1, expected_query=QUERY)
        self.assertFalse(result["valid"])
        self.assertTrue(any("must contain 3 days" in error for error in result["errors"]))
        self.assertTrue(any("must equal 2" in error for error in result["errors"]))

    def test_strict_parser_rejects_markdown_and_non_json(self):
        raw = json.dumps(submission())
        self.assertEqual(parse_json_object(raw), submission())
        self.assertIsNone(parse_json_object(f"```json\n{raw}\n```"))
        self.assertIsNone(parse_json_object("not json"))
        self.assertIsNone(parse_json_object("[]"))

    def test_prompt_has_inputs_but_no_example_plan(self):
        task = {
            "idx": 1,
            "query": QUERY,
            "reference_information": {"Restaurants in B": [{"Name": "Real Cafe"}]},
        }
        prompt = build_direct_prompt(task)
        self.assertIn(QUERY, prompt)
        self.assertIn("Real Cafe", prompt)
        self.assertNotIn("Catfish Charlie's", prompt)

    def test_missing_key_fails_before_sdk_call(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                DirectBaseline()

    def test_reference_entity_violation_is_reported_only(self):
        value = submission()
        value["plan"][0]["breakfast"] = "Invented Cafe, B"
        reference = {"Restaurants in B": [{"Name": "Real Cafe"}]}
        result = validate_reference_entities(value, reference)
        self.assertFalse(result["valid"])
        self.assertEqual(value["plan"][0]["breakfast"], "Invented Cafe, B")

    def test_evaluator_literal_format(self):
        value = submission()
        value["plan"][0].update(
            {
                "current_city": "from A to B",
                "transportation": "Flight Number: F1234567, from A to B, Departure Time: 08:00, Arrival Time: 09:00",
                "lunch": "Real Cafe, B",
                "attraction": "Real Museum, B; Real Park, B",
                "accommodation": "Real Room, B",
            }
        )
        self.assertTrue(validate_evaluator_format(value)["valid"])
        value["plan"][0]["transportation"] = "Flight F1234567"
        value["plan"][0]["lunch"] = "Real Cafe"
        result = validate_evaluator_format(value)
        self.assertFalse(result["valid"])
        self.assertTrue(any("official flight syntax" in error for error in result["errors"]))
        self.assertTrue(any("Name, City" in error for error in result["errors"]))

    def test_pilot_is_balanced_deterministic_and_excludes_one(self):
        rows = []
        idx = 1
        for level in ("easy", "medium", "hard"):
            for days in (3, 5, 7):
                for _ in range(20):
                    rows.append({"idx": idx, "level": level, "days": days})
                    idx += 1
        first = pilot_indices(rows)
        second = pilot_indices(rows)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 18)
        self.assertNotIn(1, first)
        selected = [row for row in rows if row["idx"] in first]
        counts = Counter((row["level"], row["days"]) for row in selected)
        self.assertEqual(set(counts.values()), {2})

    def test_train_development_is_one_per_cell_and_deterministic(self):
        rows = []
        idx = 1
        for level in ("easy", "medium", "hard"):
            for days in (3, 5, 7):
                for _ in range(5):
                    rows.append({"idx": idx, "level": level, "days": days})
                    idx += 1
        selected = development_indices(rows)
        self.assertEqual(selected, development_indices(rows))
        self.assertEqual(len(selected), 9)
        counts = Counter((row["level"], row["days"]) for row in rows if row["idx"] in selected)
        self.assertEqual(set(counts.values()), {1})


if __name__ == "__main__":
    unittest.main()
