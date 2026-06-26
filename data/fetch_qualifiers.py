"""Fetch open World Cup qualifier results and merge them into historical_results.csv.

The script is intentionally conservative: failed remote sources do not alter existing data.
"""
from __future__ import annotations

import csv
import json
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
HIST_PATH = ROOT / "data" / "historical_results.csv"

QUALIFIER_SOURCES = [
    {
        "url": "https://raw.githubusercontent.com/openfootball/south-america.json/master/2026/worldcup-qualifying.json",
        "match_type": "qualifier",
        "label": "CONMEBOL",
    },
    {
        "url": "https://raw.githubusercontent.com/openfootball/world.json/master/2025/qualifiers.json",
        "match_type": "qualifier",
        "label": "FIFA qualifiers",
    },
]


def _fetch_json(url: str) -> Any | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "worldcup-agent-harness/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"Warning: failed to fetch {url}: {exc}")
        return None


def _extract_matches(data: Any, match_type: str) -> list[dict[str, str]]:
    if isinstance(data, dict):
        items = data.get("rounds") or data.get("matches") or []
    elif isinstance(data, list):
        items = data
    else:
        return []
    matches = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for match in item.get("matches", [item]):
            if not isinstance(match, dict):
                continue
            score = match.get("score") or {}
            ft = score.get("ft") or score.get("fulltime") or [None, None]
            if len(ft) < 2 or ft[0] is None or ft[1] is None:
                continue
            home = match.get("team1") or match.get("home_team") or ""
            away = match.get("team2") or match.get("away_team") or ""
            date = match.get("date") or ""
            if date and home and away:
                matches.append({
                    "date": date[:10],
                    "home_team": home,
                    "away_team": away,
                    "home_goals": str(ft[0]),
                    "away_goals": str(ft[1]),
                    "match_type": match_type,
                })
    return matches


def _load_existing() -> tuple[list[dict[str, str]], list[str], set[tuple[str, str, str]]]:
    rows = []
    existing = set()
    if HIST_PATH.exists():
        with HIST_PATH.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            for row in reader:
                if not row.get("match_type"):
                    row["match_type"] = "wc_2026"
                rows.append(row)
                existing.add((row.get("date", ""), row.get("home_team", ""), row.get("away_team", "")))
    else:
        fieldnames = ["date", "home_team", "away_team", "home_goals", "away_goals", "match_type"]
    if "match_type" not in fieldnames:
        fieldnames.append("match_type")
    return rows, fieldnames, existing


def merge_and_save(new_matches: list[dict[str, str]]) -> int:
    rows, fieldnames, existing = _load_existing()
    added = 0
    for match in new_matches:
        key = (match["date"], match["home_team"], match["away_team"])
        if key not in existing:
            rows.append(match)
            existing.add(key)
            added += 1
    rows.sort(key=lambda row: (row.get("date", ""), row.get("home_team", ""), row.get("away_team", "")))
    with HIST_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return added


def main() -> None:
    all_matches = []
    for source in QUALIFIER_SOURCES:
        print(f"Fetching {source['label']}")
        data = _fetch_json(source["url"])
        if data is not None:
            all_matches.extend(_extract_matches(data, source["match_type"]))
    if not all_matches:
        print("No qualifier matches fetched; historical_results.csv unchanged.")
        return
    print(f"Added {merge_and_save(all_matches)} new qualifier matches from {len(all_matches)} fetched rows.")


if __name__ == "__main__":
    main()
