from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SOURCE = DATA / "worldcup_2026_openfootball.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert World Cup JSON into Agent Harness CSV inputs.")
    parser.add_argument("--source", default=str(SOURCE), help="Path to openfootball worldcup JSON.")
    parser.add_argument("--from-date", default=None, help="First fixture date to forecast.")
    parser.add_argument("--to-date", default=None, help="Last fixture date to forecast.")
    parser.add_argument(
        "--scope",
        choices=["date-window", "remaining-groups", "all-remaining"],
        default="remaining-groups",
        help="Fixture scope to export.",
    )
    args = parser.parse_args()

    source = Path(args.source)
    data = json.loads(source.read_text(encoding="utf-8"))
    matches = data["matches"]
    from_date = datetime.fromisoformat(args.from_date).date() if args.from_date else None
    to_date = datetime.fromisoformat(args.to_date).date() if args.to_date else None
    generated_at = datetime.now(timezone.utc)

    completed = [m for m in matches if "score" in m and "ft" in m["score"]]
    all_group_fixtures = [(idx, match) for idx, match in enumerate(matches, start=1) if match.get("group")]
    forecast_fixtures = []
    for idx, match in enumerate(matches, start=1):
        if "score" in match:
            continue
        match_date = datetime.fromisoformat(match["date"]).date()
        if args.scope == "remaining-groups" and not match.get("group"):
            continue
        if args.scope == "date-window":
            if from_date and match_date < from_date:
                continue
            if to_date and match_date > to_date:
                continue
        forecast_fixtures.append((idx, match))

    _write_csv(
        DATA / "historical_results.csv",
        ["date", "home_team", "away_team", "home_goals", "away_goals", "match_type"],
        [
            {
                "date": m["date"],
                "home_team": m["team1"],
                "away_team": m["team2"],
                "home_goals": m["score"]["ft"][0],
                "away_goals": m["score"]["ft"][1],
                "match_type": "wc_2026",
            }
            for m in completed
        ],
    )

    _write_csv(
        DATA / "all_group_fixtures.csv",
        ["match_id", "home_team", "away_team", "kickoff_utc", "generated_at_utc", "group", "ground", "round", "stage"],
        [
            {
                "match_id": f"WC-{idx:03d}",
                "home_team": m["team1"],
                "away_team": m["team2"],
                "kickoff_utc": _kickoff_utc(m).isoformat().replace("+00:00", "Z"),
                "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
                "group": m.get("group", ""),
                "ground": m.get("ground", ""),
                "round": m.get("round", ""),
                "stage": _stage(m),
            }
            for idx, m in all_group_fixtures
        ],
    )

    _write_csv(
        DATA / "fixtures.csv",
        ["match_id", "home_team", "away_team", "kickoff_utc", "generated_at_utc", "group", "ground", "round", "stage"],
        [
            {
                "match_id": f"WC-{idx:03d}",
                "home_team": m["team1"],
                "away_team": m["team2"],
                "kickoff_utc": _kickoff_utc(m).isoformat().replace("+00:00", "Z"),
                "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
                "group": m.get("group", ""),
                "ground": m.get("ground", ""),
                "round": m.get("round", ""),
                "stage": _stage(m),
            }
            for idx, m in forecast_fixtures
        ],
    )

    actual_rows = _existing_actual_results()
    for idx, match in enumerate(matches, start=1):
        if match.get("group") and "score" in match and "ft" in match["score"]:
            actual_rows[f"WC-{idx:03d}"] = {
                "match_id": f"WC-{idx:03d}",
                "home_goals": match["score"]["ft"][0],
                "away_goals": match["score"]["ft"][1],
            }
    _write_csv(DATA / "actual_results.csv", ["match_id", "home_goals", "away_goals"], list(actual_rows.values()))

    _write_csv(
        DATA / "butterfly_events.csv",
        ["match_id", "event_time_utc", "event_type", "description", "impact", "confidence", "benefits"],
        _butterfly_rows(forecast_fixtures, generated_at),
    )

    print(f"Converted {len(completed)} completed World Cup matches.")
    print(f"Prepared {len(forecast_fixtures)} forecast fixtures with scope={args.scope}.")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _existing_actual_results() -> dict[str, dict]:
    path = DATA / "actual_results.csv"
    if not path.exists():
        return {}
    rows = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rows[row["match_id"]] = row
    return rows


def _kickoff_utc(match: dict) -> datetime:
    local_time, offset = match["time"].split(" UTC")
    hours, minutes = [int(part) for part in local_time.split(":")]
    offset_hours = int(offset)
    local_dt = datetime.fromisoformat(match["date"]).replace(hour=hours, minute=minutes)
    return (local_dt - timedelta(hours=offset_hours)).replace(tzinfo=timezone.utc)


def _stage(match: dict) -> str:
    if match.get("group"):
        return "group"
    return "knockout"


def _butterfly_rows(fixtures: list[tuple[int, dict]], generated_at: datetime) -> list[dict]:
    rows = []
    for idx, match in fixtures:
        home = match["team1"]
        away = match["team2"]
        match_id = f"WC-{idx:03d}"
        if home in {"England", "Portugal", "Brazil", "France", "Argentina"}:
            rows.append(_event(match_id, generated_at, "favorite_pressure", f"{home} carries heavy favorite pressure in a decisive group fixture.", "medium", "medium", "against_home"))
        if away in {"England", "Portugal", "Brazil", "France", "Argentina"}:
            rows.append(_event(match_id, generated_at, "favorite_pressure", f"{away} carries heavy favorite pressure in a decisive group fixture.", "medium", "medium", "against_away"))
        if match.get("ground") in {"Mexico City", "Guadalajara (Zapopan)", "Monterrey (Guadalupe)"}:
            rows.append(_event(match_id, generated_at, "altitude_heat_context", "Mexico venue context may increase fatigue variance.", "medium", "low", "against_away"))
    return rows


def _event(match_id: str, generated_at: datetime, event_type: str, description: str, impact: str, confidence: str, benefits: str) -> dict:
    return {
        "match_id": match_id,
        "event_time_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "event_type": event_type,
        "description": description,
        "impact": impact,
        "confidence": confidence,
        "benefits": benefits,
    }


if __name__ == "__main__":
    main()
