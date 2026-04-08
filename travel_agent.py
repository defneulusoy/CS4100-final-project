"""
AI Travel Recommendation Agent
Two-layer First-Choice Hill Climbing:
  Layer 1: Optimize city visit order by flight cost + duration
  Layer 2: Rank attractions in each city by importance score

Environment variables:
    SERPAPI_KEY         – from https://api.flightapi.io/register  (free)
    GOOGLE_PLACES_API_KEY – from https://console.cloud.google.com   (free tier)
                            If absent, mock attraction data is used.
"""

import math
import random
import os
from dataclasses import dataclass, field
from typing import Optional
import urllib.request
import urllib.parse
import json

# Flight data module (same directory)
from flights_api import (
    Airport, Flight,
    build_flight_data, make_api_key,
)


# ---------------------------------------------------------------------------
# Data classes  (Flight and Airport are imported from flights_api)
# ---------------------------------------------------------------------------

@dataclass
class Attraction:
    name: str
    rating: float          # 0.0 – 5.0
    review_count: int
    price_level: int       # 0 (free) – 4 (very expensive)
    types: list[str] = field(default_factory=list)
    score: float = 0.0     # computed importance score


@dataclass
class CityPlan:
    city: str
    days: int                    # allocated days to spend here
    flight: Optional[Flight]
    attractions: list[Attraction] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Attraction importance score
# ---------------------------------------------------------------------------

CATEGORY_WEIGHTS: dict[str, float] = {
    "museum": 1.2,
    "park": 1.1,
    "tourist_attraction": 1.15,
    "art_gallery": 1.1,
    "church": 1.0,
    "restaurant": 0.8,
    "shopping_mall": 0.7,
    "default": 1.0,
}

PRICE_PENALTY: dict[int, float] = {
    0: 1.0,   # free
    1: 0.97,
    2: 0.93,
    3: 0.87,
    4: 0.75,  # very expensive
}


def attraction_importance(attr: Attraction, budget_per_day: float) -> float:
    """
    Composite importance score.

    Formula:
        score = rating * log(reviews + 1) * category_weight * price_penalty

    - log(reviews + 1): dampens raw count — prevents viral spots from dominating
    - category_weight:  boosts culturally rich venues (museums, parks, landmarks)
    - price_penalty:    down-ranks expensive spots when budget is tight
                        (penalty steepens if budget_per_day < $100)

    Returns a float. Higher = more important to visit.
    """
    if attr.rating == 0 and attr.review_count == 0:
        return 0.0

    # Pick the highest-weight category the attraction belongs to
    cat_w = max(
        (CATEGORY_WEIGHTS.get(t, CATEGORY_WEIGHTS["default"]) for t in attr.types),
        default=CATEGORY_WEIGHTS["default"],
    )

    # Tighten price penalty on a tight budget
    base_penalty = PRICE_PENALTY.get(attr.price_level, 1.0)
    if budget_per_day < 100 and attr.price_level >= 3:
        base_penalty *= 0.80

    score = attr.rating * math.log(attr.review_count + 1) * cat_w * base_penalty
    return round(score, 4)


# ---------------------------------------------------------------------------
# Layer 1 – Hill climbing: city visit order
# ---------------------------------------------------------------------------

def flight_cost(origin: str, destination: str, flight_data: dict[tuple, Flight]) -> float:
    """Return flight price or a large penalty if the route doesn't exist."""
    key = (origin.lower(), destination.lower())
    if key in flight_data:
        return flight_data[key].price
    # Try reverse (won't be used for routing but avoids KeyError in edge cases)
    return 999_999.0


def route_objective(
    order: list[str],
    start_city: str,
    flight_data: dict[tuple, Flight],
    total_days: int,
    budget: float,
) -> float:
    """
    Objective to MINIMISE for Layer 1.

    Cost = total_flight_price
           + duration_penalty   (over-budget time penalised)
           + budget_overage * 100

    Lower is better.
    """
    cities = [start_city] + order
    total_price = 0.0
    total_hours = 0.0

    for i in range(len(cities) - 1):
        key = (cities[i].lower(), cities[i + 1].lower())
        flight = flight_data.get(key)
        if flight is None:
            total_price += 999_999.0   # heavy penalty for missing route
        else:
            total_price += flight.price
            total_hours += flight.duration

    # Penalise if total flight time consumes too much of the trip
    available_hours = total_days * 24
    if total_hours > available_hours * 0.4:
        total_price += (total_hours - available_hours * 0.4) * 50

    # Penalise budget overage
    if total_price > budget:
        total_price += (total_price - budget) * 100

    return total_price


