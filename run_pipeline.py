from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from football_harness.agents import (
    ButterflyFactorsAgent,
    CriticAuditorAgent,
    DataCollectionAgent,
    SelfCorrectionAgent,
    SpecialistAnalysisAgent,
    SynthesizerAgent,
    TeamIntelligenceAgent,
)
from football_harness.core import AgentHarness, MatchContext


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the football forecasting Agent Harness.")
    parser.add_argument("--match-id", default=None, help="Fixture match_id to forecast. Defaults to first fixture.")
    args = parser.parse_args()

    fixture = _load_fixture(args.match_id)
    match = MatchContext(
        match_id=fixture["match_id"],
        home_team=fixture["home_team"],
        away_team=fixture["away_team"],
        kickoff_utc=_parse_datetime(fixture["kickoff_utc"]),
        generated_at_utc=_parse_datetime(fixture["generated_at_utc"]),
        metadata={
            "neutral_venue": fixture["match_id"].startswith("WC-"),
            "group": fixture.get("group", ""),
            "ground": fixture.get("ground", ""),
            "round": fixture.get("round", ""),
            "stage": fixture.get("stage", "group"),
        },
    )

    harness = AgentHarness(
        agents=[
            DataCollectionAgent(
                DATA / "historical_results.csv",
                DATA / "butterfly_events.csv",
                DATA / "team_seed_ranks.csv",
                DATA / "match_advanced_stats.csv",
                DATA / "model_calibration.json",
            ),
            SpecialistAnalysisAgent(),
            TeamIntelligenceAgent(),
            ButterflyFactorsAgent(),
            CriticAuditorAgent(),
            SynthesizerAgent(),
            SelfCorrectionAgent(DATA / "actual_results.csv"),
        ]
    )
    state = harness.run_match(match)
    report = {
        "match": {
            "match_id": match.match_id,
            "home_team": match.home_team,
            "away_team": match.away_team,
            "kickoff_utc": match.kickoff_utc.isoformat(),
            "group": fixture.get("group", ""),
            "ground": fixture.get("ground", ""),
            "round": fixture.get("round", ""),
            "stage": fixture.get("stage", "group"),
        },
        "audit_log": state.audit_log,
        "agents": {
            name: {
                "status": result.status,
                "summary": result.summary,
                "warnings": result.warnings,
                "payload": _json_safe(result.payload),
            }
            for name, result in state.results.items()
        },
    }

    OUTPUTS.mkdir(exist_ok=True)
    output_path = OUTPUTS / f"forecast_{match.match_id}.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    final = report["agents"]["synthesizer"]["payload"]
    print(f"Forecast saved to: {output_path}")
    print(f"{match.home_team} vs {match.away_team}")
    print(
        "Final probabilities: "
        f"home={final['home_win']:.3f}, draw={final['draw']:.3f}, away={final['away_win']:.3f}"
    )
    print(f"Recommendation: {final['recommended_label']}")
    print(f"Explanation: {final['explanation']}")


def _load_fixture(match_id: str | None) -> dict[str, str]:
    import csv

    with (DATA / "fixtures.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if match_id is None or row["match_id"] == match_id:
                return row
    raise SystemExit(f"Unknown match_id: {match_id}")


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "__dict__"):
        return _json_safe(value.__dict__)
    return value


if __name__ == "__main__":
    main()
