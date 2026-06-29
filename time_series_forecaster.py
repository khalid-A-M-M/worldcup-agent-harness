from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"
TARGET = DATA / "time_series_forecast.json"


def main() -> None:
    series = _build_team_series()
    advanced = _advanced_stat_trends()
    teams = sorted(set(series) | set(advanced))
    profiles = {team: _team_profile(team, series.get(team, []), advanced.get(team, {})) for team in teams}
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "agent": "time_series_agent",
        "inspired_by": {
            "project": "google-research/timesfm",
            "note": "Stable local fallback: EWMA/quantile time-series layer for GitHub Actions. If TimesFM is installed later, this file can become the adapter input/output contract without changing the dashboard.",
        },
        "method": {
            "series": "Per-team chronological goal-difference and points signal from completed World Cup matches, enriched with advanced match stats when available.",
            "forecast": "Exponentially weighted momentum with volatility penalty and confidence bands. This keeps the free GitHub workflow deterministic while borrowing the TimesFM idea: recent sequence shape matters, not only static weights.",
            "equation": "time_series_edge = 0.018 * momentum_index + 0.010 * stat_trend_index - 0.006 * volatility_index",
        },
        "teams": profiles,
    }
    TARGET.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated time-series profiles for {len(profiles)} teams at {TARGET}")


def _build_team_series() -> dict[str, list[dict[str, Any]]]:
    rows = []
    historical = DATA / "historical_results.csv"
    if historical.exists():
        rows.extend(_read_csv(historical))
    actuals = DATA / "actual_results.csv"
    fixtures = _fixtures_by_id()
    if actuals.exists():
        for row in _read_csv(actuals):
            fixture = fixtures.get(row.get("match_id", ""), {})
            if not fixture:
                continue
            rows.append({
                "date": fixture.get("kickoff_utc", "")[:10],
                "home_team": fixture.get("home_team", ""),
                "away_team": fixture.get("away_team", ""),
                "home_goals": row.get("home_goals", ""),
                "away_goals": row.get("away_goals", ""),
                "match_type": "wc_2026_actual",
            })
    rows = [row for row in rows if row.get("home_team") and row.get("away_team")]
    rows.sort(key=lambda row: row.get("date", ""))
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        home = row["home_team"]
        away = row["away_team"]
        hg = _safe_float(row.get("home_goals"), 0.0)
        ag = _safe_float(row.get("away_goals"), 0.0)
        if hg > ag:
            hp, ap = 3.0, 0.0
        elif ag > hg:
            hp, ap = 0.0, 3.0
        else:
            hp, ap = 1.0, 1.0
        out.setdefault(home, []).append({"date": row.get("date", ""), "points": hp, "goal_diff": hg - ag, "goals_for": hg, "goals_against": ag})
        out.setdefault(away, []).append({"date": row.get("date", ""), "points": ap, "goal_diff": ag - hg, "goals_for": ag, "goals_against": hg})
    return out


def _advanced_stat_trends() -> dict[str, dict[str, float]]:
    path = DATA / "match_advanced_stats.csv"
    if not path.exists():
        return {}
    numeric = ["shots_on_target", "xg", "dominance_index", "attacking_pressure_index", "match_momentum", "momentum_last_15"]
    grouped: dict[str, list[dict[str, float]]] = {}
    for row in _read_csv(path):
        team = row.get("team", "")
        if not team:
            continue
        item = {field: _safe_float(row.get(field), 0.0) for field in numeric}
        grouped.setdefault(team, []).append(item)
    out: dict[str, dict[str, float]] = {}
    for team, items in grouped.items():
        if not items:
            continue
        latest = _ewma([_stat_strength(row) for row in items], alpha=0.62)
        early = sum(_stat_strength(row) for row in items[: max(1, len(items)//2)]) / max(1, len(items[: max(1, len(items)//2)]))
        out[team] = {
            "stat_trend_index": max(-10.0, min(10.0, (latest - early) / 4.0)),
            "latest_stat_strength": latest,
            "sample_size": float(len(items)),
        }
    return out


def _team_profile(team: str, matches: list[dict[str, Any]], stats: dict[str, float]) -> dict[str, Any]:
    points = [float(row.get("points", 0.0)) for row in matches]
    gd = [float(row.get("goal_diff", 0.0)) for row in matches]
    gf = [float(row.get("goals_for", 0.0)) for row in matches]
    ga = [float(row.get("goals_against", 0.0)) for row in matches]
    sample = len(matches)
    point_momentum = _ewma(points, alpha=0.58) if points else 1.0
    gd_momentum = _ewma(gd, alpha=0.58) if gd else 0.0
    scoring_form = _ewma(gf, alpha=0.58) if gf else 1.0
    defensive_form = _ewma(ga, alpha=0.58) if ga else 1.0
    volatility = _std(gd[-6:]) if len(gd) >= 2 else 0.8
    stat_trend = float(stats.get("stat_trend_index", 0.0))
    momentum_index = max(-10.0, min(10.0, (point_momentum - 1.25) * 2.4 + gd_momentum * 1.7 + (scoring_form - defensive_form) * 0.8))
    volatility_index = max(0.0, min(10.0, volatility * 2.2))
    edge = 0.018 * momentum_index + 0.010 * stat_trend - 0.006 * volatility_index
    confidence = max(0.20, min(0.88, 0.34 + sample * 0.055 + float(stats.get("sample_size", 0.0)) * 0.025 - volatility_index * 0.025))
    return {
        "sample_size": sample,
        "momentum_index": round(momentum_index, 4),
        "stat_trend_index": round(stat_trend, 4),
        "volatility_index": round(volatility_index, 4),
        "time_series_edge": round(max(-0.14, min(0.14, edge)), 4),
        "confidence": round(confidence, 4),
        "point_momentum": round(point_momentum, 4),
        "goal_difference_momentum": round(gd_momentum, 4),
        "scoring_form": round(scoring_form, 4),
        "defensive_form": round(defensive_form, 4),
        "last_dates": [row.get("date", "") for row in matches[-5:]],
    }


def _stat_strength(row: dict[str, float]) -> float:
    xg = row.get("xg", 0.0)
    xg_component = xg * 8.0 if xg else 0.0
    return (
        row.get("shots_on_target", 0.0) * 2.6
        + row.get("dominance_index", 50.0) * 0.20
        + row.get("attacking_pressure_index", 45.0) * 0.16
        + row.get("match_momentum", 0.0) * 0.08
        + row.get("momentum_last_15", 0.0) * 0.10
        + xg_component
    )


def _fixtures_by_id() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for path in [DATA / "all_group_fixtures.csv", DATA / "fixtures.csv", DATA / "knockout_fixtures.csv"]:
        if path.exists():
            for row in _read_csv(path):
                out[row.get("match_id", "")] = row
    return out


def _ewma(values: list[float], alpha: float = 0.55) -> float:
    if not values:
        return 0.0
    current = values[0]
    for value in values[1:]:
        current = alpha * value + (1 - alpha) * current
    return current


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    main()
