from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path

from predict_knockout_bracket import _shrink_two_way
from evolve_after_results import _actual_id_for_match
from forecast_ledger import load_latest_pre_match_knockout_predictions

ROOT = Path(__file__).resolve().parent.parent


class KnockoutLayerTest(unittest.TestCase):
    def test_knockout_fixture_count(self) -> None:
        with (ROOT / "data" / "knockout_fixtures.csv").open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 16)
        self.assertTrue(all(row["stage"] == "knockout" for row in rows))

    def test_knockout_actual_id_alias_maps_wc_to_ko(self) -> None:
        actuals = {"WC-073": {"home_goals": 0, "away_goals": 1}}
        self.assertEqual(_actual_id_for_match("KO-073", actuals), "WC-073")


    def test_knockout_pre_match_snapshot_uses_generated_time(self) -> None:
        from unittest.mock import patch

        fixtures = {
            "KO-073": {
                "match_id": "KO-073",
                "kickoff_utc": "2026-06-28T17:00:00Z",
            }
        }
        fake_index = {
            "entries": [
                {
                    "match_id": "KO-073",
                    "winner": "Canada",
                    "created_at_utc": "2026-06-28T10:00:00Z",
                    "archived_at_utc": "20260629T091541Z",
                },
                {
                    "match_id": "KO-073",
                    "winner": "South Africa",
                    "created_at_utc": "2026-06-28T18:00:00Z",
                    "archived_at_utc": "20260629T091802Z",
                },
            ]
        }
        with patch("forecast_ledger._load_knockout_index", return_value=fake_index):
            latest = load_latest_pre_match_knockout_predictions(fixtures)
        self.assertEqual(latest["KO-073"]["winner"], "Canada")

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

    def test_knockout_prediction_contains_time_series_layer_if_present(self) -> None:
        path = ROOT / "outputs" / "knockout_bracket_prediction.json"
        if not path.exists():
            self.skipTest("knockout prediction has not been generated")
        data = json.loads(path.read_text(encoding="utf-8"))
        time_series = data.get("time_series_forecast", {})
        self.assertEqual(time_series.get("agent"), "time_series_agent")
        self.assertIn("teams", time_series)
        sample = data["rounds"][0]["matches"][0]
        self.assertIn("time_series_impact", sample)
        self.assertIn("time_series_profile", sample)

    def test_knockout_prediction_contains_equation_learning_if_present(self) -> None:
        path = ROOT / "outputs" / "knockout_bracket_prediction.json"
        if not path.exists():
            self.skipTest("knockout prediction has not been generated")
        data = json.loads(path.read_text(encoding="utf-8"))
        equation = data.get("equation_learning", {})
        self.assertIn("coefficients", equation)
        self.assertIn("formula", equation)
        self.assertIn("favorite_temperature", equation["coefficients"])
        self.assertIn("two_way_logit", equation["formula"])
        self.assertIn("equation_version", data["rounds"][-1]["matches"][0])


if __name__ == "__main__":
    unittest.main()
