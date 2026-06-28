from __future__ import annotations

import csv
import json
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


def main() -> None:
    learning = _load_learning()
    fixtures = _read_csv(DATA / "knockout_fixtures.csv")
    rounds: list[dict[str, Any]] = []
    current = [_fixture_to_match(row) for row in fixtures]
    round_index = 0
    next_match_number = 89

    while current:
        round_name = ROUND_NAMES[round_index]
        matches = []
        winners = []
        for idx, fixture in enumerate(current, start=1):
            prediction = _predict_knockout_match(fixture, round_name, learning)
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
                    "source_note": "Projected by Agent Harness knockout simulator",
                }
            )
            next_match_number += 1
        round_index += 1

    champion = rounds[-1]["matches"][0]["winner"] if rounds and rounds[-1]["matches"] else "TBD"
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "method": "Agent Harness knockout simulator: group-error learning + Dixon/ economic blend + advanced stats + penalty shootout model. No draw is allowed in knockout outputs.",
        "learning_summary": learning,
        "champion": champion,
        "rounds": rounds,
        "sources": [
            "Local audited group-stage forecast ledger and accuracy_report.json",
            "data/match_advanced_stats.csv from ESPN-derived open match statistics where available",
            "Published Round-of-32 pairings from FIFA/beIN/Yallakora text supplied with this run",
        ],
    }
    OUTPUTS.mkdir(exist_ok=True)
    (OUTPUTS / "knockout_bracket_prediction.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Projected knockout bracket through final. Champion={champion}")


def _load_learning() -> dict[str, Any]:
    path = OUTPUTS / "group_learning_report.json"
    if not path.exists():
        import subprocess, sys
        subprocess.run([sys.executable, str(ROOT / "learn_from_group_errors.py")], cwd=ROOT, check=True)
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


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


def _predict_knockout_match(fixture: dict[str, str], round_name: str, learning: dict[str, Any]) -> dict[str, Any]:
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
    shrink = float(adjustments.get("favorite_shrink", 0.08))
    upset_floor = float(adjustments.get("upset_floor", 0.14))
    penalty_sensitivity = float(adjustments.get("penalty_sensitivity", 1.0))

    home, away = _shrink_two_way(home, away, shrink, upset_floor)
    draw = max(0.05, min(0.42, draw * penalty_sensitivity))
    penalty_home = _penalty_edge(fixture["home_team"], fixture["away_team"])
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
        "key_factors": final.get("key_factors", [])[:6],
        "model_diagnostics": final.get("model_diagnostics", {}),
        "blend_weights": final.get("blend_weights", {}),
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


def _penalty_edge(home: str, away: str) -> float:
    stats = _team_stats()
    ranks = _seed_ranks()
    h, a = stats.get(home, {}), stats.get(away, {})
    rank_edge = (ranks.get(away, 48) - ranks.get(home, 48)) / 120.0
    keeper_edge = (h.get("saves", 1.5) - a.get("saves", 1.5)) * 0.025
    shot_edge = (h.get("shots_on_target", 3.0) - a.get("shots_on_target", 3.0)) * 0.012
    pressure_edge = (h.get("attacking_pressure_index", 45.0) - a.get("attacking_pressure_index", 45.0)) * 0.002
    discipline_edge = ((a.get("yellow_cards", 1.0) + 2 * a.get("red_cards", 0.0)) - (h.get("yellow_cards", 1.0) + 2 * h.get("red_cards", 0.0))) * 0.012
    return max(0.35, min(0.65, 0.50 + rank_edge + keeper_edge + shot_edge + pressure_edge + discipline_edge))


if __name__ == "__main__":
    main()
