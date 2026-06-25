from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .core import AgentResult, PipelineState
from .model import DixonColesLiteModel, load_results, load_team_priors, normalize_three_way


class DataCollectionAgent:
    name = "data_collection"

    def __init__(
        self,
        historical_results_path: Path,
        butterfly_events_path: Path,
        team_priors_path: Path | None = None,
        advanced_stats_path: Path | None = None,
        calibration_path: Path | None = None,
        economic_world_path: Path | None = None,
    ):
        self.historical_results_path = historical_results_path
        self.butterfly_events_path = butterfly_events_path
        self.team_priors_path = team_priors_path
        self.advanced_stats_path = advanced_stats_path
        self.calibration_path = calibration_path
        self.economic_world_path = economic_world_path

    def run(self, state: PipelineState) -> AgentResult:
        results = load_results(self.historical_results_path)
        events = _read_csv(self.butterfly_events_path)
        team_priors = load_team_priors(self.team_priors_path) if self.team_priors_path else {}
        advanced_stats = _read_csv(self.advanced_stats_path) if self.advanced_stats_path and self.advanced_stats_path.exists() else []
        economic_world = _read_csv(self.economic_world_path) if self.economic_world_path and self.economic_world_path.exists() else []
        calibration = _read_json(self.calibration_path) if self.calibration_path and self.calibration_path.exists() else {}
        match_events = [row for row in events if row["match_id"] == state.match.match_id]

        warnings = []
        if len(results) < 20:
            warnings.append("Historical sample is small; confidence should be widened.")
        if not match_events:
            warnings.append("No butterfly events found for this match.")

        return AgentResult(
            agent_name=self.name,
            status="ok",
            summary=(
                f"Loaded {len(results)} historical matches, {len(team_priors)} team priors, "
                f"{len(economic_world)} economic-world profiles, and {len(match_events)} live event cues."
            ),
            payload={
                "historical_results": results,
                "butterfly_events": match_events,
                "team_priors": team_priors,
                "team_seed_ranks_path": str(self.team_priors_path) if self.team_priors_path else None,
                "advanced_stats": advanced_stats,
                "economic_world": economic_world,
                "calibration": calibration,
            },
            warnings=warnings,
        )


class SpecialistAnalysisAgent:
    name = "specialist_analysis"

    def run(self, state: PipelineState) -> AgentResult:
        data = state.get_payload("data_collection")
        model = DixonColesLiteModel(team_priors=data.get("team_priors", {})).fit(data["historical_results"])
        prediction = model.predict(
            state.match.home_team,
            state.match.away_team,
            neutral_venue=bool(state.match.metadata.get("neutral_venue")),
        )
        top_scores = sorted(prediction.score_matrix, key=lambda row: row.probability, reverse=True)[:5]

        payload = {
            "baseline_probabilities": {
                "home_win": prediction.home_win,
                "draw": prediction.draw,
                "away_win": prediction.away_win,
            },
            "expected_goals": {
                "home": prediction.expected_home_goals,
                "away": prediction.expected_away_goals,
            },
            "top_scores": [asdict(score) for score in top_scores],
        }
        return AgentResult(
            agent_name=self.name,
            status="ok",
            summary="Produced Dixon-Coles-lite baseline probabilities.",
            payload=payload,
        )


