# Free Stable Deployment

Recommended path: GitHub Actions + GitHub Pages.

Why this path:
- It runs without your computer being on.
- It is free for a public GitHub repository.
- It supports scheduled automation every 20 minutes.
- It preserves model evolution as Git commits and files under `outputs/model_versions` and `outputs/forecast_ledger`.
- It serves the dashboard as a public static site through GitHub Pages.

How it works:
1. GitHub Actions wakes up every 20 minutes.
2. `update_worldcup_results.py` refreshes open-source match data.
3. ESPN stats are fetched by the agent pipeline when due matches are processed.
4. The model compares predictions with actual results.
5. A new calibration/model snapshot is stored.
6. Forecasts for the remaining group matches are regenerated.
7. GitHub Pages publishes `index.html`, `outputs`, and `data`.

Setup:
1. Push this project folder to a public GitHub repository.
2. In GitHub, open Settings -> Pages.
3. Set Source to "GitHub Actions".
4. Open Actions and run "World Cup Agent Harness" manually once.
5. After the first successful run, open the Pages URL shown by GitHub.

Important reality:
- Free automation still needs an external service. GitHub is that service here.
- Your personal computer and internet do not need to stay on after the project is pushed.
- Scheduled GitHub Actions can occasionally start a few minutes late during platform load, so "20 minutes" means practical polling, not guaranteed real-time execution.
