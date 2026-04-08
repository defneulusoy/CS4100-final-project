"""First-choice hill climbing for multi-city trip optimization.

Layer 1 – flight ordering & day allocation (optimized by hill climbing).
Layer 2 – attraction selection per city (greedy, given remaining budget).
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

from models import Attraction, City, Flight, TripRequest, TripResult, TripState
from city_data import get_flight, get_attractions

# ---------------------------------------------------------------------------
# Layer 2 – greedy attraction selection
# ---------------------------------------------------------------------------

def select_attractions(
    city: City,
    remaining_budget: float,
) -> Tuple[List[Attraction], float]:
    """Pick attractions greedily (cheapest first). Returns (selected, total_cost)."""
    all_attractions = get_attractions(city)
    candidates = sorted(all_attractions, key=lambda a: a.cost_usd)

    selected: List[Attraction] = []
    total_cost = 0.0

    for attr in candidates:
        if total_cost + attr.cost_usd > remaining_budget:
            continue
        selected.append(attr)
        total_cost += attr.cost_usd

    return selected, total_cost

# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(
    state: TripState,
    request: TripRequest,
    city_map: Dict[str, City],
    return_to_start: bool = True,
) -> Tuple[float, List[Flight], Dict[str, List[Attraction]], float, float]:
    """Score a candidate state.  Higher is better.

    Returns (score, flights, attractions_by_city, flight_cost, attraction_cost).
    """
    origin = request.origin
    order = state.city_order

    # --- flights (use IATA codes) ---
    origin_city = city_map[origin]
    flights: List[Flight] = []
    legs = [origin] + list(order)
    if return_to_start:
        legs.append(origin)

    for i in range(len(legs) - 1):
        from_iata = city_map[legs[i]].iata
        to_iata = city_map[legs[i + 1]].iata
        flights.append(get_flight(from_iata, to_iata))

    flight_cost = sum(f.price_usd for f in flights)

    # --- budget feasibility ---
    if flight_cost > request.budget_usd:
        overshoot = flight_cost - request.budget_usd
        return (-1e9 - overshoot, flights, {}, flight_cost, 0.0)

    remaining_budget = request.budget_usd - flight_cost

    # --- Layer 2: greedy attraction selection ---
    attractions_by_city: Dict[str, List[Attraction]] = {}
    attraction_cost = 0.0

    for city_name in order:
        city = city_map[city_name]
        selected, cost = select_attractions(city, remaining_budget)
        attractions_by_city[city_name] = selected
        attraction_cost += cost
        remaining_budget -= cost

    # --- score: maximize attraction count; lightly penalize flight cost ---
    total_attractions_count = sum(len(v) for v in attractions_by_city.values())

    score = (
        total_attractions_count * 10
        - flight_cost * 0.01
    )

    return (score, flights, attractions_by_city, flight_cost, attraction_cost)

# ---------------------------------------------------------------------------
# Neighbor generation
# ---------------------------------------------------------------------------

def _random_neighbor(state: TripState, rng: random.Random) -> TripState:
    new = TripState(
        city_order=list(state.city_order),
        days_per_city=list(state.days_per_city),
    )
    n = len(new.city_order)
    if n < 2:
        return new

    move = rng.choice(["swap", "shift_day", "reverse"])

    if move == "swap":
        i, j = rng.sample(range(n), 2)
        new.city_order[i], new.city_order[j] = new.city_order[j], new.city_order[i]

    elif move == "shift_day":
        donors = [i for i, d in enumerate(new.days_per_city) if d > 1]
        if donors:
            from_idx = rng.choice(donors)
            to_idx = rng.choice([i for i in range(n) if i != from_idx])
            new.days_per_city[from_idx] -= 1
            new.days_per_city[to_idx] += 1

    elif move == "reverse":
        i, j = sorted(rng.sample(range(n), 2))
        new.city_order[i : j + 1] = reversed(new.city_order[i : j + 1])

    return new

# ---------------------------------------------------------------------------
# Random initial state
# ---------------------------------------------------------------------------

def _random_state(request: TripRequest, rng: random.Random) -> TripState:
    order = list(request.destinations)
    rng.shuffle(order)

    n = len(order)
    total = request.total_days

    if total < n:
        raise ValueError(
            f"Need at least {n} days for {n} destinations (1 day each)."
        )

    days = [1] * n
    remaining = total - n
    for _ in range(remaining):
        days[rng.randrange(n)] += 1

    return TripState(city_order=order, days_per_city=days)

# ---------------------------------------------------------------------------
# First-choice hill climbing
# ---------------------------------------------------------------------------

def first_choice_hill_climbing(
    request: TripRequest,
    city_map: Dict[str, City],
    *,
    max_iterations: int = 2000,
    max_neighbors: int = 100,
    num_restarts: int = 10,
    return_to_start: bool = True,
    seed: int = 42,
) -> TripResult:
    """Run first-choice hill climbing with random restarts."""
    rng = random.Random(seed)

    best_state: Optional[TripState] = None
    best_score = -math.inf
    best_extras: Optional[tuple] = None

    for _ in range(num_restarts):
        current = _random_state(request, rng)
        cur_score, *cur_extras = evaluate(current, request, city_map, return_to_start)

        for _ in range(max_iterations):
            improved = False

            for _ in range(max_neighbors):
                neighbor = _random_neighbor(current, rng)
                n_score, *n_extras = evaluate(neighbor, request, city_map, return_to_start)

                if n_score > cur_score:
                    current = neighbor
                    cur_score = n_score
                    cur_extras = n_extras
                    improved = True
                    break  # first-choice: accept first improvement

            if not improved:
                break  # local optimum

        if cur_score > best_score:
            best_state = current
            best_score = cur_score
            best_extras = tuple(cur_extras)

    if best_state is None or best_extras is None:
        raise ValueError("Hill climbing failed to find any solution.")

    flights, attractions_by_city, flight_cost, attraction_cost = best_extras

    return TripResult(
        origin=request.origin,
        city_order=list(best_state.city_order),
        days_per_city=list(best_state.days_per_city),
        flights=flights,
        total_flight_cost=round(flight_cost, 2),
        total_attraction_cost=round(attraction_cost, 2),
        total_cost=round(flight_cost + attraction_cost, 2),
        attractions_by_city=attractions_by_city,
        budget_usd=request.budget_usd,
        total_days=request.total_days,
        score=round(best_score, 3),
    )
