from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from forecast_ledger import archive_forecast


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"


def main() -> None:
    match_ids = []
    with (DATA / "fixtures.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            match_ids.append(row["match_id"])

    manifest = []
    with (DATA / "team_visuals.csv").open("r", encoding="utf-8", newline="") as f:
        visuals = {
            row["team"]: {
                "arabic_name": row["arabic_name"],
                "primary_color": row["primary_color"],
                "secondary_color": row["secondary_color"],
            }
            for row in csv.DictReader(f)
        }
    for match_id in match_ids:
        subprocess.run(
            [sys.executable, str(ROOT / "run_pipeline.py"), "--match-id", match_id],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        archive_forecast(OUTPUTS / f"forecast_{match_id}.json")
        manifest.append(f"outputs/forecast_{match_id}.json")

    subprocess.run(
        [sys.executable, str(ROOT / "project_tournament_paths.py")],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [sys.executable, str(ROOT / "learn_from_group_errors.py")],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [sys.executable, str(ROOT / "learn_equation_parameters.py")],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [sys.executable, str(ROOT / "time_series_forecaster.py")],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [sys.executable, str(ROOT / "predict_knockout_bracket.py")],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )

    OUTPUTS.mkdir(exist_ok=True)
    (OUTPUTS / "forecast_manifest.json").write_text(
        json.dumps(
            {
                "files": manifest,
                "team_visuals": visuals,
                "knockout_bracket": "outputs/knockout_bracket_prediction.json",
                "learning_report": "outputs/group_learning_report.json",
                "equation_learning": "data/equation_learning.json",
                "time_series_forecast": "data/time_series_forecast.json",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Generated {len(manifest)} World Cup forecasts.")


if __name__ == "__main__":
    main()
