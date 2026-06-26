"""Fetch international Elo ratings and refresh team_seed_ranks.csv.

The script uses only Python stdlib. If the remote source is unavailable,
it keeps the existing file untouched.
"""
from __future__ import annotations

import csv
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "team_seed_ranks.csv"

ELO_URLS = [
    "http://api.eloratings.net/World_Cup_2026.tsv",
    "http://api.eloratings.net/all.tsv",
]

WC2026_TEAMS = {
    "Argentina", "France", "England", "Spain", "Brazil", "Portugal", "Netherlands",
    "Belgium", "Germany", "Croatia", "Uruguay", "Colombia", "USA", "Switzerland",
    "Morocco", "Mexico", "Japan", "Senegal", "Iran", "Austria", "South Korea",
    "Australia", "Turkey", "Ecuador", "Qatar", "Ivory Coast", "Algeria", "Canada",
    "Scotland", "Norway", "Egypt", "Ghana", "Tunisia", "Panama", "Cape Verde",
    "Saudi Arabia", "DR Congo", "South Africa", "Czech Republic", "Bosnia & Herzegovina",
    "Haiti", "New Zealand", "Uzbekistan", "Paraguay", "Iraq", "Jordan", "Cura?ao",
}

ALIASES = {
    "United States": "USA",
    "Czechia": "Czech Republic",
    "Congo DR": "DR Congo",
    "Congo-Kinshasa": "DR Congo",
    "Curacao": "Cura?ao",
}


def _fetch_tsv(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "worldcup-agent-harness/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _parse_elo_tsv(content: str) -> list[dict[str, float | str]]:
    rows = []
    for line in content.strip().splitlines()[1:]:
        parts = line.split("	")
        if len(parts) < 3:
            continue
        team = parts[1].strip()
        try:
            elo = float(parts[2].strip())
        except ValueError:
            continue
        rows.append({"team": team, "elo_rating": elo})
    return rows


def _match_wc_team(name: str) -> str | None:
    if name in ALIASES:
        return ALIASES[name]
    low = name.lower()
    for team in WC2026_TEAMS:
        if low == team.lower() or low in team.lower() or team.lower() in low:
            return team
    return None


def fetch_and_save(output_path: Path = OUTPUT) -> bool:
    rows = []
    for url in ELO_URLS:
        try:
            print(f"Fetching Elo data from {url}")
            rows = _parse_elo_tsv(_fetch_tsv(url))
            if rows:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"Warning: Elo fetch failed from {url}: {exc}")
    if not rows:
        print("No Elo data fetched; keeping existing team_seed_ranks.csv")
        return False

    wc_rows = []
    seen = set()
    for row in rows:
        matched = _match_wc_team(str(row["team"]))
        if matched and matched not in seen:
            wc_rows.append({"team": matched, "elo_rating": float(row["elo_rating"])})
            seen.add(matched)
    if len(wc_rows) < 30:
        print(f"Only matched {len(wc_rows)} World Cup teams; keeping existing file.")
        return False

    wc_rows.sort(key=lambda item: item["elo_rating"], reverse=True)
    for index, row in enumerate(wc_rows, 1):
        row["seed_rank"] = index

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["team", "seed_rank", "elo_rating"])
        writer.writeheader()
        writer.writerows(wc_rows)
    print(f"Saved {len(wc_rows)} Elo priors to {output_path}")
    return True


if __name__ == "__main__":
    fetch_and_save()
