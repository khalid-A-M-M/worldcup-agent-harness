from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from football_harness.agents import (
    ButterflyFactorsAgent,
    CriticAuditorAgent,
    DataCollectionAgent,
    EconomicWorldAgent,
    SpecialistAnalysisAgent,
    SynthesizerAgent,
    TeamIntelligenceAgent,
)
from football_harness.core import AgentHarness, MatchContext
from run_pipeline import _json_safe

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"

ROUND_NAMES = ["Round of 32", "Round of 16", "Quarterfinals", "Semifinals", "Final"]

SCENARIOS = [
    {
        "id": "A",
        "arabic_name": "المسار أ: العقل البارد",
        "description": "يعطي وزناً أعلى للمرشح الأقوى، يقلل الفوضى، ولا يقلب مباراة إلا عند وجود هامش واضح.",
        "favorite_shrink_delta": -0.018,
        "upset_floor_delta": -0.025,
        "penalty_multiplier": 0.88,
        "player_weight": 0.55,
        "team_stats_weight": 0.70,
        "goal_timing_weight": 0.55,
        "time_series_weight": 0.65,
        "chaos_weight": 0.35,
    },
    {
        "id": "B",
        "arabic_name": "المسار ب: النموذج المتوازن",
        "description": "النسخة الرسمية الحالية: تمزج Agent Harness مع النموذج الاقتصادي وإحصاءات البطولة والتعلم من الأخطاء واتجاهات السلاسل الزمنية.",
        "favorite_shrink_delta": 0.0,
        "upset_floor_delta": 0.0,
        "penalty_multiplier": 1.0,
        "player_weight": 0.75,
        "team_stats_weight": 0.85,
        "goal_timing_weight": 0.75,
        "time_series_weight": 0.90,
        "chaos_weight": 0.60,
    },
    {
        "id": "C",
        "arabic_name": "المسار ج: جنون الاحتمالات",
        "description": "يعظم أثر الفراشة: ركلات الترجيح، اللاعب الحاسم، الزخم المتأخر، اتجاه السلسلة الزمنية، والمفاجآت القريبة.",
        "favorite_shrink_delta": 0.035,
        "upset_floor_delta": 0.045,
        "penalty_multiplier": 1.24,
        "player_weight": 1.05,
        "team_stats_weight": 1.0,
        "goal_timing_weight": 1.15,
        "time_series_weight": 1.25,
        "chaos_weight": 1.0,
    },
]


def main() -> None:
    learning = _load_learning()
    equation = _load_equation_learning()
    time_series = _load_time_series_forecast()
    fixtures = _read_csv(DATA / "knockout_fixtures.csv")
    actual_winners = _load_knockout_actual_winners()
    scenarios = [_project_scenario(fixtures, learning, equation, time_series, scenario, actual_winners) for scenario in SCENARIOS]
    official = next(item for item in scenarios if item["scenario_id"] == "B")
    rounds = official["rounds"]
    champion = official["champion"]
    scenario_summaries = [_scenario_summary(item) for item in scenarios]
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "method": "Agent Harness knockout simulator: three scenario paths + group-error learning + Dixon/economic blend + advanced stats + player-impact proxies + goal-timing layer + TimesFM-inspired time-series agent + penalty shootout model. No draw is allowed in knockout outputs.",
        "learning_summary": learning,
        "equation_learning": equation,
        "time_series_forecast": time_series,
        "champion": champion,
        "rounds": rounds,
        "scenarios": scenario_summaries,
        "sources": [
            "Local audited group-stage forecast ledger and accuracy_report.json",
            "data/match_advanced_stats.csv from ESPN-derived open match statistics where available",
            "data/player_performance_indicators.csv open-source-ready player-impact layer",
            "data/goal_timing_events.csv optional goal-minute layer; falls back to late-momentum indicators when minutes are not available",
            "data/equation_learning.json learned equation parameters after every completed-match audit",
            "data/time_series_forecast.json TimesFM-inspired sequence trend layer for team momentum and volatility",
            "google-research/timesfm design idea: sequence-first forecasting; implemented here as a stable free fallback for GitHub Actions",
            "Published Round-of-32 pairings from FIFA/beIN/Yallakora text supplied with this run",
        ],
    }
    OUTPUTS.mkdir(exist_ok=True)
    (OUTPUTS / "knockout_bracket_prediction.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Projected 3 knockout paths through final. Official champion={champion}")


