from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path

from predict_knockout_bracket import _shrink_two_way

ROOT = Path(__file__).resolve().parent.parent


class KnockoutLayerTest(unittest.TestCase):
    def test_knockout_fixture_count(self) -> None:
        with (ROOT / "data" / "knockout_fixtures.csv").open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 16)
        self.assertTrue(all(row["stage"] == "knockout" for row in rows))

    def test_two_way_shrink_keeps_no_draw_output(self) -> None:
        home, away = _shrink_two_way(0.70, 0.20, 0.08, 0.14)
        self.assertLess(abs(home + away - 1.0), 1e-9)
        self.assertGreaterEqual(min(home, away), 0.14)

    def test_knockout_prediction_shape_if_present(self) -> None:
        path = ROOT / "outputs" / "knockout_bracket_prediction.json"
        if not path.exists():
            self.skipTest("knockout prediction has not been generated")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(data["rounds"]), 5)
        self.assertEqual(sum(len(round_["matches"]) for round_ in data["rounds"]), 31)
        self.assertTrue(data["champion"])

    def test_knockout_scenarios_are_generated_if_present(self) -> None:
        path = ROOT / "outputs" / "knockout_bracket_prediction.json"
        if not path.exists():
            self.skipTest("knockout prediction has not been generated")
        data = json.loads(path.read_text(encoding="utf-8"))
        scenarios = data.get("scenarios", [])
        self.assertEqual([item["scenario_id"] for item in scenarios], ["A", "B", "C"])
        for scenario in scenarios:
            self.assertTrue(scenario["champion"])
            self.assertGreater(scenario["estimated_accuracy"], 0.0)
            self.assertEqual(sum(len(round_["matches"]) for round_ in scenario["rounds"]), 31)
            sample = scenario["rounds"][0]["matches"][0]
            self.assertIn("player_impact", sample)
            self.assertIn("team_stat_impact", sample)
            self.assertIn("goal_timing_impact", sample)


if __name__ == "__main__":
    unittest.main()
