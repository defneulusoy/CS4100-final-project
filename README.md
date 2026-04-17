# CS4100 Final Project: Travel Itinerary Optimization

A Python-based travel planner that builds multi-city trip itineraries by optimizing destination order, attractions, and day allocation, complete with an interactive map display.


## Set Up

1. Clone the repository:

```bash
git clone https://github.com/defneulusoy/CS4100-final-project.git
cd CS4100-final-project
```

2. Make sure Python 3 is installed:

```bash
python3 --version
```

3. Set your API keys:

```bash
export SERPAPI_KEY=your_serpapi_key
export GOOGLE_PLACES_API_KEY=your_google_places_key
```

- SERPAPI_KEY is required for running
- If GOOGLE_PLACES_API_KEY is absent, mock data is used.


## How To Run

Run the main script from the project directory:
```bash
python3 travel_agent.py
```

The program will prompt you for:

- Starting city
- Cities to visit (comma-separated)
- Total budget (USD)
- Total trip duration (days)


## Reproducing Results

To reproduce our results, run the program and enter the following:

- Starting city: Boston
- Cities to visit: Paris, Rome, London
- Budget: 10000
- Total trip duration: 14

This will generate a full itinerary and an interactive map showing the travel route and budget breakdown, including attractions and duration of time in each destination.


## Code Organization

- travel_agent.py - main script that runs the itinerary planning workflow
- flights_api.py - handles flight and hotel data retrieval
- output_map.py - generates the interactive HTML map visualization