def _project_scenario(fixtures: list[dict[str, str]], learning: dict[str, Any], equation: dict[str, Any], time_series: dict[str, Any], scenario: dict[str, Any], actual_winners: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    actual_winners = actual_winners or {}
    rounds: list[dict[str, Any]] = []
    current = [_fixture_to_match(row) for row in fixtures]
    round_index = 0
    next_match_number = 89

    while current:
        round_name = ROUND_NAMES[round_index]
        matches = []
        winners = []
        for fixture in current:
            prediction = _predict_knockout_match(fixture, round_name, learning, equation, time_series, scenario)
            prediction = _apply_actual_winner_lock(prediction, actual_winners.get(fixture.get("match_id", "")) or actual_winners.get(fixture.get("source_actual_match_id", "")))
            matches.append(prediction)
            winners.append(prediction["winner"])
        rounds.append({"round": round_name, "matches": matches})
        if len(winners) == 1:
            break
        current = []
        for i in range(0, len(winners), 2):
            current.append(
                {
                    "match_id": f"KO-{next_match_number:03d}",
                    "home_team": winners[i],
                    "away_team": winners[i + 1],
                    "kickoff_utc": (datetime(2026, 7, 6, 19, tzinfo=timezone.utc) + timedelta(days=round_index * 3 + i // 2)).isoformat().replace("+00:00", "Z"),
                    "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "round": ROUND_NAMES[round_index + 1],
                    "stage": "knockout",
                    "bracket_slot": f"{ROUND_NAMES[round_index + 1]}-{i//2 + 1}",
                    "source_note": f"Projected by Agent Harness knockout simulator scenario {scenario['id']}",
                }
            )
            next_match_number += 1
        round_index += 1

    champion = rounds[-1]["matches"][0]["winner"] if rounds and rounds[-1]["matches"] else "TBD"
    reliability = _scenario_reliability(rounds, learning, scenario)
    return {
        "scenario_id": scenario["id"],
        "arabic_name": scenario["arabic_name"],
        "description": scenario["description"],
        "estimated_accuracy": reliability["estimated_accuracy"],
        "confidence_grade": reliability["confidence_grade"],
        "high_risk_matches": reliability["high_risk_matches"],
        "average_confidence_margin": reliability["average_confidence_margin"],
        "average_penalty_probability": reliability["average_penalty_probability"],
        "champion": champion,
        "final": rounds[-1]["matches"][0] if rounds and rounds[-1]["matches"] else None,
        "rounds": rounds,
    }


def _scenario_summary(scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenario_id": scenario["scenario_id"],
        "arabic_name": scenario["arabic_name"],
        "description": scenario["description"],
        "estimated_accuracy": scenario["estimated_accuracy"],
        "confidence_grade": scenario["confidence_grade"],
        "high_risk_matches": scenario["high_risk_matches"],
        "average_confidence_margin": scenario["average_confidence_margin"],
        "average_penalty_probability": scenario["average_penalty_probability"],
        "champion": scenario["champion"],
        "final": _compact_match_for_scenario(scenario["final"]) if scenario.get("final") else None,
        "rounds": [
            {"round": round_item["round"], "matches": [_compact_match_for_scenario(match) for match in round_item["matches"]]}
            for round_item in scenario["rounds"]
        ],
    }


def _compact_match_for_scenario(match: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "match_id",
        "round",
        "home_team",
        "away_team",
        "winner",
        "winner_method",
        "home_advance_probability",
        "away_advance_probability",
        "penalty_shootout",
        "upset_risk",
        "confidence_margin",
        "player_impact",
        "team_stat_impact",
        "goal_timing_impact",
        "time_series_impact",
        "scenario",
        "kickoff_utc",
        "generated_at_utc",
        "actual_result_locked",
        "predicted_winner_before_actual",
    ]
    return {key: match.get(key) for key in keys if key in match}


def _load_equation_learning() -> dict[str, Any]:
    path = DATA / "equation_learning.json"
    if not path.exists():
        import subprocess, sys
        subprocess.run([sys.executable, str(ROOT / "learn_equation_parameters.py")], cwd=ROOT, check=True)
    return json.loads(path.read_text(encoding="utf-8"))

def _load_time_series_forecast() -> dict[str, Any]:
    path = DATA / "time_series_forecast.json"
    if not path.exists():
        import subprocess, sys
        subprocess.run([sys.executable, str(ROOT / "time_series_forecaster.py")], cwd=ROOT, check=True)
    return json.loads(path.read_text(encoding="utf-8"))


def _load_learning() -> dict[str, Any]:
    path = OUTPUTS / "group_learning_report.json"
    if not path.exists():
        import subprocess, sys
        subprocess.run([sys.executable, str(ROOT / "learn_from_group_errors.py")], cwd=ROOT, check=True)
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_knockout_actual_winners() -> dict[str, dict[str, str]]:
    path = DATA / "knockout_actual_winners.csv"
    if not path.exists():
        return {}
    winners: dict[str, dict[str, str]] = {}
    for row in _read_csv(path):
        if row.get("match_id"):
            winners[row["match_id"]] = row
        if row.get("source_actual_match_id"):
            winners[row["source_actual_match_id"]] = row
    return winners


def _apply_actual_winner_lock(prediction: dict[str, Any], winner_row: dict[str, str] | None) -> dict[str, Any]:
    if not winner_row or not winner_row.get("winner"):
        return prediction
    actual_winner = winner_row["winner"]
    if actual_winner not in {prediction.get("home_team"), prediction.get("away_team")}:
        return prediction
    original_winner = prediction.get("winner")
    prediction = dict(prediction)
    prediction["winner"] = actual_winner
    prediction["winner_method"] = winner_row.get("method") or prediction.get("winner_method")
    prediction["actual_result_locked"] = True
    prediction["predicted_winner_before_actual"] = original_winner
    prediction["key_factors"] = list(prediction.get("key_factors", [])) + [
        f"Actual completed result lock: {actual_winner} advanced via {prediction['winner_method']}."
    ]
    return prediction


def _fixture_to_match(row: dict[str, str]) -> dict[str, str]:
    return dict(row)


def _harness() -> AgentHarness:
    return AgentHarness(
        agents=[
            DataCollectionAgent(
                DATA / "historical_results.csv",
                DATA / "butterfly_events.csv",
                DATA / "team_seed_ranks.csv",
                DATA / "match_advanced_stats.csv",
                DATA / "model_calibration.json",
                DATA / "economic_world_indicators.csv",
            ),
            SpecialistAnalysisAgent(),
            TeamIntelligenceAgent(),
            ButterflyFactorsAgent(),
            EconomicWorldAgent(),
            CriticAuditorAgent(),
            SynthesizerAgent(),
        ]
    )


def _predict_knockout_match(fixture: dict[str, str], round_name: str, learning: dict[str, Any], equation: dict[str, Any], time_series: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    state = _harness().run_match(
        MatchContext(
            match_id=fixture["match_id"],
            home_team=fixture["home_team"],
            away_team=fixture["away_team"],
            kickoff_utc=_parse_dt(fixture["kickoff_utc"]),
            generated_at_utc=_parse_dt(fixture["generated_at_utc"]),
            metadata={
                "neutral_venue": True,
                "group": "",
                "ground": fixture.get("ground", ""),
                "round": round_name,
                "stage": "knockout",
            },
        )
    )
    final = state.get_payload("synthesizer")
    home, draw, away = float(final["home_win"]), float(final["draw"]), float(final["away_win"])
    adjustments = learning.get("learned_knockout_adjustments", {})
    coefficients = equation.get("coefficients", {})
    shrink = max(0.0, float(adjustments.get("favorite_shrink", 0.08)) + float(coefficients.get("upset_curve", 0.14)) * 0.18 + float(scenario.get("favorite_shrink_delta", 0.0)))
    upset_floor = max(0.05, min(0.34, float(adjustments.get("upset_floor", 0.14)) + float(coefficients.get("upset_curve", 0.14)) * 0.20 + float(scenario.get("upset_floor_delta", 0.0))))
    penalty_sensitivity = float(adjustments.get("penalty_sensitivity", 1.0)) * float(coefficients.get("penalty_logit_gain", 1.0)) * float(scenario.get("penalty_multiplier", 1.0))

    influence = _scenario_influence(fixture["home_team"], fixture["away_team"], scenario, coefficients, time_series)
    home += influence["home_probability_delta"]
    away += influence["away_probability_delta"]
    home, away = _apply_equation_two_way(home, away, coefficients)
    home, away = _shrink_two_way(home, away, shrink, upset_floor)
    draw = max(0.05, min(0.48, (draw * float(coefficients.get("draw_temperature", 1.0)) + float(coefficients.get("draw_intercept", 0.0)) + influence["draw_delta"]) * penalty_sensitivity))
    penalty_home = _penalty_edge(fixture["home_team"], fixture["away_team"], scenario, coefficients)
    home_direct = home
    away_direct = away
    home_penalty = draw * penalty_home
    away_penalty = draw * (1 - penalty_home)
    home_advance = home_direct + home_penalty
    away_advance = away_direct + away_penalty
    total = home_advance + away_advance
    home_advance, away_advance = home_advance / total, away_advance / total
    winner = fixture["home_team"] if home_advance >= away_advance else fixture["away_team"]
    winner_direct = home_direct if winner == fixture["home_team"] else away_direct
    winner_penalty = home_penalty if winner == fixture["home_team"] else away_penalty
    method = "penalties" if winner_penalty / max(winner_direct + winner_penalty, 1e-9) >= 0.34 else "direct_or_extra_time"
    confidence = abs(home_advance - away_advance)
    risk = "high" if confidence < 0.10 else "medium" if confidence < 0.22 else "low"

    return {
        "match_id": fixture["match_id"],
        "round": round_name,
        "kickoff_utc": fixture.get("kickoff_utc"),
        "generated_at_utc": fixture.get("generated_at_utc"),
        "home_team": fixture["home_team"],
        "away_team": fixture["away_team"],
        "winner": winner,
        "winner_method": method,
        "home_advance_probability": home_advance,
        "away_advance_probability": away_advance,
        "regulation_or_extra_time": {"home": home_direct, "away": away_direct},
        "penalty_shootout": {"probability": draw, "home_win_if_shootout": penalty_home, "away_win_if_shootout": 1 - penalty_home},
        "upset_risk": risk,
        "confidence_margin": confidence,
        "baseline_three_way": {"home_win": final["home_win"], "draw": final["draw"], "away_win": final["away_win"]},
        "key_factors": (final.get("key_factors", [])[:6] + influence["key_factors"]),
        "scenario": {"id": scenario["id"], "arabic_name": scenario["arabic_name"]},
        "player_impact": influence["player_impact"],
        "team_stat_impact": influence["team_stat_impact"],
        "goal_timing_impact": influence["goal_timing_impact"],
        "time_series_impact": influence["time_series_impact"],
        "time_series_profile": influence["time_series_profile"],
        "model_diagnostics": final.get("model_diagnostics", {}),
        "blend_weights": final.get("blend_weights", {}),
        "equation_version": equation.get("equation_version"),
        "equation_coefficients": coefficients,
        "audit_log": state.audit_log,
        "agents": _compact_agents(state),
    }


def _compact_agents(state) -> dict[str, Any]:
    compact = {}
    for name, result in state.results.items():
        payload = result.payload
        keep: dict[str, Any] = {}
        if name == "economic_world":
            keep = {
                "home_score": payload.get("home_score"),
                "away_score": payload.get("away_score"),
                "adjusted_probabilities": payload.get("adjusted_probabilities"),
            }
        elif name == "team_intelligence":
            keep = {
                "probability_adjustment": payload.get("probability_adjustment"),
                "home_profile": payload.get("home_profile"),
                "away_profile": payload.get("away_profile"),
            }
        elif name == "specialist_analysis":
            keep = {
                "baseline_probabilities": payload.get("baseline_probabilities"),
                "expected_goals": payload.get("expected_goals"),
                "model_diagnostics": payload.get("model_diagnostics"),
            }
        elif name == "critic_auditor":
            keep = {
                "favorite": payload.get("favorite"),
                "objections": payload.get("objections"),
                "confidence_penalty": payload.get("confidence_penalty"),
            }
        elif name == "butterfly_factors":
            keep = payload
        elif name == "synthesizer":
            keep = {
                "home_win": payload.get("home_win"),
                "draw": payload.get("draw"),
                "away_win": payload.get("away_win"),
                "recommended_label": payload.get("recommended_label"),
                "explanation": payload.get("explanation"),
            }
        compact[name] = {
            "status": result.status,
            "summary": result.summary,
            "payload": _json_safe(keep),
            "warnings": result.warnings,
        }
    return compact


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)



def _apply_equation_two_way(home: float, away: float, coefficients: dict[str, Any]) -> tuple[float, float]:
    total = max(home + away, 1e-9)
    h = home / total
    a = away / total
    temperature = float(coefficients.get("favorite_temperature", 1.0))
    bias = float(coefficients.get("home_bias_delta", 0.0))
    logit = math.log(max(h, 1e-9) / max(a, 1e-9))
    adjusted = logit * temperature + bias
    h2 = 1 / (1 + math.exp(-adjusted))
    return h2, 1 - h2

def _shrink_two_way(home: float, away: float, shrink: float, floor: float) -> tuple[float, float]:
    total = max(home + away, 1e-9)
    h = home / total
    a = away / total
    if h >= a:
        h = max(floor, h - shrink)
        a = 1 - h
    else:
        a = max(floor, a - shrink)
        h = 1 - a
    return h, a


def _team_stats() -> dict[str, dict[str, float]]:
    rows = _read_csv(DATA / "match_advanced_stats.csv") if (DATA / "match_advanced_stats.csv").exists() else []
    grouped: dict[str, dict[str, float]] = {}
    counts: dict[str, int] = {}
    fields = ["saves", "shots_on_target", "attacking_pressure_index", "dominance_index", "pass_pct", "yellow_cards", "red_cards"]
    for row in rows:
        team = row.get("team", "")
        if not team:
            continue
        grouped.setdefault(team, {field: 0.0 for field in fields})
        counts[team] = counts.get(team, 0) + 1
        for field in fields:
            try:
                grouped[team][field] += float(row.get(field) or 0)
            except ValueError:
                pass
    for team, values in grouped.items():
        n = max(counts.get(team, 1), 1)
        for field in fields:
            values[field] /= n
    return grouped


def _seed_ranks() -> dict[str, float]:
    path = DATA / "team_seed_ranks.csv"
    rows = _read_csv(path) if path.exists() else []
    return {row["team"]: float(row.get("seed_rank") or 50) for row in rows}


def _penalty_edge(home: str, away: str, scenario: dict[str, Any] | None = None, coefficients: dict[str, Any] | None = None) -> float:
    stats = _team_stats()
    ranks = _seed_ranks()
    scenario = scenario or {}
    coefficients = coefficients or {}
    coefficients = coefficients or {}
    players = _player_indicators()
    h, a = stats.get(home, {}), stats.get(away, {})
    hp, ap = players.get(home, {}), players.get(away, {})
    rank_edge = (ranks.get(away, 48) - ranks.get(home, 48)) / 120.0
    keeper_edge = (h.get("saves", 1.5) - a.get("saves", 1.5)) * 0.025
    shot_edge = (h.get("shots_on_target", 3.0) - a.get("shots_on_target", 3.0)) * 0.012
    pressure_edge = (h.get("attacking_pressure_index", 45.0) - a.get("attacking_pressure_index", 45.0)) * 0.002
    discipline_edge = ((a.get("yellow_cards", 1.0) + 2 * a.get("red_cards", 0.0)) - (h.get("yellow_cards", 1.0) + 2 * h.get("red_cards", 0.0))) * 0.012
    player_weight = float(scenario.get("player_weight", 0.75)) * float(coefficients.get("player_signal_gain", 1.0))
    player_keeper_edge = (hp.get("goalkeeper_penalty_index", 50.0) - ap.get("goalkeeper_penalty_index", 50.0)) * 0.0012 * player_weight
    taker_edge = (hp.get("penalty_taker_index", 50.0) - ap.get("penalty_taker_index", 50.0)) * 0.0010 * player_weight
    return max(0.33, min(0.67, 0.50 + rank_edge + keeper_edge + shot_edge + pressure_edge + discipline_edge + player_keeper_edge + taker_edge))


def _player_indicators() -> dict[str, dict[str, float]]:
    path = DATA / "player_performance_indicators.csv"
    if not path.exists():
        return {}
    rows = _read_csv(path)
    numeric_fields = [
        "attacking_star_index",
        "goalkeeper_penalty_index",
        "penalty_taker_index",
        "defensive_leader_index",
        "bench_depth_index",
        "availability_index",
    ]
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        team = row.get("team", "")
        if not team:
            continue
        out[team] = {}
        for field in numeric_fields:
            try:
                out[team][field] = float(row.get(field) or 50)
            except ValueError:
                out[team][field] = 50.0
    return out


def _goal_timing_profile() -> dict[str, dict[str, float]]:
    stats = _team_stats()
    timing: dict[str, dict[str, float]] = {}
    path = DATA / "goal_timing_events.csv"
    if path.exists():
        for row in _read_csv(path):
            team = row.get("team", "")
            if not team:
                continue
            minute = _safe_float(row.get("minute"), 45.0)
            timing.setdefault(team, {"early_goals": 0.0, "late_goals": 0.0, "comeback_goals": 0.0})
            if minute <= 20:
                timing[team]["early_goals"] += 1.0
            if minute >= 70:
                timing[team]["late_goals"] += 1.0
            if row.get("state", "").lower() in {"equalizer", "winner", "comeback"}:
                timing[team]["comeback_goals"] += 1.0
    for team, values in stats.items():
        timing.setdefault(team, {"early_goals": 0.0, "late_goals": 0.0, "comeback_goals": 0.0})
        timing[team]["late_momentum_proxy"] = values.get("momentum_last_15", 0.0) or values.get("attacking_pressure_index", 45.0)
    return timing


def _scenario_influence(home: str, away: str, scenario: dict[str, Any], coefficients: dict[str, Any] | None = None, time_series: dict[str, Any] | None = None) -> dict[str, Any]:
    players = _player_indicators()
    stats = _team_stats()
    timing = _goal_timing_profile()
    hp, ap = players.get(home, {}), players.get(away, {})
    hs, away_stats = stats.get(home, {}), stats.get(away, {})
    ht, at = timing.get(home, {}), timing.get(away, {})
    ts = _time_series_edge(home, away, scenario, time_series or {})

    player_edge = (
        (hp.get("attacking_star_index", 50) - ap.get("attacking_star_index", 50)) * 0.0017
        + (hp.get("availability_index", 50) - ap.get("availability_index", 50)) * 0.0012
        + (hp.get("bench_depth_index", 50) - ap.get("bench_depth_index", 50)) * 0.0010
        + (hp.get("defensive_leader_index", 50) - ap.get("defensive_leader_index", 50)) * 0.0008
    ) * float(scenario.get("player_weight", 0.75)) * float(coefficients.get("player_signal_gain", 1.0))
    team_edge = (
        (hs.get("dominance_index", 50) - away_stats.get("dominance_index", 50)) * 0.0009
        + (hs.get("attacking_pressure_index", 45) - away_stats.get("attacking_pressure_index", 45)) * 0.0009
        + (hs.get("shots_on_target", 3) - away_stats.get("shots_on_target", 3)) * 0.006
        + (hs.get("pass_pct", 0.82) - away_stats.get("pass_pct", 0.82)) * 0.08
    ) * float(scenario.get("team_stats_weight", 0.85)) * float(coefficients.get("stat_signal_gain", 1.0))
    timing_edge = (
        (ht.get("late_goals", 0) - at.get("late_goals", 0)) * 0.010
        + (ht.get("comeback_goals", 0) - at.get("comeback_goals", 0)) * 0.012
        + (ht.get("late_momentum_proxy", 45) - at.get("late_momentum_proxy", 45)) * 0.0006
    ) * float(scenario.get("goal_timing_weight", 0.75)) * float(coefficients.get("timing_signal_gain", 1.0))
    time_series_edge = ts["edge"]
    total_edge = max(-0.18, min(0.18, player_edge + team_edge + timing_edge + time_series_edge + float(coefficients.get("home_bias_delta", 0.0))))
    draw_delta = abs(total_edge) * -0.10 + float(scenario.get("chaos_weight", 0.6)) * 0.015
    return {
        "home_probability_delta": total_edge,
        "away_probability_delta": -total_edge,
        "draw_delta": draw_delta,
        "player_impact": round(player_edge, 4),
        "team_stat_impact": round(team_edge, 4),
        "goal_timing_impact": round(timing_edge, 4),
        "time_series_impact": round(time_series_edge, 4),
        "time_series_profile": ts,
        "key_factors": [
            {"side": "home" if player_edge >= 0 else "away", "label": "أثر اللاعبين كأفراد", "value": f"فرق مؤشرات النجوم والحارس والمسددين: {player_edge:+.3f}", "impact": round(player_edge, 4)},
            {"side": "home" if team_edge >= 0 else "away", "label": "أرقام المنتخب في البطولة", "value": f"ضغط هجومي، تسديدات على المرمى، سيطرة وتمرير: {team_edge:+.3f}", "impact": round(team_edge, 4)},
            {"side": "home" if timing_edge >= 0 else "away", "label": "زمن تسجيل الأهداف", "value": f"زخم متأخر/أهداف عودة/حسم: {timing_edge:+.3f}", "impact": round(timing_edge, 4)},
            {"side": "home" if time_series_edge >= 0 else "away", "label": "اتجاه السلسلة الزمنية", "value": f"زخم آخر المباريات مع عقوبة التذبذب: {time_series_edge:+.3f}", "impact": round(time_series_edge, 4)},
        ],
    }


def _time_series_edge(home: str, away: str, scenario: dict[str, Any], time_series: dict[str, Any]) -> dict[str, Any]:
    teams = time_series.get("teams", {}) if isinstance(time_series, dict) else {}
    hp = teams.get(home, {})
    ap = teams.get(away, {})
    weight = float(scenario.get("time_series_weight", 0.9))
    home_edge = float(hp.get("time_series_edge", 0.0))
    away_edge = float(ap.get("time_series_edge", 0.0))
    confidence = (float(hp.get("confidence", 0.25)) + float(ap.get("confidence", 0.25))) / 2
    volatility_gap = float(hp.get("volatility_index", 0.0)) - float(ap.get("volatility_index", 0.0))
    edge = (home_edge - away_edge) * weight * max(0.35, min(1.0, confidence)) - volatility_gap * 0.0015
    return {
        "edge": max(-0.10, min(0.10, edge)),
        "home_momentum_index": hp.get("momentum_index"),
        "away_momentum_index": ap.get("momentum_index"),
        "home_stat_trend_index": hp.get("stat_trend_index"),
        "away_stat_trend_index": ap.get("stat_trend_index"),
        "home_volatility_index": hp.get("volatility_index"),
        "away_volatility_index": ap.get("volatility_index"),
        "confidence": round(confidence, 4),
    }


def _scenario_reliability(rounds: list[dict[str, Any]], learning: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    matches = [match for round_item in rounds for match in round_item["matches"]]
    if not matches:
        return {"estimated_accuracy": 0.0, "confidence_grade": "غير كافية", "high_risk_matches": 0, "average_confidence_margin": 0.0, "average_penalty_probability": 0.0}
    base_accuracy = float(learning.get("summary", {}).get("accuracy", 0.50))
    margins = [float(match.get("confidence_margin", 0)) for match in matches]
    penalties = [float(match.get("penalty_shootout", {}).get("probability", 0)) for match in matches]
    high_risk = sum(1 for match in matches if match.get("upset_risk") == "high")
    avg_margin = sum(margins) / len(margins)
    avg_penalty = sum(penalties) / len(penalties)
    scenario_bonus = {"A": 0.035, "B": 0.015, "C": -0.015}.get(str(scenario.get("id")), 0.0)
    reliability = base_accuracy + scenario_bonus + avg_margin * 0.28 - avg_penalty * 0.10 - (high_risk / len(matches)) * 0.12
    reliability = max(0.42, min(0.82, reliability))
    grade = "عالية" if reliability >= 0.68 else "متوسطة" if reliability >= 0.57 else "تجريبية"
    return {
        "estimated_accuracy": reliability,
        "confidence_grade": grade,
        "high_risk_matches": high_risk,
        "average_confidence_margin": avg_margin,
        "average_penalty_probability": avg_penalty,
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    main()
