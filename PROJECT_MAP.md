# Project Map — World Cup Agent Harness Dashboard

This document tracks the technical state, architecture, system flow, and pending tasks for the World Cup forecasting dashboard.

---

## 🛠️ [TECH_STACK]

- **Front-end**: Vanilla HTML5, CSS3 (Custom Styles), Javascript (ES6+, asynchronous fetch)
- **Data Formats**: JSON (`forecast_manifest.json`, `tournament_projection.json`, model configs), CSV (`fixtures.csv`, `actual_results.csv`, `match_advanced_stats.csv`)
- **Backend/Scripts**: Python 3.12+ (standard library, `urllib`, `argparse`, `csv`)
- **Automation/CI-CD**: GitHub Actions (runs every 20m), GitHub Pages (serves dashboard as static site)

---

## 🔄 [SYSTEM_FLOW]

1. **GitHub Actions Scheduler**:
   - Runs `update_worldcup_results.py` to sync match data from the openfootball JSON source.
   - Determines if any match is due/recently completed, triggers `fetch_espn_match_stats.py` to pull detailed stats from ESPN APIs (with a robust ±3 days search window).
   - Recalibrates prediction models, runs simulations, and rebuilds JSON outputs.
   - Commits changes to Git and deploys the static files to GitHub Pages.

2. **Dashboard Client (`index.html`)**:
   - Fetches `outputs/forecast_manifest.json` to load available team configurations, primary colors, Arabic names, and a list of forecast files.
   - Loads match statistics, actual results, and knockout winner CSVs using a compliant RFC-4180 CSV parser.
   - Renders the responsive group pairings, tournament projections, knockout bracket, and the model's accuracy/metrics dashboard.

---

## 📐 [ARCHITECTURE]

- **Data Files (`/data`)**: Source fixtures, actual scores, and advanced match stats.
- **Output Files (`/outputs`)**: Compiled forecasts, tournament simulation projections, and model metrics.
- **Orchestrator (`match_monitor.py`)**: Runs in the background, checks due matches, coordinates fetching and calibrating pipelines.
- **Visuals Design**:
  - Theme: Dark glassmorphism styled layout.
  - Colors: Dynamic, defined per team in `forecast_manifest.json`.

---

## 📝 [ORPHANS & PENDING]

These are pending feature upgrades requested by the user, inspired by `mcp.magnific.com` and `wcup2026.org`:

### 🎨 Visual & Design Upgrades (Style of mcp.magnific.com)
- [ ] Implement dark glassmorphism theme (`backdrop-filter: blur`, subtle translucent borders).
- [ ] Add neon glowing borders matching active team colors.
- [ ] Integrate modern typography using the Cairo Google Font (`Cairo:wght@400;600;700;900`).
- [ ] Clean up and polish mobile viewport responsive alignments.

### 📊 Dashboard Match Indicators (Style of wcup2026.org)
- [ ] **AI Prediction Score**: Show predicted score (e.g. `2-1` or `1-0`) on match cards.
- [ ] **FIFA Team Rank**: Show FIFA ranking (e.g., `#2` or `#8`) for each team on match cards.
- [ ] **Probability Bars**: Render probability percentages (`home_win %` / `draw %` / `away_win %`) as visual colored horizontal bars instead of plain text.
- [ ] **Match Meta**: Display stadium name and local kickoff time on the cards.
- [ ] **Referees & Stadium Info**: Expand the detailed views to show referee names and additional match metadata when stats are available.
