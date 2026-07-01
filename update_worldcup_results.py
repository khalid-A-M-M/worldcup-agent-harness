from __future__ import annotations

import subprocess
import sys
import time
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlretrieve


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SOURCE_URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"


def main() -> None:
    target = DATA / "worldcup_2026_openfootball.json"
    fallback = DATA / "worldcup_2026_openfootball_latest_check.json"
    print(f"Downloading latest World Cup data from {SOURCE_URL}")
    try:
        _download_with_retry(target)
    except URLError as exc:
        if fallback.exists():
            print(f"Download failed ({exc}); using latest checked local source: {fallback.name}")
            target.write_text(fallback.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            raise
    subprocess.run(
        [sys.executable, str(ROOT / "import_worldcup_data.py"), "--scope", "remaining-groups"],
        cwd=ROOT,
        check=True,
    )
    _refresh_due_espn_matches()
    subprocess.run([sys.executable, str(ROOT / "evolve_after_results.py")], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "predict_knockout_bracket.py")], cwd=ROOT, check=True)
    print("Dashboard data refreshed.")


def _download_with_retry(target: Path, attempts: int = 3) -> None:
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            urlretrieve(SOURCE_URL, target)
            return
        except URLError as exc:
            last_error = exc
            print(f"Download attempt {attempt}/{attempts} failed: {exc}")
            time.sleep(2 * attempt)
    if last_error:
        raise last_error


def _refresh_due_espn_matches(buffer_minutes: int = 110, stats_lookback_hours: int = 36) -> None:
    fixtures_paths = [DATA / "all_group_fixtures.csv", DATA / "knockout_fixtures.csv"]
    fixtures = []
    for fixtures_path in fixtures_paths:
        if fixtures_path.exists():
            with fixtures_path.open("r", encoding="utf-8", newline="") as f:
                fixtures.extend(csv.DictReader(f))
    if not fixtures:
        return
    now = datetime.now(timezone.utc)
    actuals = _load_actual_match_ids()
    stats = _load_advanced_stat_match_ids()
    due = []
    seen = set()
    for row in fixtures:
        match_id = row.get("match_id", "")
        if not match_id or match_id in seen:
            continue
        seen.add(match_id)
        kickoff_raw = row.get("kickoff_utc")
        if not kickoff_raw:
            continue
        kickoff = datetime.fromisoformat(kickoff_raw.replace("Z", "+00:00")).astimezone(timezone.utc)
        needs_result = match_id not in actuals
        recently_finished = now - kickoff <= timedelta(hours=stats_lookback_hours)
        needs_stats = match_id not in stats and recently_finished
        if now >= kickoff + timedelta(minutes=buffer_minutes) and (needs_result or needs_stats):
            due.append(match_id)
    if not due:
        print("No due ESPN result/stat refresh needed.")
        return
    print(f"Refreshing ESPN result/stat data for {len(due)} due match(es): {', '.join(due)}")
    for match_id in due:
        subprocess.run(
            [sys.executable, str(ROOT / "fetch_espn_match_stats.py"), "--match-id", match_id],
            cwd=ROOT,
            check=False,
        )


def _load_actual_match_ids() -> set[str]:
    path = DATA / "actual_results.csv"
    if not path.exists():
        return set()
    ids: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            match_id = row["match_id"]
            ids.add(match_id)
            if match_id.startswith("WC-"):
                ids.add("KO-" + match_id.split("-", 1)[1])
            elif match_id.startswith("KO-"):
                ids.add("WC-" + match_id.split("-", 1)[1])
    return ids


def _load_advanced_stat_match_ids() -> set[str]:
    path = DATA / "match_advanced_stats.csv"
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8", newline="") as f:
        counts = {}
        for row in csv.DictReader(f):
            counts[row["match_id"]] = counts.get(row["match_id"], 0) + 1
    return {match_id for match_id, count in counts.items() if count >= 2}


if __name__ == "__main__":
    main()
