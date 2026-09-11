import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from travelplanner_agent.experiment_runner import run_experiment


def metadata():
    rows = []
    idx = 1
    for level in ("easy", "medium", "hard"):
        for days in (3, 5, 7):
            for _ in range(20):
                rows.append({
                    "idx": idx, "level": level, "days": days,
                    "local_constraint": {
                        "house rule": None, "cuisine": None,
                        "room type": None, "transportation": None,
                    },
                    "query": f"query {idx}",
                })
                idx += 1
    return rows, "test-fingerprint"


class ExperimentResumeTests(unittest.TestCase):
    def test_resume_does_not_repeat_terminal_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []

            def fake_direct(repo, runs_dir, index, **kwargs):
                calls.append(index)
                run_dir = root / f"run-{index}"
                run_dir.mkdir()
                submission = {
                    "idx": index,
                    "query": kwargs["canonical_query"],
                    "plan": [{"days": 1}],
                }
                (run_dir / "submission.jsonl").write_text(
                    json.dumps(submission) + "\n", encoding="utf-8"
                )
                return {
                    "run_dir": str(run_dir), "status": "completed",
                    "retryable": False, "attempt": kwargs["attempt"],
                }

            aggregate_result = {"total": 18, "delivered": 18}
            with (
                patch("travelplanner_agent.experiment_runner.load_validation_metadata", return_value=metadata()),
                patch("travelplanner_agent.experiment_runner.run_direct", side_effect=fake_direct),
                patch("travelplanner_agent.experiment_runner.aggregate_experiment", return_value=aggregate_result),
            ):
                common = dict(
                    repo=root, runs_dir=root / "runs", experiment_id="pilot-test",
                    mode="pilot", model="deepseek-chat",
                    base_url="https://api.deepseek.com", timeout=120.0,
                    max_retries=2,
                )
                run_experiment(**common, resume=False)
                self.assertEqual(len(calls), 18)
                run_experiment(**common, resume=True)
                self.assertEqual(len(calls), 18)

    def test_planner_resume_does_not_repeat_terminal_planner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []

            def fake_planner(repo, runs_dir, index, **kwargs):
                calls.append(index)
                run_dir = root / f"planner-run-{index}"
                run_dir.mkdir()
                (run_dir / "submission.jsonl").write_text(json.dumps({
                    "idx": index, "query": kwargs["canonical_query"], "plan": [{"days": 1}],
                }) + "\n", encoding="utf-8")
                return {"run_dir": str(run_dir), "status": "completed",
                        "retryable": False, "attempt": kwargs["attempt"],
                        "planner_calls": 1}

            with (
                patch("travelplanner_agent.experiment_runner.load_validation_metadata", return_value=metadata()),
                patch("travelplanner_agent.experiment_runner.run_planner_react", side_effect=fake_planner),
                patch("travelplanner_agent.experiment_runner.aggregate_experiment",
                      return_value={"total": 18, "delivered": 18}),
            ):
                common = dict(repo=root, runs_dir=root / "runs", experiment_id="planner-pilot",
                              mode="pilot", model="deepseek-chat",
                              base_url="https://api.deepseek.com", timeout=120.0,
                              max_retries=2, baseline="planner-react")
                run_experiment(**common, resume=False)
                self.assertEqual(len(calls), 18)
                run_experiment(**common, resume=True)
                self.assertEqual(len(calls), 18)


if __name__ == "__main__":
    unittest.main()
