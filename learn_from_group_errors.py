from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"


def main() -> None:
    report_path = OUTPUTS / "accuracy_report.json"
    if not report_path.exists():
        raise SystemExit("accuracy_report.json is missing; run evolve_after_results.py first.")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    matches = report.get("matches", [])
    metrics = report.get("metrics", {})
    missed = [row for row in matches if not row.get("correct")]
    correct = [row for row in matches if row.get("correct")]

    by_predicted = Counter(row.get("predicted") for row in missed)
    by_actual = Counter(row.get("actual") for row in missed)
    severe = [row for row in missed if float(row.get("log_loss") or 0) >= 1.15]
    shock = [row for row in missed if float(row.get("probability_actual") or 0) < 0.18]

    lessons = []
    if metrics.get("accuracy", 0) < 0.60:
        lessons.append("Low group-stage hit rate: shrink overconfident favorites and increase upset sensitivity.")
    if by_actual.get("draw", 0):
        lessons.append("Draw outcomes hurt the group model; knockout conversion must treat draw mass as extra-time/penalty risk, not discard it.")
    if shock:
        lessons.append("Several misses assigned very low probability to the actual outcome; widen uncertainty bands before elimination matches.")
    if by_predicted.get("away_win", 0) > by_predicted.get("home_win", 0):
        lessons.append("Away-side/favorite bias appeared in misses; neutralize nominal home/away wording in knockout fixtures.")

    accuracy = float(metrics.get("accuracy") or 0.0)
    log_loss = metrics.get("mean_log_loss") or 0.0
    uncertainty_multiplier = 1.0 + max(0.0, 0.62 - accuracy) * 0.75 + min(log_loss, 2.0) * 0.06
    favorite_shrink = min(0.18, max(0.04, (0.58 - accuracy) * 0.22 + 0.04))
    upset_floor = min(0.24, max(0.12, 0.10 + len(shock) * 0.015))
    penalty_sensitivity = min(1.25, 0.85 + len(missed) / max(len(matches), 1) * 0.55)

    payload = {
        "summary": {
            "completed_forecasts": len(matches),
            "correct": len(correct),
            "missed": len(missed),
            "accuracy": accuracy,
            "mean_brier_score": metrics.get("mean_brier_score"),
            "mean_log_loss": metrics.get("mean_log_loss"),
        },
        "miss_patterns": {
            "misses_by_predicted_label": dict(by_predicted),
            "misses_by_actual_label": dict(by_actual),
            "severe_log_loss_match_ids": [row["match_id"] for row in severe],
            "shock_match_ids": [row["match_id"] for row in shock],
        },
        "learned_knockout_adjustments": {
            "uncertainty_multiplier": round(uncertainty_multiplier, 4),
            "favorite_shrink": round(favorite_shrink, 4),
            "upset_floor": round(upset_floor, 4),
            "penalty_sensitivity": round(penalty_sensitivity, 4),
            "target_accuracy_note": "90% is an ambition target, not a guaranteed property; the model now reports confidence and penalty risk instead of pretending certainty.",
        },
        "lessons": lessons,
        "source": "Derived from outputs/accuracy_report.json completed group-stage forecast audit.",
    }
    (OUTPUTS / "group_learning_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Learned from {len(matches)} completed matches: accuracy={accuracy:.3f}, misses={len(missed)}")


if __name__ == "__main__":
    main()
