from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from forecast_ledger import load_latest_pre_match_forecasts


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"
VERSIONS = OUTPUTS / "model_versions"
CALIBRATION = DATA / "model_calibration.json"


def main() -> None:
    actuals = _load_actuals()
    scored = []
    forecasts = load_latest_pre_match_forecasts()
    if not forecasts:
        forecasts = {
            path.stem.replace("forecast_", ""): json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(OUTPUTS.glob("forecast_WC-*.json"))
        }
    for forecast in forecasts.values():
        match_id = forecast["match"]["match_id"]
        if match_id not in actuals:
            continue
        final = forecast["agents"]["synthesizer"]["payload"]
        outcome = _actual_outcome(actuals[match_id]["home_goals"], actuals[match_id]["away_goals"])
        probs = {
            "home_win": final["home_win"],
            "draw": final["draw"],
            "away_win": final["away_win"],
        }
        predicted = max(probs, key=probs.get)
        scored.append(
            {
                "match_id": match_id,
                "home_team": forecast["match"]["home_team"],
                "away_team": forecast["match"]["away_team"],
                "predicted": predicted,
                "actual": outcome,
                "correct": predicted == outcome,
                "probability_actual": probs[outcome],
                "brier_score": sum((probs[k] - (1.0 if k == outcome else 0.0)) ** 2 for k in probs),
                "log_loss": -math.log(max(probs[outcome], 1e-9)),
                "calibration_version": final.get("calibration_version", 1),
            }
        )

    metrics = _aggregate_metrics(scored)
    version_dir = _snapshot_version(scored, metrics)
    calibration = _load_calibration()
    updated = _update_calibration(calibration, metrics)
    CALIBRATION.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUTPUTS / "accuracy_report.json").write_text(
        json.dumps({"metrics": metrics, "matches": scored, "snapshot": str(version_dir)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    subprocess.run([sys.executable, str(ROOT / "learn_equation_parameters.py")], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "run_worldcup_batch.py")], cwd=ROOT, check=True)
    print(f"Scored {len(scored)} completed forecasts.")
    brier = "n/a" if metrics["mean_brier_score"] is None else f"{metrics['mean_brier_score']:.3f}"
    log_loss = "n/a" if metrics["mean_log_loss"] is None else f"{metrics['mean_log_loss']:.3f}"
    print(f"Accuracy: {metrics['accuracy']:.3f}, Brier: {brier}, LogLoss: {log_loss}")
    print(f"Saved model snapshot: {version_dir}")
    print(f"New calibration version: {updated['version']}")


def _load_actuals() -> dict[str, dict[str, int]]:
    actuals = {}
    with (DATA / "actual_results.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            actuals[row["match_id"]] = {
                "home_goals": int(row["home_goals"]),
                "away_goals": int(row["away_goals"]),
            }
    return actuals


def _actual_outcome(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home_win"
    if home_goals < away_goals:
        return "away_win"
    return "draw"


def _aggregate_metrics(scored: list[dict]) -> dict:
    if not scored:
        return {
            "completed_forecasts": 0,
            "accuracy": 0.0,
            "mean_brier_score": None,
            "mean_log_loss": None,
        }
    return {
        "completed_forecasts": len(scored),
        "accuracy": sum(1 for row in scored if row["correct"]) / len(scored),
        "mean_brier_score": sum(row["brier_score"] for row in scored) / len(scored),
        "mean_log_loss": sum(row["log_loss"] for row in scored) / len(scored),
    }


def _snapshot_version(scored: list[dict], metrics: dict) -> Path:
    VERSIONS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    calibration = _load_calibration()
    version_dir = VERSIONS / f"v{calibration.get('version', 1):03d}_{stamp}"
    version_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CALIBRATION, version_dir / "model_calibration.json")
    for path in sorted(OUTPUTS.glob("forecast_WC-*.json")):
        shutil.copy2(path, version_dir / path.name)
    if (OUTPUTS / "tournament_projection.json").exists():
        shutil.copy2(OUTPUTS / "tournament_projection.json", version_dir / "tournament_projection.json")
    if (DATA / "equation_learning.json").exists():
        shutil.copy2(DATA / "equation_learning.json", version_dir / "equation_learning.json")
    (version_dir / "accuracy_report.json").write_text(
        json.dumps({"metrics": metrics, "matches": scored}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return version_dir


def _load_calibration() -> dict:
    return json.loads(CALIBRATION.read_text(encoding="utf-8"))


def _update_calibration(calibration: dict, metrics: dict) -> dict:
    updated = dict(calibration)
    updated["version"] = int(updated.get("version", 1)) + 1
    if metrics["completed_forecasts"] < 3:
        updated.setdefault("notes", []).append("Not enough completed forecasts for aggressive recalibration.")
        return updated

    log_loss = metrics["mean_log_loss"] or 0.0
    accuracy = metrics["accuracy"]
    if log_loss > 1.15 or accuracy < 0.42:
        updated["team_adjustment_weight"] = max(0.75, updated.get("team_adjustment_weight", 1.0) * 0.94)
        updated["butterfly_adjustment_weight"] = max(0.7, updated.get("butterfly_adjustment_weight", 1.0) * 0.95)
        updated["confidence_penalty_weight"] = min(1.35, updated.get("confidence_penalty_weight", 1.0) * 1.05)
        updated.setdefault("notes", []).append("Reduced adjustment weights after weak completed-match accuracy.")
    else:
        updated["team_adjustment_weight"] = min(1.18, updated.get("team_adjustment_weight", 1.0) * 1.02)
        updated.setdefault("notes", []).append("Slightly reinforced team-intelligence layer after acceptable accuracy.")
    return updated


if __name__ == "__main__":
    main()
