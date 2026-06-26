from __future__ import annotations

import csv
import unittest
from datetime import date
from pathlib import Path

from football_harness.agents import _coerce_probability_map, _economic_probabilities_from_scores, _kliment_weight
from football_harness.model import (
    DixonColesLiteModel,
    MatchResult,
    _estimate_rho,
    compute_match_weight,
    normalize_three_way,
)

MATCHES = [
    MatchResult("France", "Morocco", 2, 1, "2026-06-01", "wc_2026"),
    MatchResult("Brazil", "Canada", 3, 0, "2026-06-01", "wc_2026"),
    MatchResult("Spain", "Germany", 1, 1, "2026-06-02", "wc_2026"),
    MatchResult("Argentina", "USA", 2, 0, "2026-06-02", "wc_2026"),
] * 4


class ModelBasicsTest(unittest.TestCase):
    def test_normalize_three_way(self) -> None:
        values = normalize_three_way(2.0, 1.0, 1.0)
        self.assertLess(abs(sum(values) - 1.0), 1e-9)
        self.assertLess(abs(values[0] - 0.5), 1e-6)

    def test_compute_match_weight_type_and_time(self) -> None:
        today = date(2026, 6, 26)
        self.assertEqual(compute_match_weight(today, "wc_2026", today), 1.0)
        self.assertGreater(
            compute_match_weight(date(2026, 6, 1), "wc_2026", today),
            compute_match_weight(date(2026, 6, 1), "friendly", today),
        )
        self.assertGreater(
            compute_match_weight(date(2026, 6, 20), "qualifier", today),
            compute_match_weight(date(2024, 6, 20), "qualifier", today),
        )

    def test_dynamic_rho_bounds(self) -> None:
        rho = _estimate_rho(MATCHES)
        self.assertGreaterEqual(rho, -0.20)
        self.assertLessEqual(rho, 0.0)

    def test_weighted_fit_predicts_valid_probabilities(self) -> None:
        weighted = [(match, 0.8) for match in MATCHES]
        model = DixonColesLiteModel().fit(weighted)
        pred = model.predict("France", "Canada", neutral_venue=True)
        self.assertLess(abs(pred.home_win + pred.draw + pred.away_win - 1.0), 1e-6)
        self.assertGreater(model.effective_matches, 0)
        self.assertGreaterEqual(model.rho, -0.20)
        self.assertLessEqual(model.rho, 0.0)


class DataIntegrityTest(unittest.TestCase):
    def test_historical_results_have_match_type(self) -> None:
        path = Path(__file__).resolve().parent.parent / "data" / "historical_results.csv"
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            self.assertIn("match_type", reader.fieldnames or [])
            rows = list(reader)
        self.assertTrue(rows)
        self.assertTrue(all(row.get("match_type") for row in rows))



class AgentBlendTest(unittest.TestCase):
    def test_kliment_weight_decays_with_tournament_sample(self) -> None:
        self.assertAlmostEqual(_kliment_weight(0), 0.70)
        self.assertGreater(_kliment_weight(3), _kliment_weight(6))
        self.assertAlmostEqual(_kliment_weight(6), 0.16)
        self.assertEqual(_kliment_weight(20), 0.15)

    def test_probability_map_coerces_string_values(self) -> None:
        values = _coerce_probability_map({"home_win": "0.50", "draw": "0.25", "away_win": "0.25"})
        self.assertLess(abs(sum(values.values()) - 1.0), 1e-9)
        self.assertGreater(values["home_win"], values["away_win"])

    def test_economic_probabilities_are_numeric(self) -> None:
        values = _economic_probabilities_from_scores(70.0, 55.0)
        self.assertTrue(all(isinstance(value, float) for value in values.values()))
        self.assertLess(abs(sum(values.values()) - 1.0), 1e-9)
        self.assertGreater(values["home_win"], values["away_win"])


if __name__ == "__main__":
    unittest.main()
