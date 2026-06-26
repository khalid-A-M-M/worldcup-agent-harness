from __future__ import annotations

import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date as Date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass
class MatchResult:
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    match_date: str = ""
    match_type: str = "default"


@dataclass
class ScoreProbability:
    home_goals: int
    away_goals: int
    probability: float


@dataclass
class ModelPrediction:
    home_win: float
    draw: float
    away_win: float
    expected_home_goals: float
    expected_away_goals: float
    score_matrix: List[ScoreProbability]


MATCH_TYPE_WEIGHTS: Dict[str, float] = {
    "wc_2026": 1.00,
    "qualifier": 0.65,
    "cup_2022": 0.22,
    "cup_2018": 0.10,
    "friendly": 0.18,
    "default": 0.35,
}

TAU = 0.003


def load_results(path: Path) -> List[MatchResult]:
    return [match for match, _weight in load_results_weighted(path)]


def load_results_weighted(path: Path) -> List[Tuple[MatchResult, float]]:
    weighted: List[Tuple[MatchResult, float]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            match = MatchResult(
                home_team=row["home_team"],
                away_team=row["away_team"],
                home_goals=int(row["home_goals"]),
                away_goals=int(row["away_goals"]),
                match_date=row.get("date", ""),
                match_type=row.get("match_type") or "default",
            )
            weighted.append((match, compute_match_weight(match.match_date, match.match_type)))
    return weighted


def compute_match_weight(match_date: str | Date, match_type: str, today: Date | None = None) -> float:
    today = today or Date.today()
    parsed_date = _parse_match_date(match_date)
    days_ago = max(0, (today - parsed_date).days) if parsed_date else 0
    time_weight = math.exp(-TAU * days_ago)
    type_weight = MATCH_TYPE_WEIGHTS.get(match_type, MATCH_TYPE_WEIGHTS["default"])
    return time_weight * type_weight


def _parse_match_date(value: str | Date) -> Date | None:
    if isinstance(value, Date):
        return value
    if not value:
        return None
    try:
        return Date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _estimate_rho(matches: List[MatchResult]) -> float:
    if len(matches) < 12:
        return -0.08
    low_score = sum(1 for m in matches if m.home_goals <= 1 and m.away_goals <= 1)
    draws_00_11 = sum(1 for m in matches if (m.home_goals, m.away_goals) in {(0, 0), (1, 1)})
    low_ratio = low_score / len(matches)
    draw_low_ratio = draws_00_11 / max(low_score, 1)
    rho = -0.04 - 0.18 * low_ratio + 0.08 * draw_low_ratio
    return max(-0.20, min(0.0, rho))


class DixonColesLiteModel:
    """Poisson goal model with a Dixon-Coles-style low-score adjustment."""

    def __init__(
        self,
        rho: float = -0.08,
        max_goals: int = 8,
        team_priors: Optional[Dict[str, Tuple[float, float]]] = None,
    ):
        self.rho = rho
        self.max_goals = max_goals
        self.team_priors = team_priors or {}
        self.home_advantage = 1.0
        self.attack: Dict[str, float] = {}
        self.defense: Dict[str, float] = {}
        self.global_home_goals = 1.35
        self.global_away_goals = 1.05
        self.effective_matches = 0.0

    def fit(self, results: Iterable[Any]) -> "DixonColesLiteModel":
        weighted_matches = [_coerce_weighted_result(item) for item in results]
        if not weighted_matches:
            raise ValueError("Cannot fit model without historical results.")
        matches = [match for match, _weight in weighted_matches]
        total_weight = max(sum(weight for _match, weight in weighted_matches), 0.001)
        self.effective_matches = total_weight
        self.rho = _estimate_rho(matches)

        teams = sorted({m.home_team for m in matches} | {m.away_team for m in matches})
        goals_for = defaultdict(float)
        goals_against = defaultdict(float)
        games = defaultdict(float)
        home_goals = sum(m.home_goals * weight for m, weight in weighted_matches)
        away_goals = sum(m.away_goals * weight for m, weight in weighted_matches)

        self.global_home_goals = max(home_goals / total_weight, 0.2)
        self.global_away_goals = max(away_goals / total_weight, 0.2)
        league_avg = (self.global_home_goals + self.global_away_goals) / 2
        self.home_advantage = max(self.global_home_goals / self.global_away_goals, 0.75)

        for match, weight in weighted_matches:
            goals_for[match.home_team] += match.home_goals * weight
            goals_against[match.home_team] += match.away_goals * weight
            games[match.home_team] += weight
            goals_for[match.away_team] += match.away_goals * weight
            goals_against[match.away_team] += match.home_goals * weight
            games[match.away_team] += weight

        for team in teams:
            attack_rate = (goals_for[team] + league_avg) / (games[team] + 1)
            defense_rate = (goals_against[team] + league_avg) / (games[team] + 1)
            observed_attack = attack_rate / league_avg
            observed_defense = defense_rate / league_avg
            prior_attack, prior_defense = self.team_priors.get(team, (1.0, 1.0))
            observed_weight = min(games[team] / (games[team] + 3), 0.75)
            prior_weight = 1 - observed_weight
            self.attack[team] = observed_attack * observed_weight + prior_attack * prior_weight
            self.defense[team] = observed_defense * observed_weight + prior_defense * prior_weight
        return self

    def predict(self, home_team: str, away_team: str, neutral_venue: bool = False) -> ModelPrediction:
        home_attack = self.attack.get(home_team, 1.0)
        away_attack = self.attack.get(away_team, 1.0)
        home_defense = self.defense.get(home_team, 1.0)
        away_defense = self.defense.get(away_team, 1.0)

        if neutral_venue:
            neutral_base = (self.global_home_goals + self.global_away_goals) / 2
            expected_home = neutral_base * home_attack * away_defense
            expected_away = neutral_base * away_attack * home_defense
        else:
            expected_home = self.global_home_goals * home_attack * away_defense
            expected_away = self.global_away_goals * away_attack * home_defense
        expected_home = min(max(expected_home, 0.25), 4.5)
        expected_away = min(max(expected_away, 0.25), 4.5)

        matrix: List[ScoreProbability] = []
        total = 0.0
        for hg in range(self.max_goals + 1):
            for ag in range(self.max_goals + 1):
                p = _poisson_pmf(hg, expected_home) * _poisson_pmf(ag, expected_away)
                p *= self._low_score_tau(hg, ag, expected_home, expected_away)
                matrix.append(ScoreProbability(hg, ag, p))
                total += p

        matrix = [
            ScoreProbability(item.home_goals, item.away_goals, item.probability / total)
            for item in matrix
        ]
        home_win = sum(item.probability for item in matrix if item.home_goals > item.away_goals)
        draw = sum(item.probability for item in matrix if item.home_goals == item.away_goals)
        away_win = sum(item.probability for item in matrix if item.home_goals < item.away_goals)

        return ModelPrediction(
            home_win=home_win,
            draw=draw,
            away_win=away_win,
            expected_home_goals=expected_home,
            expected_away_goals=expected_away,
            score_matrix=matrix,
        )

    def _low_score_tau(self, home_goals: int, away_goals: int, home_xg: float, away_xg: float) -> float:
        if home_goals == 0 and away_goals == 0:
            return max(0.01, 1 - home_xg * away_xg * self.rho)
        if home_goals == 0 and away_goals == 1:
            return max(0.01, 1 + home_xg * self.rho)
        if home_goals == 1 and away_goals == 0:
            return max(0.01, 1 + away_xg * self.rho)
        if home_goals == 1 and away_goals == 1:
            return max(0.01, 1 - self.rho)
        return 1.0


def _coerce_weighted_result(item: Any) -> Tuple[MatchResult, float]:
    if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], MatchResult):
        return item[0], max(float(item[1]), 0.001)
    if isinstance(item, MatchResult):
        return item, 1.0
    raise TypeError(f"Unsupported match result item: {type(item)!r}")


def _poisson_pmf(k: int, rate: float) -> float:
    return math.exp(-rate) * rate**k / math.factorial(k)


def normalize_three_way(home: float, draw: float, away: float) -> Tuple[float, float, float]:
    values = [max(home, 0.001), max(draw, 0.001), max(away, 0.001)]
    total = sum(values)
    return values[0] / total, values[1] / total, values[2] / total


def load_team_priors(path: Path) -> Dict[str, Tuple[float, float]]:
    if not path.exists():
        return {}
    priors: Dict[str, Tuple[float, float]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rank = float(row["seed_rank"])
            attack = 1.0 + max(min((55 - rank) / 180, 0.18), -0.14)
            defense = 1.0 - max(min((55 - rank) / 230, 0.14), -0.12)
            priors[row["team"]] = (attack, defense)
    return priors