def first_choice_hill_climbing_route(
    cities: list[str],
    start_city: str,
    flight_data: dict[tuple, Flight],
    total_days: int,
    budget: float,
    max_iterations: int = 2000,
    max_sideways: int = 50,
) -> list[str]:
    """
    First-Choice Hill Climbing for city ordering.

    Neighbourhood: random swap of two cities in the route.
    Accepts the first neighbour that strictly improves the objective.
    Sideways moves allowed to escape flat plateaux.
    """
    current = cities[:]
    random.shuffle(current)
    current_score = route_objective(current, start_city, flight_data, total_days, budget)

    sideways = 0

    for _ in range(max_iterations):
        if len(current) < 2:
            break

        # Generate a random neighbour (swap two random positions)
        i, j = random.sample(range(len(current)), 2)
        neighbour = current[:]
        neighbour[i], neighbour[j] = neighbour[j], neighbour[i]
        neighbour_score = route_objective(neighbour, start_city, flight_data, total_days, budget)

        if neighbour_score < current_score:
            current = neighbour
            current_score = neighbour_score
            sideways = 0
        elif neighbour_score == current_score and sideways < max_sideways:
            current = neighbour
            sideways += 1
        # else: discard (first-choice: only move on improvement or sideways)

    return current


# ---------------------------------------------------------------------------
# Layer 2 – Rank attractions per city
# ---------------------------------------------------------------------------

def rank_attractions(
    attractions: list[Attraction],
    budget_per_day: float,
    top_n: int = 10,
) -> list[Attraction]:
    """
    Score and sort attractions using the importance formula.
    Returns top_n attractions, highest score first.

    This is hill climbing in selection space:
    - Start with a random subset of min(top_n, len) attractions
    - Iteratively swap out one attraction for a better-scored unchosen one
    - Stop when no improving swap exists (local optimum)

    For small lists (≤ top_n) this degenerates to a simple sort — which IS
    the global optimum, so that's fine.
    """
    for attr in attractions:
        attr.score = attraction_importance(attr, budget_per_day)

    if len(attractions) <= top_n:
        return sorted(attractions, key=lambda a: a.score, reverse=True)

    # Hill climbing selection
    chosen = set(range(top_n))
    unchosen = set(range(top_n, len(attractions)))
    current_value = sum(attractions[i].score for i in chosen)

    improved = True
    while improved:
        improved = False
        for i in list(chosen):
            for j in list(unchosen):
                if attractions[j].score > attractions[i].score:
                    chosen.remove(i)
                    unchosen.add(i)
                    chosen.add(j)
                    unchosen.remove(j)
                    current_value += attractions[j].score - attractions[i].score
                    improved = True
                    break
            if improved:
                break

    result = [attractions[i] for i in chosen]
    return sorted(result, key=lambda a: a.score, reverse=True)




# ---------------------------------------------------------------------------
# Day allocation across cities
# ---------------------------------------------------------------------------

def allocate_days(
    ordered_cities: list[str],
    city_attractions: dict[str, list[Attraction]],
    total_days: int,
    flight_hours: dict[str, float],
) -> dict[str, int]:
    """
    Distribute total_days across cities proportionally to each city's
    cumulative attraction score (sum of top-10 scores).

    Cities with more and better attractions earn more days.
    Transit time (flight duration rounded up to nearest half-day) is
    subtracted from the pool first so travel overhead is accounted for.

    Guarantees every city gets at least 1 day.
    """
    n = len(ordered_cities)
    if n == 0:
        return {}

    # Deduct travel days (each flight leg eats time)
    transit_days = sum(
        math.ceil(flight_hours.get(c, 0) / 12) * 0.5   # half-day per ~12h flight
        for c in ordered_cities
    )
    available = max(n, total_days - transit_days)   # always at least 1 day/city

    # Weight each city by total attraction score
    weights: dict[str, float] = {}
    for city in ordered_cities:
        attractions = city_attractions.get(city, [])
        weights[city] = sum(a.score for a in attractions) or 1.0   # floor at 1

    total_weight = sum(weights.values())

    # Proportional allocation, floor at 1
    raw: dict[str, float] = {
        c: max(1.0, (weights[c] / total_weight) * available)
        for c in ordered_cities
    }

    # Round down, then distribute leftover days to highest-weighted cities
    alloc = {c: int(v) for c, v in raw.items()}
    remainder = total_days - sum(alloc.values())

    # Give extra days to cities with the largest fractional parts
    fractions = sorted(ordered_cities, key=lambda c: raw[c] - alloc[c], reverse=True)
    for city in fractions:
        if remainder <= 0:
            break
        alloc[city] += 1
        remainder -= 1

    return alloc

