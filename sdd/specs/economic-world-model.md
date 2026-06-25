# Economic World Model

## Purpose

The Economic World Model is a long-run country-strength layer. It does not replace match form, tactical statistics, or butterfly events. It asks a slower question:

> Does this country possess the structural conditions that repeatedly manufacture strong football teams?

## Inputs

The first operational version reads `data/economic_world_indicators.csv`.

Normalized fields:

- `gdp_per_capita_index`: national income capacity.
- `population_index`: size of the talent pool.
- `football_market_index`: money, player value, league/commercial strength.
- `academy_pipeline_index`: ability to convert youth talent into elite players.
- `climate_fit_index`: comfort with the tournament weather and match environment.
- `league_export_index`: number and quality of players exported to strong leagues.
- `home_region_fit_index`: geographic and cultural fit with the host region.

## Agent

`EconomicWorldAgent` produces:

- `home_score`
- `away_score`
- `probability_adjustment`
- visible factor cards under the final forecast explanation

## Guardrails

- The layer is capped to a small probability adjustment.
- It is weighted by `economic_world_weight` in `data/model_calibration.json`.
- It must not dominate fresh match evidence.
- Missing data creates a warning instead of a false confident adjustment.

## Interpretation

This layer captures the idea from the Al Jazeera model:

- Money does not score goals directly, but it builds the path to talent.
- Population widens the search space.
- Climate and host-region familiarity affect comfort and preparation.
- Football markets and academies convert raw talent into elite team strength.

The Agent Harness now combines two worlds:

- short-run match intelligence: results, advanced stats, butterfly events, critic review
- long-run economic world intelligence: the country behind the team
