# CS4100-final-project

Offline-first CLI workflow for flight itinerary optimization using a genetic algorithm with local search.

## User Guide

### Who this is for

Use this project if you want to optimize a multi-city flight itinerary from the terminal using a genetic algorithm.

### Prerequisites

- Python 3.10+ installed
- Internet access for API calls
- API keys generated for SerpAPI and Google Places API

### Quick start

Run these three commands in order:

```bash
python3 data_collection.py --output routes_raw.csv --max-routes 5000
python3 data_cleaning.py --input routes_raw.csv --output routes_clean.csv --graph-output route_graph.json --meta-output cleaning_meta.json
python3 genetic.py --interactive --input routes_clean.csv
```

### Interactive trip planning flow

When you run interactive mode, answer:

1. `Where are you starting from?` (single IATA code or city name)
2. `What location(s) would you like to visit?` (city names of IATA codes, comma-separated)
3. `What is your budget?` (USD)
4. `What is your the duration of your trip?` (days)

Example input:

- Start: `Boston`
- Destinations: `New York, Rome, Paris, Tokyo`
- Budget: `9000`
- Days: `15`

### How to read results

- `Best itinerary`: route order selected by GA
- `Best total duration (min)`: objective value being minimized
- `Estimated total cost (USD)`: estimated total spend from route prices or distance heuristic
- `Budget (USD)`: shown if you entered one

### Common issues

- `Budget not enough for `
	- Ensure you provide 1 start city + at least 1 destination.
- `Cities list must not contain duplicates`
	- Remove repeated airport codes.

## Objective

- Problem scope: multi-city itinerary optimization
- Primary objective: minimize total estimated travel time
- Data strategy: offline open datasets by default, optional live API enrichment later

## Data schema

All stages use this route schema:

- `origin_iata`
- `destination_iata`
- `distance_km`
- `est_duration_min`
- `optional_price`
- `source`

## 1) Collect raw routes

Uses OpenFlights airports/routes (free/open) and computes estimated duration from great-circle distance.

```bash
python3 data_collection.py \
	--output routes_raw.csv \
	--max-routes 5000
```

Optional local sources:

```bash
python3 data_collection.py \
	--airports-source ./data/airports.dat \
	--routes-source ./data/routes.dat \
	--output routes_raw.csv
```

## 2) Clean + build route graph

Validates IATA pairs, removes invalid rows, deduplicates origin/destination edges, and exports graph + stats.

```bash
python3 data_cleaning.py \
	--input routes_raw.csv \
	--output routes_clean.csv \
	--graph-output route_graph.json \
	--meta-output cleaning_meta.json
```

## 3) Optimize itinerary with GA + 2-opt

You can run this either interactively (prompt-based) or with flags.

### Interactive mode (recommended)

```bash
python3 genetic.py --interactive --input routes_clean.csv
```

Prompts:

- `What location(s) would you like to visit?`
- `Where are you starting from?`
- `What is your budget?`

Budget is optional. If provided, it is used as a soft constraint in fitness (over-budget itineraries are penalized).

### Flag mode

Provide comma-separated cities; first city is fixed as start.

```bash
python3 genetic.py \
	--input routes_clean.csv \
	--cities JFK,LAX,SFO,SEA,ORD \
	--budget 1200 \
	--population-size 120 \
	--generations 250 \
	--output best_itinerary.json
```

Useful flags:

- `--no-return` to avoid forcing return to starting city
- `--no-two-opt` to disable local search refinement
- `--seed` for deterministic runs

## Output artifacts

- `routes_raw.csv`: collected route candidates
- `routes_clean.csv`: cleaned route table for optimization
- `route_graph.json`: adjacency map with duration weights
- `cleaning_meta.json`: row-count quality report
- `best_itinerary.json`: best route found and fitness history