# ---------------------------------------------------------------------------
# Google Places API helper
# ---------------------------------------------------------------------------

def fetch_attractions_google(city: str, api_key: str) -> list[Attraction]:
    """
    Fetch tourist attractions from Google Places Text Search API.
    Returns up to 20 candidate attractions for hill-climbing selection.
    """
    query = urllib.parse.quote(f"top tourist attractions in {city}")
    url = (
        f"https://maps.googleapis.com/maps/api/place/textsearch/json"
        f"?query={query}&type=tourist_attraction&key={api_key}"
    )

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [warning] Could not fetch attractions for {city}: {e}")
        return []

    attractions = []
    for place in data.get("results", []):
        attr = Attraction(
            name=place.get("name", "Unknown"),
            rating=float(place.get("rating", 0)),
            review_count=int(place.get("user_ratings_total", 0)),
            price_level=int(place.get("price_level", 0)),
            types=place.get("types", []),
        )
        attractions.append(attr)

    return attractions


def mock_attractions(city: str) -> list[Attraction]:
    """
    Placeholder used when no Google API key is provided.
    Generates plausible-looking fake data so the algorithm can be demonstrated.
    """
    samples = [
        ("Historic Old Town", 4.7, 18500, 0, ["tourist_attraction", "church"]),
        ("National Museum", 4.5, 12000, 1, ["museum"]),
        ("Central Park / Gardens", 4.6, 22000, 0, ["park"]),
        ("Art Gallery of Modern Art", 4.4, 8500, 2, ["art_gallery"]),
        ("Famous Cathedral", 4.8, 31000, 0, ["church", "tourist_attraction"]),
        ("Street Food Market", 4.3, 9800, 1, ["restaurant", "food"]),
        ("City Viewpoint", 4.5, 14000, 0, ["tourist_attraction"]),
        ("Archaeological Site", 4.6, 7200, 1, ["tourist_attraction", "museum"]),
        ("Botanical Garden", 4.4, 6500, 1, ["park"]),
        ("Luxury Shopping District", 4.0, 21000, 4, ["shopping_mall"]),
        ("Local Craft Market", 4.2, 5000, 1, ["shopping_mall"]),
        ("Royal Palace / Fortress", 4.7, 28000, 2, ["tourist_attraction"]),
        ("Science Museum", 4.3, 11000, 2, ["museum"]),
        ("Waterfront Promenade", 4.5, 17000, 0, ["park", "tourist_attraction"]),
        ("Zoo / Aquarium", 4.2, 13000, 3, ["tourist_attraction"]),
    ]
    result = []
    for name, rating, reviews, price_lvl, types in samples:
        result.append(Attraction(
            name=f"{name} ({city})",
            rating=rating + random.uniform(-0.2, 0.2),
            review_count=reviews + random.randint(-1000, 1000),
            price_level=price_lvl,
            types=types,
        ))
    random.shuffle(result)
    return result


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def prompt(msg: str) -> str:
    return input(msg).strip()


def get_cities() -> tuple[str, list[str]]:
    start = prompt("Starting city: ").title()
    raw = prompt("Cities to visit (comma-separated): ")
    destinations = [c.strip().title() for c in raw.split(",") if c.strip()]
    return start, destinations


def get_budget() -> float:
    while True:
        try:
            return float(prompt("Total budget (USD): $"))
        except ValueError:
            print("  Please enter a number.")


def get_days() -> int:
    while True:
        try:
            return int(prompt("Total trip duration (days): "))
        except ValueError:
            print("  Please enter a whole number.")




# ---------------------------------------------------------------------------
# Pretty output
# ---------------------------------------------------------------------------

SEPARATOR = "─" * 60


