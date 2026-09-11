import csv
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrozenAnalysisTests(unittest.TestCase):
    def test_freeze_manifest_has_all_stages_and_hashes(self):
        freeze = json.loads((ROOT / "analysis/freeze_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(set(freeze["stages"]), set("ABCD"))
        self.assertEqual(freeze["policy"], "analysis_only_no_model_tool_or_evaluator_calls")
        for value in freeze["stages"].values():
            self.assertEqual(len(value["files"]), 5)
            self.assertTrue(all(len(x) == 64 for x in value["files"].values()))

    def test_standardized_rows_and_taxonomy_are_complete(self):
        with (ROOT / "analysis/standardized_samples.csv").open(encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 720)
        for stage in "ABCD":
            selected = [x for x in rows if x["stage"] == stage]
            self.assertEqual(len(selected), 180)
            self.assertEqual({int(x["idx"]) for x in selected}, set(range(1, 181)))
            self.assertTrue(all(x["unified_failure"] for x in selected))

    def test_paired_and_funnel_counts(self):
        summary = json.loads((ROOT / "analysis/analysis_summary.json").read_text(encoding="utf-8"))
        for row in summary["paired"]:
            self.assertEqual(sum(row[k] for k in ("left_fail_right_fail", "left_fail_right_pass",
                                                   "left_pass_right_fail", "left_pass_right_pass")), 180)
        funnel = list(summary["stage_d_funnel"].values())
        self.assertEqual(funnel[:2], [119, 119])
        self.assertTrue(all(a >= b for a, b in zip(funnel, funnel[1:])))

    def test_ppt_ready_figure_triplets_exist(self):
        figures = ROOT / "analysis/figures"
        for i in range(1, 11):
            prefix = f"{i:02d}_"
            for suffix in (".svg", ".png", ".csv"):
                self.assertEqual(len(list(figures.glob(prefix + "*" + suffix))), 1)


if __name__ == "__main__":
    unittest.main()