class TeamIntelligenceAgent:
    name = "team_intelligence"

    def run(self, state: PipelineState) -> AgentResult:
        data = state.get_payload("data_collection")
        matches = data["historical_results"]
        advanced_stats = data.get("advanced_stats", [])
        seed_ranks = _read_seed_ranks(data.get("team_seed_ranks_path"))
        home = state.match.home_team
        away = state.match.away_team
        home_profile = _team_profile(home, matches, seed_ranks)
        away_profile = _team_profile(away, matches, seed_ranks)
        home_advanced = _advanced_profile(home, advanced_stats)
        away_advanced = _advanced_profile(away, advanced_stats)
        home_score = _team_factor_score(home_profile)
        away_score = _team_factor_score(away_profile)
        calibration = data.get("calibration", {})
        advanced_weight = float(calibration.get("advanced_stats_weight", 1.0))
        home_score += _advanced_factor_score(home_advanced) * advanced_weight
        away_score += _advanced_factor_score(away_advanced) * advanced_weight
        diff = max(min(home_score - away_score, 0.16), -0.16)

        factors = []
        factors.extend(_profile_factors(home_profile, "home"))
        factors.extend(_profile_factors(away_profile, "away"))
        factors.extend(_advanced_factors(home_advanced, "home"))
        factors.extend(_advanced_factors(away_advanced, "away"))
        if abs(diff) < 0.025:
            factors.append(
                {
                    "side": "neutral",
                    "label": "الفارق الكلي ضيق",
                    "value": "لا توجد أفضلية رقمية حاسمة من أداء البطولة والـ seed.",
                    "impact": 0.0,
                }
            )

        warnings = []
        if home_profile["matches"] < 2 or away_profile["matches"] < 2:
            warnings.append("Tournament sample is still small; prediction should stay conservative.")
        if not home_advanced["matches"] or not away_advanced["matches"]:
            warnings.append("FIFA/beIN advanced match stats are not connected yet for both teams; using scores, group form, priors, and butterfly cues.")

        return AgentResult(
            agent_name=self.name,
            status="ok",
            summary=f"Computed tournament form and prior-strength factors for {home} and {away}.",
            payload={
                "home_profile": home_profile,
                "away_profile": away_profile,
                "home_advanced_profile": home_advanced,
                "away_advanced_profile": away_advanced,
                "home_factor_score": home_score,
                "away_factor_score": away_score,
                "probability_adjustment": diff,
                "factors": factors,
            },
            warnings=warnings,
        )


class ButterflyFactorsAgent:
    name = "butterfly_factors"

    impact_values = {"low": 0.015, "medium": 0.035, "high": 0.07}
    confidence_values = {"low": 0.45, "medium": 0.7, "high": 0.9}

    def run(self, state: PipelineState) -> AgentResult:
        events = state.get_payload("data_collection").get("butterfly_events", [])
        scored_events = []
        home_adjustment = 0.0
        away_adjustment = 0.0

        for event in events:
            event_time = _parse_datetime(event["event_time_utc"])
            hours_to_kickoff = max((state.match.kickoff_utc - event_time).total_seconds() / 3600, 0.0)
            time_weight = _recency_weight(hours_to_kickoff)
            impact = self.impact_values[event["impact"]]
            confidence = self.confidence_values[event["confidence"]]
            signed_effect = impact * confidence * time_weight

            if event["benefits"] == "home":
                home_adjustment += signed_effect
            elif event["benefits"] == "away":
                away_adjustment += signed_effect
            elif event["benefits"] == "against_home":
                home_adjustment -= signed_effect
            elif event["benefits"] == "against_away":
                away_adjustment -= signed_effect

            scored_events.append(
                {
                    "event_type": event["event_type"],
                    "description": event["description"],
                    "hours_to_kickoff": round(hours_to_kickoff, 2),
                    "time_weight": round(time_weight, 3),
                    "signed_effect": round(signed_effect, 4),
                    "benefits": event["benefits"],
                }
            )

        return AgentResult(
            agent_name=self.name,
            status="ok",
            summary=f"Scored {len(scored_events)} high-impact contextual cues.",
            payload={
                "home_adjustment": home_adjustment,
                "away_adjustment": away_adjustment,
                "events": scored_events,
            },
        )


