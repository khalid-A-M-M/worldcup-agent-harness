from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from forecast_ledger import load_latest_pre_match_forecasts, load_latest_pre_match_knockout_predictions


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"
VERSIONS = OUTPUTS / "model_versions"
CALIBRATION = DATA / "model_calibration.json"
SYSTEM_START_UTC = "2026-06-23T00:00:00Z"


def main() -> None:
    actuals = _load_actuals()
    knockout_winners = _load_knockout_actual_winners()
    scored = []
    scored.extend(_score_group_forecasts(actuals))
    scored.extend(_score_knockout_forecasts(actuals, knockout_winners))
    scored.sort(key=lambda row: (row.get("kickoff_utc", ""), row.get("match_id", "")))

    metrics = _aggregate_metrics(scored)
    version_dir = _snapshot_version(scored, metrics)
    calibration = _load_calibration()
    updated = _update_calibration(calibration, metrics) if scored else calibration
    CALIBRATION.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUTPUTS / "accuracy_report.json").write_text(
        json.dumps({"system_start_utc": SYSTEM_START_UTC, "update_policy": "GitHub Actions checks every 20 minutes; completed matches are refreshed after kickoff + 110 minutes, which approximates 20 minutes after full time for open sources to publish results and stats.", "metrics": metrics, "matches": scored, "snapshot": _relative_snapshot_path(version_dir)}, ensure_ascii=False, indent=2),
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


def _relative_snapshot_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _score_group_forecasts(actuals: dict[str, dict[str, int]]) -> list[dict]:
    scored = []
    forecasts = load_latest_pre_match_forecasts()
    if not forecasts:
        forecasts = {
            path.stem.replace("forecast_", ""): json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(OUTPUTS.glob("forecast_WC-*.json"))
        }
    for forecast in forecasts.values():
        match_id = forecast["match"]["match_id"]
        if match_id not in actuals or not _forecast_is_in_system_window(forecast):
            continue
        final = forecast["agents"]["synthesizer"]["payload"]
        outcome = _actual_outcome(actuals[match_id]["home_goals"], actuals[match_id]["away_goals"])
        probs = {
            "home_win": float(final["home_win"]),
            "draw": float(final["draw"]),
            "away_win": float(final["away_win"]),
        }
        predicted = max(probs, key=probs.get)
        scored.append(_score_row(
            match_id=match_id,
            stage="group",
            home_team=forecast["match"]["home_team"],
            away_team=forecast["match"]["away_team"],
            predicted=predicted,
            actual=outcome,
            probs=probs,
            calibration_version=final.get("calibration_version", 1),
            forecast_created_at=forecast["match"].get("generated_at_utc"),
            kickoff_utc=forecast["match"].get("kickoff_utc"),
            model_family="Agent Harness group model",
        ))
    return scored


def _score_knockout_forecasts(actuals: dict[str, dict[str, int]], knockout_winners: dict[str, dict[str, str]]) -> list[dict]:
    fixtures = _load_knockout_fixtures()
    predictions = load_latest_pre_match_knockout_predictions(fixtures)
    scored = []
    for match_id, prediction in predictions.items():
        actual_id = _actual_id_for_match(match_id, actuals)
        if not actual_id:
            continue
        home_team = prediction.get("home_team", "")
        away_team = prediction.get("away_team", "")
        actual = _actual_knockout_outcome(
            actuals[actual_id]["home_goals"],
            actuals[actual_id]["away_goals"],
            home_team,
            away_team,
            knockout_winners.get(match_id) or knockout_winners.get(actual_id),
        )
        if actual is None:
            continue
        probs = {
            "home_win": float(prediction.get("home_advance_probability") or 0.5),
            "away_win": float(prediction.get("away_advance_probability") or 0.5),
        }
        total = max(sum(probs.values()), 1e-9)
        probs = {key: value / total for key, value in probs.items()}
        predicted = "home_win" if prediction.get("winner") == home_team else "away_win"
        fixture = fixtures.get(match_id, {})
        scored.append(_score_row(
            match_id=match_id,
            source_actual_match_id=actual_id,
            stage="knockout",
            round_name=prediction.get("round"),
            home_team=home_team,
            away_team=away_team,
            predicted=predicted,
            actual=actual,
            probs=probs,
            calibration_version=None,
            forecast_created_at=prediction.get("created_at_utc"),
            kickoff_utc=fixture.get("kickoff_utc"),
            model_family="Agent Harness knockout path model",
        ))
    return scored


def _score_row(match_id: str, stage: str, home_team: str, away_team: str, predicted: str, actual: str, probs: dict[str, float], calibration_version: int | None, forecast_created_at: str | None, kickoff_utc: str | None, model_family: str, source_actual_match_id: str | None = None, round_name: str | None = None) -> dict:
    labels = list(probs)
    probability_actual = probs.get(actual, 1e-9)
    return {
        "match_id": match_id,
        "source_actual_match_id": source_actual_match_id or match_id,
        "stage": stage,
        "round": round_name,
        "home_team": home_team,
        "away_team": away_team,
        "predicted": predicted,
        "actual": actual,
        "correct": predicted == actual,
        "probability_actual": probability_actual,
        "brier_score": sum((probs[k] - (1.0 if k == actual else 0.0)) ** 2 for k in labels),
        "log_loss": -math.log(max(probability_actual, 1e-9)),
        "calibration_version": calibration_version,
        "forecast_created_at": forecast_created_at,
        "kickoff_utc": kickoff_utc,
        "model_family": model_family,
    }


def _forecast_is_in_system_window(forecast: dict) -> bool:
    generated = forecast.get("match", {}).get("generated_at_utc") or forecast.get("generated_at_utc") or ""
    return not generated or generated >= SYSTEM_START_UTC


def _load_knockout_fixtures() -> dict[str, dict[str, str]]:
    path = DATA / "knockout_fixtures.csv"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as f:
        return {row["match_id"]: row for row in csv.DictReader(f)}


def _actual_id_for_match(match_id: str, actuals: dict[str, dict[str, int]]) -> str | None:
    if match_id in actuals:
        return match_id
    if match_id.startswith("KO-"):
        alias = "WC-" + match_id.split("-", 1)[1]
        if alias in actuals:
            return alias
    return None


def _actual_knockout_outcome(home_goals: int, away_goals: int, home_team: str, away_team: str, winner_row: dict[str, str] | None = None) -> str | None:
    if winner_row and winner_row.get("winner"):
        winner = winner_row["winner"]
        if winner == home_team:
            return "home_win"
        if winner == away_team:
            return "away_win"
    if home_goals > away_goals:
        return "home_win"
    if home_goals < away_goals:
        return "away_win"
    return None




def _load_knockout_actual_winners() -> dict[str, dict[str, str]]:
    path = DATA / "knockout_actual_winners.csv"
    if not path.exists():
        return {}
    winners: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("match_id"):
                winners[row["match_id"]] = row
            if row.get("source_actual_match_id"):
                winners[row["source_actual_match_id"]] = row
    return winners


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
            "group_completed_forecasts": 0,
            "knockout_completed_forecasts": 0,
            "correct": 0,
            "missed": 0,
        }
    return {
        "completed_forecasts": len(scored),
        "accuracy": sum(1 for row in scored if row["correct"]) / len(scored),
        "mean_brier_score": sum(row["brier_score"] for row in scored) / len(scored),
        "mean_log_loss": sum(row["log_loss"] for row in scored) / len(scored),
        "group_completed_forecasts": sum(1 for row in scored if row.get("stage") == "group"),
        "knockout_completed_forecasts": sum(1 for row in scored if row.get("stage") == "knockout"),
        "correct": sum(1 for row in scored if row["correct"]),
        "missed": sum(1 for row in scored if not row["correct"]),
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
    if (DATA / "time_series_forecast.json").exists():
        shutil.copy2(DATA / "time_series_forecast.json", version_dir / "time_series_forecast.json")
    (version_dir / "accuracy_report.json").write_text(
        json.dumps({"system_start_utc": SYSTEM_START_UTC, "metrics": metrics, "matches": scored}, ensure_ascii=False, indent=2),
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
