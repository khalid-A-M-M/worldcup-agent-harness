from __future__ import annotations

import csv
import argparse
import json
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CACHE = DATA / "espn_cache"
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={date}"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event={event_id}"


ADVANCED_FIELDS = [
    "match_id",
    "team",
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
    "data_completeness",
    "source",
]


ESPN_TO_INTERNAL = {
    "Congo DR": "DR Congo",
    "Czechia": "Czech Republic",
    "United States": "USA",
    "Korea Republic": "South Korea",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch completed match results and team stats from ESPN.")
    parser.add_argument("--match-id", default=None, help="Limit refresh to one WC match id.")
    parser.add_argument("--date", default=None, help="Limit refresh to one UTC date YYYYMMDD.")
    args = parser.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    registry = DATA / "all_group_fixtures.csv"
    fixtures = _read_csv(registry if registry.exists() else DATA / "fixtures.csv")
    if args.match_id:
        fixtures = [row for row in fixtures if row["match_id"] == args.match_id]
    if args.date:
        fixtures = [
            row
            for row in fixtures
            if datetime.fromisoformat(row["kickoff_utc"].replace("Z", "+00:00")).strftime("%Y%m%d") == args.date
        ]
    actuals = _read_actual_results()
    advanced_rows = _read_advanced_rows()

    updated_results = 0
    updated_stats = 0
    for fixture in fixtures:
        date_key = datetime.fromisoformat(fixture["kickoff_utc"].replace("Z", "+00:00")).strftime("%Y%m%d")
        try:
            scoreboard = _load_json_from_url(SCOREBOARD_URL.format(date=date_key), CACHE / f"scoreboard_{date_key}.json")
        except Exception as exc:
            print(f"Skipping ESPN scoreboard for {date_key}: {exc}")
            continue
        event = _find_event(scoreboard, fixture["home_team"], fixture["away_team"])
        if not event:
            continue
        competition = event["competitions"][0]
        status = competition["status"]["type"]
        if not status.get("completed"):
            continue
        event_id = event["id"]
        scores = _scores_from_event(event, fixture["home_team"], fixture["away_team"])
        if scores and fixture["match_id"] not in actuals:
            actuals[fixture["match_id"]] = scores
            updated_results += 1

        try:
            summary = _load_json_from_url(SUMMARY_URL.format(event_id=event_id), CACHE / f"summary_{event_id}.json")
        except Exception as exc:
            print(f"Skipping ESPN summary for {event_id}: {exc}")
            continue
        rows = _stats_from_summary(fixture["match_id"], summary)
        for row in rows:
            key = (row["match_id"], row["team"])
            if key not in advanced_rows:
                advanced_rows[key] = row
                updated_stats += 1
            elif advanced_rows[key].get("source") == row.get("source"):
                advanced_rows[key] = {**advanced_rows[key], **row}

    _write_actual_results(actuals)
    _write_advanced_rows(advanced_rows)
    print(f"ESPN refresh complete: {updated_results} result(s), {updated_stats} team-stat row(s) added.")


def _load_json_from_url(url: str, path: Path) -> dict:
    try:
        _download(url, path)
    except Exception as exc:
        legacy_candidates = [DATA / path.name, DATA / f"espn_{path.name}"]
        for legacy_path in legacy_candidates:
            if legacy_path.exists() and not path.exists():
                path.write_text(legacy_path.read_text(encoding="utf-8"), encoding="utf-8")
                break
        if not path.exists():
            raise
        print(f"Using cached ESPN file after download failure: {path.name} ({exc})")
    return json.loads(path.read_text(encoding="utf-8"))


def _download(url: str, path: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 football-agent-harness/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            path.write_bytes(response.read())
        return
    except Exception:
        if sys.platform != "win32":
            raise

    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        f"Invoke-WebRequest -UseBasicParsing -Uri '{url}' -OutFile '{path}'",
    ]
    subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _find_event(scoreboard: dict, team1: str, team2: str) -> dict | None:
    wanted = {_normalize_team(team1), _normalize_team(team2)}
    for event in scoreboard.get("events", []):
        competitors = event.get("competitions", [{}])[0].get("competitors", [])
        names = {_normalize_team(c["team"]["displayName"]) for c in competitors}
        if wanted == names:
            return event
    return None


def _scores_from_event(event: dict, team1: str, team2: str) -> dict[str, int] | None:
    scores = {}
    for competitor in event["competitions"][0]["competitors"]:
        scores[_normalize_team(competitor["team"]["displayName"])] = int(competitor["score"])
    home = _normalize_team(team1)
    away = _normalize_team(team2)
    if home in scores and away in scores:
        return {"home_goals": scores[home], "away_goals": scores[away]}
    return None


def _stats_from_summary(match_id: str, summary: dict) -> list[dict]:
    rows = []
    raw_rows = []
    for item in summary.get("boxscore", {}).get("teams", []):
        team = _normalize_team(item["team"]["displayName"])
        stats = {stat["name"]: _to_number(stat.get("displayValue")) for stat in item.get("statistics", [])}
        raw_rows.append((team, stats))
    dominance = _dominance_indices(raw_rows)
    for team, stats in raw_rows:
        rows.append(
            {
                "match_id": match_id,
                "team": team,
                "shots": stats.get("totalShots", 0),
                "shots_on_target": stats.get("shotsOnTarget", 0),
                "possession": stats.get("possessionPct", 0),
                "xg": "",
                "big_chances": "",
                "corners": stats.get("wonCorners", 0),
                "yellow_cards": stats.get("yellowCards", 0),
                "red_cards": stats.get("redCards", 0),
                "passes_into_final_third": "",
                "fouls": stats.get("foulsCommitted", 0),
                "offsides": stats.get("offsides", 0),
                "saves": stats.get("saves", 0),
                "accurate_passes": stats.get("accuratePasses", 0),
                "total_passes": stats.get("totalPasses", 0),
                "pass_pct": stats.get("passPct", 0),
                "accurate_crosses": stats.get("accurateCrosses", 0),
                "total_crosses": stats.get("totalCrosses", 0),
                "blocked_shots": stats.get("blockedShots", 0),
                "total_tackles": stats.get("totalTackles", 0),
                "interceptions": stats.get("interceptions", 0),
                "clearances": stats.get("totalClearance", 0),
                "match_momentum": "",
                "momentum_last_15": "",
                "dominance_index": dominance.get(team, {}).get("dominance_index", 0),
                "attacking_pressure_index": dominance.get(team, {}).get("attacking_pressure_index", 0),
                "data_completeness": "partial_no_timeline_momentum_no_xg",
                "source": "ESPN",
            }
        )
    return rows


def _dominance_indices(raw_rows: list[tuple[str, dict]]) -> dict[str, dict[str, float]]:
    if len(raw_rows) != 2:
        return {}
    totals = {}
    for _, stats in raw_rows:
        totals["shots"] = totals.get("shots", 0) + stats.get("totalShots", 0)
        totals["sot"] = totals.get("sot", 0) + stats.get("shotsOnTarget", 0)
        totals["corners"] = totals.get("corners", 0) + stats.get("wonCorners", 0)
        totals["passes"] = totals.get("passes", 0) + stats.get("totalPasses", 0)
    output = {}
    for team, stats in raw_rows:
        shot_share = _share(stats.get("totalShots", 0), totals["shots"])
        sot_share = _share(stats.get("shotsOnTarget", 0), totals["sot"])
        corner_share = _share(stats.get("wonCorners", 0), totals["corners"])
        pass_share = _share(stats.get("totalPasses", 0), totals["passes"])
        possession = stats.get("possessionPct", 50) / 100
        attacking_pressure = 100 * (0.45 * sot_share + 0.25 * shot_share + 0.2 * corner_share + 0.1 * possession)
        dominance = 100 * (0.35 * possession + 0.25 * pass_share + 0.2 * shot_share + 0.2 * sot_share)
        output[team] = {
            "dominance_index": round(dominance, 2),
            "attacking_pressure_index": round(attacking_pressure, 2),
        }
    return output


def _share(value: float, total: float) -> float:
    if not total:
        return 0.5
    return value / total


def _normalize_team(team: str) -> str:
    return ESPN_TO_INTERNAL.get(team, team)


def _to_number(value) -> float:
    if value is None:
        return 0.0
    text = str(value).replace("%", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _read_actual_results() -> dict[str, dict[str, int]]:
    rows = {}
    path = DATA / "actual_results.csv"
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rows[row["match_id"]] = {"home_goals": int(row["home_goals"]), "away_goals": int(row["away_goals"])}
    return rows


def _write_actual_results(rows: dict[str, dict[str, int]]) -> None:
    with (DATA / "actual_results.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["match_id", "home_goals", "away_goals"])
        writer.writeheader()
        for match_id, row in sorted(rows.items()):
            writer.writerow({"match_id": match_id, **row})


def _read_advanced_rows() -> dict[tuple[str, str], dict]:
    path = DATA / "match_advanced_stats.csv"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as f:
        return {(row["match_id"], row["team"]): row for row in csv.DictReader(f)}


def _write_advanced_rows(rows: dict[tuple[str, str], dict]) -> None:
    with (DATA / "match_advanced_stats.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ADVANCED_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for _, row in sorted(rows.items()):
            writer.writerow(row)


if __name__ == "__main__":
    main()
