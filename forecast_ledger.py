from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
LEDGER = OUTPUTS / "forecast_ledger"
INDEX_PATH = LEDGER / "index.json"


def archive_forecast(forecast_path: Path) -> Path:
    forecast = json.loads(forecast_path.read_text(encoding="utf-8"))
    match_id = forecast["match"]["match_id"]
    version = forecast["agents"]["synthesizer"]["payload"].get("calibration_version", 1)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    LEDGER.mkdir(parents=True, exist_ok=True)
    target = LEDGER / f"{match_id}_v{int(version):03d}_{stamp}.json"
    shutil.copy2(forecast_path, target)

    index = _load_index()
    entries = index.setdefault("entries", [])
    entries.append(
        {
            "match_id": match_id,
            "home_team": forecast["match"]["home_team"],
            "away_team": forecast["match"]["away_team"],
            "calibration_version": int(version),
            "created_at_utc": stamp,
            "path": str(target.relative_to(ROOT)).replace("\\", "/"),
        }
    )
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_latest_pre_match_forecasts() -> dict[str, dict]:
    index = _load_index()
    latest: dict[str, dict] = {}
    for entry in index.get("entries", []):
        match_id = entry["match_id"]
        current = latest.get(match_id)
        if current is None or entry["created_at_utc"] > current["created_at_utc"]:
            forecast_path = ROOT / entry["path"]
            if forecast_path.exists():
                latest[match_id] = {
                    "created_at_utc": entry["created_at_utc"],
                    "forecast": json.loads(forecast_path.read_text(encoding="utf-8")),
                }
    for forecast_path in _discover_forecast_files():
        forecast = json.loads(forecast_path.read_text(encoding="utf-8"))
        match_id = forecast["match"]["match_id"]
        stamp = _file_stamp(forecast_path)
        current = latest.get(match_id)
        if current is None or stamp > current["created_at_utc"]:
            latest[match_id] = {"created_at_utc": stamp, "forecast": forecast}
    return {match_id: payload["forecast"] for match_id, payload in latest.items()}


def _load_index() -> dict:
    if not INDEX_PATH.exists():
        return {"entries": []}
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def _discover_forecast_files() -> list[Path]:
    files = list(OUTPUTS.glob("forecast_WC-*.json"))
    versions = OUTPUTS / "model_versions"
    if versions.exists():
        files.extend(versions.glob("v*/forecast_WC-*.json"))
    return sorted(files)


def _file_stamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
