from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"
STATE_PATH = OUTPUTS / "match_monitor_state.json"
LOG_PATH = OUTPUTS / "match_monitor.log"


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor due World Cup matches and trigger model evolution.")
    parser.add_argument("--poll-seconds", type=int, default=300, help="Loop polling interval.")
    parser.add_argument("--final-whistle-buffer", type=int, default=110, help="Minutes after kickoff before first result/stat check.")
    parser.add_argument("--once", action="store_true", help="Run one due-match check and exit.")
    args = parser.parse_args()

    while True:
        due = _due_matches(args.final_whistle_buffer)
        if due:
            _run_update(due)
        else:
            _log("No completed-match checks are due.")
        if args.once:
            return
        time.sleep(args.poll_seconds)


def _due_matches(buffer_minutes: int) -> list[dict]:
    fixtures = []
    for fixtures_path in (DATA / "all_group_fixtures.csv", DATA / "fixtures.csv", DATA / "knockout_fixtures.csv"):
        if fixtures_path.exists():
            fixtures.extend(_read_csv(fixtures_path))
    state = _load_state()
    checked = set(state.get("checked_match_ids", []))
    # last_checked_at: وقت آخر محاولة لكل مباراة، لإعادة المحاولة بعد 6 ساعات
    last_checked_at: dict[str, str] = state.get("last_checked_at", {})
    actuals = _load_actual_match_ids()
    now = datetime.now(timezone.utc)
    retry_hours = 6
    due = []
    for row in fixtures:
        match_id = row["match_id"]
        if match_id in actuals:
            # النتيجة موجودة فعلاً — لا حاجة لإعادة المحاولة
            continue
        if not row.get("kickoff_utc"):
            continue
        kickoff = datetime.fromisoformat(row["kickoff_utc"].replace("Z", "+00:00")).astimezone(timezone.utc)
        if now < kickoff + timedelta(minutes=buffer_minutes):
            # المباراة لم تنته بعد
            continue
        if match_id in checked:
            # سبق المحاولة — نعيد فقط إذا مرّ retry_hours ساعة منذ آخر محاولة
            last = last_checked_at.get(match_id)
            if last:
                last_dt = datetime.fromisoformat(last).astimezone(timezone.utc)
                if now - last_dt < timedelta(hours=retry_hours):
                    continue
            _log(f"Retrying result fetch for {match_id} (in checked but no actual result yet).")
        due.append(row)
    return due


def _run_update(due: list[dict]) -> None:
    _log(f"{len(due)} match(es) are due for result/stat refresh:")
    for row in due:
        _log(f"- {row['match_id']}: {row['home_team']} vs {row['away_team']}")
        subprocess.run(
            [sys.executable, str(ROOT / "fetch_espn_match_stats.py"), "--match-id", row["match_id"]],
            cwd=ROOT,
            check=False,
        )
    subprocess.run([sys.executable, str(ROOT / "update_worldcup_results.py")], cwd=ROOT, check=True)
    state = _load_state()
    checked = set(state.get("checked_match_ids", []))
    last_checked_at: dict[str, str] = state.get("last_checked_at", {})
    actuals = _load_actual_match_ids()
    now_iso = datetime.now(timezone.utc).isoformat()
    completed_due = [row for row in due if row["match_id"] in actuals]
    pending_due   = [row for row in due if row["match_id"] not in actuals]
    # فقط المباريات التي اكتملت فعلاً تُضاف إلى checked
    checked.update(row["match_id"] for row in completed_due)
    # تسجيل وقت آخر محاولة لكل مباراة (سواء نجحت أم لا)
    for row in due:
        last_checked_at[row["match_id"]] = now_iso
    for row in completed_due:
        _log(f"Completed update confirmed for {row['match_id']}.")
    for row in pending_due:
        _log(f"Result not available yet for {row['match_id']}; will retry in 6h.")
    state["checked_match_ids"] = sorted(checked)
    state["last_checked_at"] = last_checked_at
    state["last_update_utc"] = now_iso
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _log(message: str) -> None:
    OUTPUTS.mkdir(exist_ok=True)
    line = f"{datetime.now(timezone.utc).isoformat()} {message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _read_csv(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {"checked_match_ids": []}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def _load_actual_match_ids() -> set[str]:
    import csv

    path = DATA / "actual_results.csv"
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8", newline="") as f:
        return {row["match_id"] for row in csv.DictReader(f)}


if __name__ == "__main__":
    main()
