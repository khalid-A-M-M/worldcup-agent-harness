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
TARGET = DATA / "equation_learning.json"


def main() -> None:
    report = _load_accuracy_report()
    matches = report.get("matches", [])
    stats = _team_stats()
    rows = [_row_with_edges(row, stats) for row in matches]
    learned = _learn_equation(rows)
    TARGET.write_text(json.dumps(learned, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "Learned equation parameters from "
        f"{learned['training_summary']['completed_matches']} matches: "
        f"favorite_temperature={learned['coefficients']['favorite_temperature']:.3f}, "
        f"stat_signal_gain={learned['coefficients']['stat_signal_gain']:.3f}"
    )


def _load_accuracy_report() -> dict[str, Any]:
    path = OUTPUTS / "accuracy_report.json"
    if not path.exists():
        return {"metrics": {}, "matches": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _team_stats() -> dict[str, dict[str, float]]:
    rows = _read_csv(DATA / "match_advanced_stats.csv")
    fields = ["shots_on_target", "attacking_pressure_index", "dominance_index", "pass_pct", "saves"]
    grouped: dict[str, dict[str, float]] = {}
    counts: dict[str, int] = {}
    for row in rows:
        team = row.get("team", "")
        if not team:
            continue
        grouped.setdefault(team, {field: 0.0 for field in fields})
        counts[team] = counts.get(team, 0) + 1
        for field in fields:
            grouped[team][field] += _safe_float(row.get(field), 0.0)
    for team, values in grouped.items():
        n = max(counts.get(team, 1), 1)
        for field in fields:
            values[field] /= n
    return grouped


def _row_with_edges(row: dict[str, Any], stats: dict[str, dict[str, float]]) -> dict[str, Any]:
    home = row.get("home_team", "")
    away = row.get("away_team", "")
    hs, aways = stats.get(home, {}), stats.get(away, {})
    stat_edge = (
        (hs.get("dominance_index", 50) - aways.get("dominance_index", 50)) * 0.0009
        + (hs.get("attacking_pressure_index", 45) - aways.get("attacking_pressure_index", 45)) * 0.0009
        + (hs.get("shots_on_target", 3) - aways.get("shots_on_target", 3)) * 0.006
        + (hs.get("pass_pct", 0.82) - aways.get("pass_pct", 0.82)) * 0.08
    )
    actual = row.get("actual")
    predicted = row.get("predicted")
    return {
        **row,
        "stat_edge": stat_edge,
        "actual_side": 1 if actual == "home_win" else -1 if actual == "away_win" else 0,
        "predicted_side": 1 if predicted == "home_win" else -1 if predicted == "away_win" else 0,
    }


def _learn_equation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = len(rows)
    correct = sum(1 for row in rows if row.get("correct"))
    accuracy = correct / completed if completed else 0.0
    misses = [row for row in rows if not row.get("correct")]
    favorite_misses = [row for row in misses if row.get("predicted") in {"home_win", "away_win"}]
    draw_misses = [row for row in misses if row.get("actual") == "draw"]
    home_miss_actuals = sum(1 for row in misses if row.get("actual") == "home_win")
    away_miss_actuals = sum(1 for row in misses if row.get("actual") == "away_win")
    favorite_error_rate = len(favorite_misses) / max(completed, 1)
    draw_error_rate = len(draw_misses) / max(completed, 1)

    aligned = 0
    observed = 0
    for row in rows:
        if row["actual_side"] == 0 or abs(row["stat_edge"]) < 1e-6:
            continue
        observed += 1
        if row["stat_edge"] * row["actual_side"] > 0:
            aligned += 1
    stat_alignment = aligned / observed if observed else 0.5

    favorite_temperature = _clamp(1.0 - favorite_error_rate * 0.55, 0.72, 1.08)
    home_bias_delta = _clamp((home_miss_actuals - away_miss_actuals) / max(completed, 1) * 0.045, -0.035, 0.035)
    draw_intercept = _clamp(draw_error_rate * 0.055, 0.0, 0.05)
    draw_temperature = _clamp(1.0 + draw_error_rate * 0.38, 0.92, 1.22)
    stat_signal_gain = _clamp(0.70 + stat_alignment * 0.78, 0.70, 1.45)
    player_signal_gain = _clamp(0.82 + accuracy * 0.34 - favorite_error_rate * 0.18, 0.72, 1.22)
    timing_signal_gain = _clamp(0.78 + draw_error_rate * 0.42 + (1 - accuracy) * 0.10, 0.78, 1.28)
    penalty_logit_gain = _clamp(0.92 + draw_error_rate * 0.50, 0.92, 1.35)
    upset_curve = _clamp(0.10 + favorite_error_rate * 0.22, 0.10, 0.26)

    return {
        "equation_version": int(_previous_version()) + 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "formula": {
            "two_way_logit": "favorite_temperature * base_logit + stat_signal_gain * stat_edge + player_signal_gain * player_edge + timing_signal_gain * timing_edge + home_bias_delta",
            "draw_mass": "draw_temperature * base_draw + draw_intercept + scenario_chaos_adjustment",
            "penalty_logit": "penalty_logit_gain * base_penalty_logit + goalkeeper_edge + taker_edge",
            "upset_floor": "base_upset_floor + upset_curve when favorite errors rise",
        },
        "coefficients": {
            "favorite_temperature": favorite_temperature,
            "home_bias_delta": home_bias_delta,
            "draw_intercept": draw_intercept,
            "draw_temperature": draw_temperature,
            "stat_signal_gain": stat_signal_gain,
            "player_signal_gain": player_signal_gain,
            "timing_signal_gain": timing_signal_gain,
            "penalty_logit_gain": penalty_logit_gain,
            "upset_curve": upset_curve,
        },
        "training_summary": {
            "completed_matches": completed,
            "correct": correct,
            "accuracy": accuracy,
            "misses": len(misses),
            "favorite_error_rate": favorite_error_rate,
            "draw_error_rate": draw_error_rate,
            "stat_alignment": stat_alignment,
            "home_miss_actuals": home_miss_actuals,
            "away_miss_actuals": away_miss_actuals,
        },
        "notes": [
            "هذه الطبقة تتعلم معاملات معادلة تصحيحية من أخطاء المباريات المكتملة بدلاً من الاكتفاء بتغيير أوزان عامة.",
            "كل تحديث بعد مباراة يحفظ نسخة جديدة من equation_version لاستخدامها في توقعات خروج المغلوب التالية.",
        ],
    }


def _previous_version() -> int:
    if not TARGET.exists():
        return 0
    try:
        return int(json.loads(TARGET.read_text(encoding="utf-8")).get("equation_version", 0))
    except (json.JSONDecodeError, ValueError):
        return 0


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


if __name__ == "__main__":
    main()
