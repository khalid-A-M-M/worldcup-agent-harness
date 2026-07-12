from __future__ import annotations

import csv
import json
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={date}"
FIELDS = ["match_id", "home_team", "away_team", "kickoff_utc", "generated_at_utc", "group", "ground", "round", "stage"]


def fetch(day: date) -> dict:
    url = SCOREBOARD_URL.format(date=day.strftime("%Y%m%d"))
    request = urllib.request.Request(url, headers={"User-Agent": "football-agent-harness/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except OSError:
        if sys.platform != "win32":
            raise
        result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", f"Invoke-WebRequest -UseBasicParsing -Uri '{url}' | Select-Object -ExpandProperty Content"], capture_output=True, text=True)
        return json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else {}


def main() -> None:
    today = datetime.now(timezone.utc).date()
    days = [today + timedelta(days=offset) for offset in range(-2, 9)]
    registry = _read_rows(DATA / "all_group_fixtures.csv")
    all_rows = {row["match_id"]: row for row in registry}
    live_rows: dict[str, dict] = {}
    actuals = {row["match_id"]: row for row in _read_rows(DATA / "actual_results.csv")}
    for day in days:
        for event in fetch(day).get("events", []):
            competition = event["competitions"][0]
            competitors = competition["competitors"]
            if len(competitors) != 2:
                continue
            home = next(item for item in competitors if item["homeAway"] == "home")
            away = next(item for item in competitors if item["homeAway"] == "away")
            match_id = f"ESPN-{event['id']}"
            row = {
                "match_id": match_id,
                "home_team": home["team"]["displayName"],
                "away_team": away["team"]["displayName"],
                "kickoff_utc": event["date"],
                "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "group": "",
                "ground": competition.get("venue", {}).get("fullName", ""),
                "round": "Knockout",
                "stage": "knockout",
            }
            all_rows[match_id] = row
            live_rows[match_id] = row
            if competition["status"]["type"].get("completed"):
                actuals[match_id] = {"match_id": match_id, "home_goals": home.get("score", "0"), "away_goals": away.get("score", "0")}
    ordered = sorted(all_rows.values(), key=lambda row: row["kickoff_utc"])
    remaining = sorted(
        (row for match_id, row in live_rows.items() if match_id not in actuals),
        key=lambda row: row["kickoff_utc"],
    )
    if not live_rows:
        raise RuntimeError("ESPN returned no fixtures; existing dashboard data was preserved.")
    for path, rows in ((DATA / "all_group_fixtures.csv", ordered), (DATA / "fixtures.csv", remaining)):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    with (DATA / "actual_results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["match_id", "home_goals", "away_goals"])
        writer.writeheader()
        writer.writerows(actuals.values())
    print(f"ESPN live sync: {len(ordered)} fixtures, {len(actuals)} completed, {len(remaining)} remaining.")


def _read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    main()