class EconomicWorldAgent:
    name = "economic_world"

    columns = [
        "gdp_per_capita_index",
        "population_index",
        "football_market_index",
        "academy_pipeline_index",
        "climate_fit_index",
        "league_export_index",
        "home_region_fit_index",
    ]
    weights = {
        "gdp_per_capita_index": 0.16,
        "population_index": 0.13,
        "football_market_index": 0.23,
        "academy_pipeline_index": 0.20,
        "climate_fit_index": 0.08,
        "league_export_index": 0.15,
        "home_region_fit_index": 0.05,
    }

    def run(self, state: PipelineState) -> AgentResult:
        rows = state.get_payload("data_collection").get("economic_world", [])
        table = {row["team"]: row for row in rows}
        home = self._profile(state.match.home_team, table)
        away = self._profile(state.match.away_team, table)
        home_score = self._score(home)
        away_score = self._score(away)
        diff = max(min((home_score - away_score) / 1000, 0.09), -0.09)
        factors = self._factors(home, "home") + self._factors(away, "away")

        warnings = []
        if not home.get("found") or not away.get("found"):
            warnings.append("Economic world profile is missing for at least one team; long-run country-strength layer is incomplete.")

        return AgentResult(
            agent_name=self.name,
            status="ok",
            summary=(
                f"Computed long-run country-strength layer: "
                f"{state.match.home_team} {home_score:.1f} vs {state.match.away_team} {away_score:.1f}."
            ),
            payload={
                "home_profile": home,
                "away_profile": away,
                "home_score": home_score,
                "away_score": away_score,
                "probability_adjustment": diff,
                "factors": factors,
            },
            warnings=warnings,
        )

    def _profile(self, team: str, table: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
        row = table.get(team)
        if not row:
            return {"team": team, "found": False, **{column: 50.0 for column in self.columns}, "notes": "missing"}
        profile = {"team": team, "found": True, "notes": row.get("notes", "")}
        for column in self.columns:
            profile[column] = _safe_float(row.get(column), 50.0)
        return profile

    def _score(self, profile: Dict[str, Any]) -> float:
        return sum(profile[column] * weight for column, weight in self.weights.items())

    def _factors(self, profile: Dict[str, Any], side: str) -> List[Dict[str, Any]]:
        score = self._score(profile)
        return [
            {
                "side": side,
                "label": "نموذج العالم الاقتصادي",
                "value": (
                    f"قوة بنيوية {score:.1f}/100: دخل {profile['gdp_per_capita_index']:.0f}، "
                    f"سكان {profile['population_index']:.0f}، سوق كرة {profile['football_market_index']:.0f}، "
                    f"أكاديميات {profile['academy_pipeline_index']:.0f}، مناخ {profile['climate_fit_index']:.0f}."
                ),
                "impact": round(max(min((score - 50) / 1000, 0.06), -0.06), 3),
            }
        ]


class CriticAuditorAgent:
    name = "critic_auditor"

    def run(self, state: PipelineState) -> AgentResult:
        baseline = state.get_payload("specialist_analysis")["baseline_probabilities"]
        butterfly = state.get_payload("butterfly_factors")
        team_intel = state.get_payload("team_intelligence")
        economic = state.get_payload("economic_world")
        data_result = state.results["data_collection"]
        warnings = list(data_result.warnings)
        warnings.extend(state.results["team_intelligence"].warnings)
        warnings.extend(state.results.get("economic_world", AgentResult("economic_world", "missing", "")).warnings)

        favorite = max(baseline, key=baseline.get)
        objections = []
        if favorite == "home_win" and butterfly["away_adjustment"] > 0.025:
            objections.append("Away-side late contextual evidence challenges the home baseline.")
        if favorite == "away_win" and butterfly["home_adjustment"] > 0.025:
            objections.append("Home-side late contextual evidence challenges the away baseline.")
        if abs(baseline["home_win"] - baseline["away_win"]) < 0.06:
            objections.append("Baseline edge is narrow; avoid overconfident final probability.")
        if favorite == "home_win" and team_intel["probability_adjustment"] < -0.05:
            objections.append("Tournament form layer challenges the home-side baseline.")
        if favorite == "away_win" and team_intel["probability_adjustment"] > 0.05:
            objections.append("Tournament form layer challenges the away-side baseline.")
        if favorite == "home_win" and economic.get("probability_adjustment", 0.0) < -0.04:
            objections.append("Economic-world layer challenges the home-side baseline.")
        if favorite == "away_win" and economic.get("probability_adjustment", 0.0) > 0.04:
            objections.append("Economic-world layer challenges the away-side baseline.")

        confidence_penalty = 0.0
        if warnings:
            confidence_penalty += 0.06
        if objections:
            confidence_penalty += 0.05

        return AgentResult(
            agent_name=self.name,
            status="reviewed",
            summary=f"Devil's Advocate found {len(objections)} objections.",
            payload={
                "favorite": favorite,
                "objections": objections,
                "confidence_penalty": confidence_penalty,
            },
            warnings=warnings,
        )


class SynthesizerAgent:
    name = "synthesizer"

    def run(self, state: PipelineState) -> AgentResult:
        baseline = state.get_payload("specialist_analysis")["baseline_probabilities"]
        expected_goals = state.get_payload("specialist_analysis")["expected_goals"]
        team_intel = state.get_payload("team_intelligence")
        economic = state.get_payload("economic_world")
        butterfly = state.get_payload("butterfly_factors")
        critic = state.get_payload("critic_auditor")
        calibration = state.get_payload("data_collection").get("calibration", {})

        team_weight = float(calibration.get("team_adjustment_weight", 1.0))
        butterfly_weight = float(calibration.get("butterfly_adjustment_weight", 1.0))
        confidence_weight = float(calibration.get("confidence_penalty_weight", 1.0))
        economic_weight = float(calibration.get("economic_world_weight", 0.65))
        team_adjustment = team_intel["probability_adjustment"] * team_weight
        economic_adjustment = economic.get("probability_adjustment", 0.0) * economic_weight
        home_butterfly = butterfly["home_adjustment"] * butterfly_weight
        away_butterfly = butterfly["away_adjustment"] * butterfly_weight
        home = baseline["home_win"] + team_adjustment + economic_adjustment + home_butterfly - away_butterfly * 0.35
        away = baseline["away_win"] - team_adjustment - economic_adjustment + away_butterfly - home_butterfly * 0.35
        draw = baseline["draw"] - abs(butterfly["home_adjustment"] - butterfly["away_adjustment"]) * 0.15
        home, draw, away = normalize_three_way(home, draw, away)

        confidence_width = min(0.38, 0.12 + critic["confidence_penalty"] * confidence_weight)
        final = {
            "home_win": home,
            "draw": draw,
            "away_win": away,
            "confidence_interval_width": confidence_width,
            "expected_goals": expected_goals,
            "key_factors": economic.get("factors", []) + team_intel["factors"] + _butterfly_factor_cards(butterfly),
            "data_quality_warnings": state.results["team_intelligence"].warnings + state.results.get("economic_world", AgentResult("economic_world", "missing", "")).warnings,
            "calibration_version": calibration.get("version", 1),
            "recommended_label": _label_for_probabilities(home, draw, away),
            "explanation": _build_explanation(state, home, draw, away),
        }

        return AgentResult(
            agent_name=self.name,
            status="ok",
            summary=f"Final forecast: {final['recommended_label']}.",
            payload=final,
        )


class SelfCorrectionAgent:
    name = "self_correction"

    def __init__(self, actual_results_path: Path):
        self.actual_results_path = actual_results_path

    def run(self, state: PipelineState) -> AgentResult:
        actuals = {row["match_id"]: row for row in _read_csv(self.actual_results_path)}
        forecast = state.get_payload("synthesizer")
        if state.match.match_id not in actuals:
            return AgentResult(
                agent_name=self.name,
                status="pending",
                summary="Actual result is not available yet; calibration update skipped.",
                payload={},
            )

        actual = actuals[state.match.match_id]
        outcome = _actual_outcome(int(actual["home_goals"]), int(actual["away_goals"]))
        probs = {
            "home_win": forecast["home_win"],
            "draw": forecast["draw"],
            "away_win": forecast["away_win"],
        }
        brier = sum((probs[k] - (1.0 if k == outcome else 0.0)) ** 2 for k in probs)
        log_loss = -math.log(max(probs[outcome], 1e-9))
        calibration_note = "increase weight of challenged factors" if log_loss > 1.1 else "keep weights stable"

        return AgentResult(
            agent_name=self.name,
            status="updated",
            summary=f"Compared forecast with actual result; {calibration_note}.",
            payload={
                "actual_outcome": outcome,
                "brier_score": brier,
                "log_loss": log_loss,
                "calibration_note": calibration_note,
            },
        )


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_float(value, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _read_seed_ranks(path: str | None) -> Dict[str, int]:
    if not path:
        return {}
    seed_path = Path(path)
    if not seed_path.exists():
        return {}
    with seed_path.open("r", encoding="utf-8", newline="") as f:
        return {row["team"]: int(row["seed_rank"]) for row in csv.DictReader(f)}


def _team_profile(team: str, matches: List[Any], seed_ranks: Dict[str, int]) -> Dict[str, Any]:
    profile = {
        "team": team,
        "matches": 0,
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "goals_for": 0,
        "goals_against": 0,
        "goal_difference": 0,
        "points": 0,
        "points_per_match": 0.0,
        "seed_rank": seed_ranks.get(team),
    }
    for match in matches:
        if match.home_team == team:
            gf, ga = match.home_goals, match.away_goals
        elif match.away_team == team:
            gf, ga = match.away_goals, match.home_goals
        else:
            continue
        profile["matches"] += 1
        profile["goals_for"] += gf
        profile["goals_against"] += ga
        if gf > ga:
            profile["wins"] += 1
            profile["points"] += 3
        elif gf == ga:
            profile["draws"] += 1
            profile["points"] += 1
        else:
            profile["losses"] += 1
    profile["goal_difference"] = profile["goals_for"] - profile["goals_against"]
    if profile["matches"]:
        profile["points_per_match"] = profile["points"] / profile["matches"]
    return profile


def _team_factor_score(profile: Dict[str, Any]) -> float:
    matches = max(profile["matches"], 1)
    gd_per_match = profile["goal_difference"] / matches
    gf_per_match = profile["goals_for"] / matches
    ga_per_match = profile["goals_against"] / matches
    ppg = profile["points_per_match"]
    rank = profile.get("seed_rank") or 55
    seed_component = max(min((55 - rank) / 500, 0.07), -0.07)
    form_component = max(min((ppg - 1.0) * 0.045, 0.08), -0.08)
    gd_component = max(min(gd_per_match * 0.055, 0.11), -0.11)
    scoring_component = max(min((gf_per_match - ga_per_match) * 0.025, 0.05), -0.05)
    return seed_component + form_component + gd_component + scoring_component


def _profile_factors(profile: Dict[str, Any], side: str) -> List[Dict[str, Any]]:
    matches = max(profile["matches"], 1)
    gd_per_match = profile["goal_difference"] / matches
    rank = profile.get("seed_rank")
    factors = [
        {
            "side": side,
            "label": "أداء البطولة حتى الآن",
            "value": (
                f"{profile['points']} نقطة من {profile['matches']} مباراة، "
                f"فارق أهداف {profile['goal_difference']}."
            ),
            "impact": round(max(min(gd_per_match * 0.055, 0.11), -0.11), 3),
        }
    ]
    if rank:
        factors.append(
            {
                "side": side,
                "label": "قوة المنتخب قبل المباراة",
                "value": f"Seed rank داخل النموذج: {rank}.",
                "impact": round(max(min((55 - rank) / 500, 0.07), -0.07), 3),
            }
        )
    if profile["goals_against"] >= 4:
        factors.append(
            {
                "side": side,
                "label": "إنذار دفاعي",
                "value": f"استقبل {profile['goals_against']} أهداف في {profile['matches']} مباراة.",
                "impact": -0.045,
            }
        )
    return factors


def _advanced_profile(team: str, rows: List[Dict[str, str]]) -> Dict[str, Any]:
    numeric_fields = [
        "shots",
        "shots_on_target",
        "possession",
        "xg",
        "big_chances",
        "corners",
        "yellow_cards",
        "red_cards",
        "passes_into_final_third",
        "fouls",
        "offsides",
        "saves",
        "accurate_passes",
        "total_passes",
        "pass_pct",
        "accurate_crosses",
        "total_crosses",
        "blocked_shots",
        "total_tackles",
        "interceptions",
        "clearances",
        "match_momentum",
        "momentum_last_15",
        "dominance_index",
        "attacking_pressure_index",
    ]
    profile: Dict[str, Any] = {"team": team, "matches": 0}
    for field in numeric_fields:
        profile[field] = 0.0
    for row in rows:
        if row.get("team") != team:
            continue
        profile["matches"] += 1
        for field in numeric_fields:
            try:
                profile[field] += float(row.get(field) or 0)
            except ValueError:
                pass
    if profile["matches"]:
        for field in numeric_fields:
            profile[f"{field}_per_match"] = profile[field] / profile["matches"]
    return profile


def _advanced_factor_score(profile: Dict[str, Any]) -> float:
    if not profile["matches"]:
        return 0.0
    xg = profile.get("xg_per_match", 0.0)
    shots_on_target = profile.get("shots_on_target_per_match", 0.0)
    possession = profile.get("possession_per_match", 50.0)
    red_cards = profile.get("red_cards_per_match", 0.0)
    dominance = profile.get("dominance_index_per_match", 50.0)
    pressure = profile.get("attacking_pressure_index_per_match", 50.0)
    timeline_momentum = profile.get("match_momentum_per_match", 0.0)
    last_15 = profile.get("momentum_last_15_per_match", 0.0)
    score = 0.0
    score += max(min((xg - 1.25) * 0.045, 0.07), -0.06)
    score += max(min((shots_on_target - 4.0) * 0.012, 0.05), -0.04)
    score += max(min((possession - 50.0) * 0.002, 0.035), -0.035)
    score += max(min((dominance - 50.0) * 0.0015, 0.045), -0.045)
    score += max(min((pressure - 50.0) * 0.0018, 0.05), -0.05)
    score += max(min(timeline_momentum * 0.01, 0.06), -0.06)
    score += max(min(last_15 * 0.012, 0.06), -0.06)
    score -= min(red_cards * 0.06, 0.08)
    return score


def _advanced_factors(profile: Dict[str, Any], side: str) -> List[Dict[str, Any]]:
    if not profile["matches"]:
        return []
    factors = [
        {
            "side": side,
            "label": "إحصاءات أداء متقدمة",
            "value": (
                f"xG {profile.get('xg_per_match', 0):.2f}، "
                f"تسديدات على المرمى {profile.get('shots_on_target_per_match', 0):.1f}، "
                f"استحواذ {profile.get('possession_per_match', 0):.1f}%، "
                f"ضغط هجومي {profile.get('attacking_pressure_index_per_match', 0):.1f}."
            ),
            "impact": round(_advanced_factor_score(profile), 3),
        }
    ]
    if profile.get("match_momentum_per_match") or profile.get("momentum_last_15_per_match"):
        factors.append(
            {
                "side": side,
                "label": "Match Momentum",
                "value": (
                    f"زخم المباراة {profile.get('match_momentum_per_match', 0):.1f}، "
                    f"آخر 15 دقيقة {profile.get('momentum_last_15_per_match', 0):.1f}."
                ),
                "impact": round(max(min(profile.get("match_momentum_per_match", 0) * 0.01, 0.06), -0.06), 3),
            }
        )
    return factors


def _butterfly_factor_cards(butterfly: Dict[str, Any]) -> List[Dict[str, Any]]:
    cards = []
    for event in butterfly.get("events", []):
        side = "neutral"
        if event["benefits"] in {"home", "against_away"}:
            side = "home"
        elif event["benefits"] in {"away", "against_home"}:
            side = "away"
        cards.append(
            {
                "side": side,
                "label": "أثر فراشة",
                "value": event["description"],
                "impact": event["signed_effect"],
            }
        )
    return cards


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _recency_weight(hours_to_kickoff: float) -> float:
    return 0.35 + 0.65 * math.exp(-hours_to_kickoff / 48)


def _label_for_probabilities(home: float, draw: float, away: float) -> str:
    labels = {"home_win": home, "draw": draw, "away_win": away}
    return max(labels, key=labels.get)


def _actual_outcome(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home_win"
    if home_goals < away_goals:
        return "away_win"
    return "draw"


def _build_explanation(state: PipelineState, home: float, draw: float, away: float) -> str:
    match = state.match
    butterfly_events = state.get_payload("butterfly_factors").get("events", [])
    critic_objections = state.get_payload("critic_auditor").get("objections", [])
    leader = _label_for_probabilities(home, draw, away)
    event_text = "; ".join(event["description"] for event in butterfly_events[:2]) or "no major late cue"
    objection_text = "; ".join(critic_objections) or "no blocking objection"
    return (
        f"{match.home_team} vs {match.away_team}: baseline model favors {leader}; "
        f"butterfly cues: {event_text}; critic: {objection_text}."
    )
