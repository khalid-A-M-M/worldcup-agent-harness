from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
LEDGER = OUTPUTS / "forecast_ledger"
INDEX_PATH = LEDGER / "index.json"
KNOCKOUT_LEDGER = OUTPUTS / "knockout_ledger"
KNOCKOUT_INDEX_PATH = KNOCKOUT_LEDGER / "index.json"


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



def archive_knockout_predictions(bracket_path: Path) -> Path:
    bracket = json.loads(bracket_path.read_text(encoding="utf-8"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    KNOCKOUT_LEDGER.mkdir(parents=True, exist_ok=True)
    target = KNOCKOUT_LEDGER / f"knockout_{stamp}.json"
    shutil.copy2(bracket_path, target)

    index = _load_knockout_index()
    entries = index.setdefault("entries", [])
    official_matches = []
    for round_item in bracket.get("rounds", []):
        for match in round_item.get("matches", []):
            official_matches.append(match)
            entries.append(
                {
                    "match_id": match.get("match_id"),
                    "home_team": match.get("home_team"),
                    "away_team": match.get("away_team"),
                    "winner": match.get("winner"),
                    "home_advance_probability": match.get("home_advance_probability"),
                    "away_advance_probability": match.get("away_advance_probability"),
                    "round": match.get("round"),
                    "scenario_id": "B",
                    "created_at_utc": _created_at_for_knockout_match(match, stamp),
                    "archived_at_utc": stamp,
                    "kickoff_utc": match.get("kickoff_utc"),
                    "path": str(target.relative_to(ROOT)).replace("\\", "/"),
                }
            )
    KNOCKOUT_INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_latest_pre_match_knockout_predictions(fixtures: dict[str, dict]) -> dict[str, dict]:
    index = _load_knockout_index()
    latest: dict[str, dict] = {}
    for entry in index.get("entries", []):
        match_id = entry.get("match_id", "")
        fixture = fixtures.get(match_id)
        if not fixture:
            continue
        kickoff = fixture.get("kickoff_utc", "")
        created_at = entry.get("created_at_utc", "")
        if kickoff and _to_utc_datetime(created_at) >= _to_utc_datetime(kickoff):
            continue
        current = latest.get(match_id)
        if current is None or _to_utc_datetime(created_at) > _to_utc_datetime(current.get("created_at_utc", "")):
            latest[match_id] = entry
    return latest




def _created_at_for_knockout_match(match: dict, fallback_stamp: str) -> str:
    generated = match.get("generated_at_utc")
    if generated:
        return _normalize_created_at(generated)
    return fallback_stamp


def _normalize_created_at(value: str) -> str:
    parsed = _to_utc_datetime(value)
    if parsed == datetime.min.replace(tzinfo=timezone.utc):
        return value
    return parsed.isoformat().replace("+00:00", "Z")


def _to_utc_datetime(value: str) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        if "T" in value and (value.endswith("Z") or "+" in value):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def _load_knockout_index() -> dict:
    if not KNOCKOUT_INDEX_PATH.exists():
        return {"entries": []}
    return json.loads(KNOCKOUT_INDEX_PATH.read_text(encoding="utf-8"))


def _stamp_to_iso(stamp: str) -> str:
    if not stamp:
        return ""
    try:
        parsed = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return parsed.isoformat().replace("+00:00", "Z")
    except ValueError:
        return stamp
