from __future__ import annotations

import unittest
from datetime import date

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


if __name__ == "__main__":
    unittest.main()