def print_itinerary(start: str, ordered_cities: list[str], city_plans: dict[str, CityPlan]):
    print(f"\n{'═'*60}")
    print("  ✈  OPTIMISED TRAVEL ITINERARY")
    print(f"{'═'*60}")
    print(f"\n  Departure: {start}\n")

    for idx, city in enumerate(ordered_cities, 1):
        plan = city_plans[city]
        flight = plan.flight

        days_label = f"{plan.days} day{'s' if plan.days != 1 else ''}"
        if flight:
            print(f"  Stop {idx}: {city}  ({days_label})")
            print(f"  {SEPARATOR}")
            print(f"  ✈  Flight:   {flight.origin_airport.name} ({flight.origin_airport.iata_code})")
            print(f"              → {flight.destination_airport.name} ({flight.destination_airport.iata_code})")
            print(f"      Airline:   {flight.airline}  |  {flight.flight_number}")
            print(f"      Departs:   {flight.departure_time}")
            print(f"      Arrives:   {flight.arrival_time}")
            stops_str = f"{flight.stops} stop{'s' if flight.stops != 1 else ''}" if flight.stops else "non-stop"
            print(f"      Duration:  {flight.duration:.1f} hrs  ({stops_str})")
            print(f"      Price:     ${flight.price:.2f}")
        else:
            print(f"\n  Stop {idx}: {city}  ({days_label}, no flight data)")

        # Attractions
        print(f"\n  🗺  Top Attractions (ranked by importance):\n")
        if plan.attractions:
            for rank, attr in enumerate(plan.attractions, 1):
                stars = "★" * round(attr.rating) + "☆" * (5 - round(attr.rating))
                price_str = ["Free", "$", "$$", "$$$", "$$$$"][attr.price_level]
                print(f"    {rank:>2}. {attr.name}")
                print(f"        {stars}  {attr.rating:.1f}  |  {attr.review_count:,} reviews"
                      f"  |  {price_str}  |  score: {attr.score:.2f}")
        else:
            print("    No attraction data available.")

        print()

    print(f"{'═'*60}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("\n╔══════════════════════════════════════╗")
    print("║   AI Travel Recommendation Agent    ║")
    print("╚══════════════════════════════════════╝\n")

    # --- User input ---
    start_city, dest_cities = get_cities()
    budget = get_budget()
    total_days = get_days()
    budget_per_day = budget / max(total_days, 1)

    google_api_key  = os.environ.get("GOOGLE_PLACES_API_KEY", "")
    use_real_attractions = bool(google_api_key)

    # --- Flight data via FlightAPI.io ---
    try:
        flight_api_key = make_api_key()
    except EnvironmentError as e:
        print(f"\n  ✗  {e}")
        print("  Cannot continue without flight data. Exiting.\n")
        return

    airports, flight_data = build_flight_data(start_city, dest_cities, flight_api_key)

    if not flight_data:
        print("\n  ✗  No flight data returned. Check your API key and city names.")
        return

    # --- Layer 1: Optimise city order ---
    print("⏳ Optimising route (Layer 1 – Hill Climbing on flights)...")
    optimised_order = first_choice_hill_climbing_route(
        dest_cities, start_city, flight_data, total_days, budget
    )

    # --- Layer 2: Fetch & rank attractions ---
    print("⏳ Ranking attractions per city (Layer 2 – Hill Climbing on importance)...\n")
    city_raw_attractions: dict[str, list] = {}
    prev_city = start_city

    for city in optimised_order:
        if use_real_attractions:
            raw = fetch_attractions_google(city, google_api_key)
        else:
            raw = mock_attractions(city)
        ranked = rank_attractions(raw, budget_per_day, top_n=10)
        city_raw_attractions[city] = ranked

    # Allocate days proportionally to attraction richness
    flight_hours = {
        city: flight_data[(optimised_order[i - 1].lower() if i > 0 else start_city.lower(),
                           city.lower())].duration
        if (optimised_order[i - 1].lower() if i > 0 else start_city.lower(),
            city.lower()) in flight_data else 0.0
        for i, city in enumerate(optimised_order)
    }
    day_alloc = allocate_days(optimised_order, city_raw_attractions, total_days, flight_hours)

    city_plans: dict[str, CityPlan] = {}
    prev_city = start_city
    for city in optimised_order:
        key = (prev_city.lower(), city.lower())
        flight = flight_data.get(key)
        city_plans[city] = CityPlan(
            city=city,
            days=day_alloc[city],
            flight=flight,
            attractions=city_raw_attractions[city],
        )
        prev_city = city

    # --- Output ---
    print_itinerary(start_city, optimised_order, city_plans)

    total_flight_cost = sum(
        city_plans[c].flight.price for c in optimised_order if city_plans[c].flight
    )
    remaining_budget = budget - total_flight_cost

    print(f"  💰 Total flight cost:  ${total_flight_cost:.2f}")
    print(f"  💰 Remaining budget:   ${remaining_budget:.2f}")
    print(f"  📅 Day breakdown:")
    for city in optimised_order:
        d = city_plans[city].days
        print(f"       {city}: {d} day{'s' if d != 1 else ''}")
    if not use_real_attractions:
        print("\n  ⚠  Attraction data is mocked. Set GOOGLE_PLACES_API_KEY to use real data.")
    print()


if __name__ == "__main__":
    main()