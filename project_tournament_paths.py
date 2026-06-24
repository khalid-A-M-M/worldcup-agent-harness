from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"


def main() -> None:
    fixtures = _read_csv(DATA / "fixtures.csv")
    visuals = {row["team"]: row for row in _read_csv(DATA / "team_visuals.csv")}
    completed = _completed_matches_by_group()
    forecasts = _load_forecasts(fixtures)
    groups = sorted({row["group"] for row in fixtures if row.get("group")})
    group_tables = []
    team_rows = []

    for group in groups:
        teams = sorted(
            {row["home_team"] for row in fixtures if row["group"] == group}
            | {row["away_team"] for row in fixtures if row["group"] == group}
            | set(completed[group].keys())
        )
        table = {team: _blank_team(team, group, visuals) for team in teams}
        for team, stats in completed[group].items():
            for key in ["played", "points", "goals_for", "goals_against", "goal_difference"]:
                table[team][key] = stats[key]

        for fixture in [row for row in fixtures if row["group"] == group]:
            forecast = forecasts[fixture["match_id"]]
            home = fixture["home_team"]
            away = fixture["away_team"]
            table[home]["expected_points"] += 3 * forecast["home_win"] + forecast["draw"]
            table[away]["expected_points"] += 3 * forecast["away_win"] + forecast["draw"]
            table[home]["expected_goal_balance"] += forecast["expected_goals"]["home"] - forecast["expected_goals"]["away"]
            table[away]["expected_goal_balance"] += forecast["expected_goals"]["away"] - forecast["expected_goals"]["home"]

        ranked = sorted(
            table.values(),
            key=lambda row: (
                row["points"] + row["expected_points"],
                row["goal_difference"] + row["expected_goal_balance"],
                row["goals_for"],
            ),
            reverse=True,
        )
        for idx, row in enumerate(ranked, start=1):
            row["projected_group_rank"] = idx
            row["qualification_probability"] = _qualification_probability(idx)
            row["route_strength"] = _route_strength(idx, row)
            row["likely_round32_opponent_tier"] = _opponent_tier(idx)
            team_rows.append(row)
        group_tables.append({"group": group, "teams": ranked})

    team_rows = sorted(
        team_rows,
        key=lambda row: (row["qualification_probability"], row["points"] + row["expected_points"]),
        reverse=True,
    )
    official_round32 = _build_official_round32(group_tables)
    projection = {
        "method": (
            "Expected-points projection from completed results plus Agent Harness forecasts. "
            "Round-of-32 pairings are indicative until official third-place allocation is known."
        ),
        "group_tables": group_tables,
        "teams": team_rows,
        "likely_round32_pairings": official_round32,
    }
    (OUTPUTS / "tournament_projection.json").write_text(
        json.dumps(projection, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Projected {len(team_rows)} teams across {len(groups)} groups.")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_forecasts(fixtures: list[dict[str, str]]) -> dict[str, dict]:
    forecasts = {}
    for fixture in fixtures:
        path = OUTPUTS / f"forecast_{fixture['match_id']}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))["agents"]["synthesizer"]["payload"]
        forecasts[fixture["match_id"]] = payload
    return forecasts


def _completed_matches_by_group() -> dict[str, dict[str, dict]]:
    source = json.loads((DATA / "worldcup_2026_openfootball.json").read_text(encoding="utf-8"))
    groups: dict[str, dict[str, dict]] = defaultdict(dict)
    for match in source["matches"]:
        if "score" not in match or not match.get("group"):
            continue
        group = match["group"]
        home = match["team1"]
        away = match["team2"]
        hg, ag = match["score"]["ft"]
        _ensure(groups[group], home)
        _ensure(groups[group], away)
        _apply_result(groups[group][home], hg, ag)
        _apply_result(groups[group][away], ag, hg)
    return groups


def _blank_team(team: str, group: str, visuals: dict[str, dict]) -> dict:
    visual = visuals.get(team, {})
    return {
        "team": team,
        "arabic_name": visual.get("arabic_name", team),
        "primary_color": visual.get("primary_color", "#38bdf8"),
        "group": group,
        "played": 0,
        "points": 0,
        "goals_for": 0,
        "goals_against": 0,
        "goal_difference": 0,
        "expected_points": 0.0,
        "expected_goal_balance": 0.0,
    }


def _ensure(group: dict[str, dict], team: str) -> None:
    if team not in group:
        group[team] = _blank_team(team, "", {})


def _apply_result(row: dict, goals_for: int, goals_against: int) -> None:
    row["played"] += 1
    row["goals_for"] += goals_for
    row["goals_against"] += goals_against
    row["goal_difference"] = row["goals_for"] - row["goals_against"]
    if goals_for > goals_against:
        row["points"] += 3
    elif goals_for == goals_against:
        row["points"] += 1


def _qualification_probability(rank: int) -> float:
    if rank == 1:
        return 0.94
    if rank == 2:
        return 0.78
    if rank == 3:
        return 0.42
    return 0.08


def _route_strength(rank: int, row: dict) -> str:
    total = row["points"] + row["expected_points"]
    if rank == 1 and total >= 6:
        return "مسار قوي"
    if rank <= 2:
        return "مسار متوسط"
    return "مسار ضعيف"


def _opponent_tier(rank: int) -> str:
    if rank == 1:
        return "وصيف أو ثالث مجموعة أخرى"
    if rank == 2:
        return "متصدر مجموعة أخرى"
    return "متصدر قوي غالباً"


ROUND32_SLOTS = [
    {"match": 73, "a": ("rank", "A", 2), "b": ("rank", "B", 2)},
    {"match": 74, "a": ("rank", "E", 1), "b": ("third", ["A", "B", "C", "D", "F"])},
    {"match": 75, "a": ("rank", "F", 1), "b": ("rank", "C", 2)},
    {"match": 76, "a": ("rank", "C", 1), "b": ("rank", "F", 2)},
    {"match": 77, "a": ("rank", "I", 1), "b": ("third", ["C", "D", "F", "G", "H"])},
    {"match": 78, "a": ("rank", "E", 2), "b": ("rank", "I", 2)},
    {"match": 79, "a": ("rank", "A", 1), "b": ("third", ["C", "E", "F", "H", "I"])},
    {"match": 80, "a": ("rank", "L", 1), "b": ("third", ["E", "H", "I", "J", "K"])},
    {"match": 81, "a": ("rank", "D", 1), "b": ("third", ["B", "E", "F", "I", "J"])},
    {"match": 82, "a": ("rank", "G", 1), "b": ("third", ["A", "E", "H", "I", "J"])},
    {"match": 83, "a": ("rank", "K", 2), "b": ("rank", "L", 2)},
    {"match": 84, "a": ("rank", "H", 1), "b": ("rank", "J", 2)},
    {"match": 85, "a": ("rank", "B", 1), "b": ("third", ["E", "F", "G", "I", "J"])},
    {"match": 86, "a": ("rank", "J", 1), "b": ("rank", "H", 2)},
    {"match": 87, "a": ("rank", "K", 1), "b": ("third", ["D", "E", "I", "J", "L"])},
    {"match": 88, "a": ("rank", "D", 2), "b": ("rank", "G", 2)},
]


def _build_official_round32(group_tables: list[dict]) -> list[dict]:
    by_group = {
        group["group"].replace("Group ", ""): group["teams"]
        for group in group_tables
    }
    used_thirds: set[str] = set()
    pairings = []
    for slot in ROUND32_SLOTS:
        team1 = _resolve_slot(slot["a"], by_group, used_thirds)
        team2 = _resolve_slot(slot["b"], by_group, used_thirds)
        pairings.append(
            {
                "match": slot["match"],
                "team1": team1.get("team", "TBD"),
                "team1_ar": team1.get("arabic_name", "لم يتحدد"),
                "team1_slot": _slot_label(slot["a"]),
                "team2": team2.get("team", "TBD"),
                "team2_ar": team2.get("arabic_name", "لم يتحدد"),
                "team2_slot": _slot_label(slot["b"]),
                "note": _slot_note(slot["b"]),
            }
        )
    return pairings


def _resolve_slot(slot: tuple, by_group: dict[str, list[dict]], used_thirds: set[str]) -> dict:
    if slot[0] == "rank":
        _, group, rank = slot
        teams = by_group.get(group, [])
        return teams[rank - 1] if len(teams) >= rank else {}
    _, groups = slot
    candidates = []
    for group in groups:
        teams = by_group.get(group, [])
        if len(teams) >= 3:
            candidate = teams[2]
            if candidate["team"] not in used_thirds and candidate["qualification_probability"] >= 0.38:
                candidates.append(candidate)
    if not candidates:
        return {
            "team": "TBD",
            "arabic_name": "أفضل ثالث من " + "/".join(groups),
        }
    selected = sorted(
        candidates,
        key=lambda row: (row["points"] + row["expected_points"], row["goal_difference"] + row["expected_goal_balance"]),
        reverse=True,
    )[0]
    used_thirds.add(selected["team"])
    return selected


def _slot_label(slot: tuple) -> str:
    if slot[0] == "rank":
        _, group, rank = slot
        if rank == 1:
            return f"متصدر المجموعة {group}"
        if rank == 2:
            return f"وصيف المجموعة {group}"
        return f"المركز {rank} من المجموعة {group}"
    return "أفضل ثالث من " + "/".join(slot[1])


def _slot_note(slot: tuple) -> str:
    if slot[0] == "third":
        return "خانة أصحاب المركز الثالث تتبع جدول FIFA/Annex C، والاختيار هنا إسقاط من أفضل ثالث متوقع ضمن المجموعات المسموحة."
    return "مسار FIFA رسمي ثابت لهذه الخانة."


if __name__ == "__main__":
    main()
