#!/usr/bin/env python3
"""CLI entry point – plan a multi-city trip using first-choice hill climbing."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from models import City, TripRequest, TripResult
from city_data import resolve_city_name
from hill_climbing import first_choice_hill_climbing


def _resolve_or_exit(text: str) -> City:
    city = resolve_city_name(text)
    if city is None:
        print(f"Could not find city: '{text}'")
        print("Tip: try the full city name (e.g. 'Boston', 'New York', 'Los Angeles').")
        sys.exit(1)
    return city


def prompt_inputs() -> Tuple[City, List[City], float, int]:
    origin_text = input("Where are you starting from? ").strip()
    origin = _resolve_or_exit(origin_text)
    print(f"  -> {origin.name} ({origin.iata})")

    dest_text = input("What cities do you want to visit? (comma-separated) ").strip()
    dest_cities: List[City] = []
    for part in dest_text.split(","):
        part = part.strip()
        if not part:
            continue
        city = _resolve_or_exit(part)
        if city.iata == origin.iata:
            print(f"  Skipping '{city.name}' – same as origin.")
            continue
        if any(c.iata == city.iata for c in dest_cities):
            print(f"  Skipping duplicate '{city.name}'.")
            continue
        print(f"  -> {city.name} ({city.iata})")
        dest_cities.append(city)

    if not dest_cities:
        print("Need at least one destination.")
        sys.exit(1)

    budget = float(input("What is your total budget (USD)? $").strip())
    days = int(input("How many days is your trip? ").strip())
    return origin, dest_cities, budget, days


def print_result(result: TripResult) -> None:
    print()
    print("=" * 60)
    print("  TRIP ITINERARY")
    print("=" * 60)

    day_counter = 1
    for i, city in enumerate(result.city_order):
        days_here = result.days_per_city[i]
        flight = result.flights[i]
        day_end = day_counter + days_here - 1
        day_label = (
            f"Day {day_counter}" if days_here == 1
            else f"Day {day_counter}-{day_end}"
        )

        print(f"\n{day_label}: {city}")
        print(
            f"  Flight: {flight.origin} -> {flight.destination}  "
            f"(${flight.price_usd:.0f}, "
            f"{flight.duration_min / 60:.1f}h)"
        )

        attractions = result.attractions_by_city.get(city, [])
        if attractions:
            print("  Attractions:")
            for a in attractions:
                cost_str = "free" if a.cost_usd == 0 else f"${a.cost_usd:.0f}"
                print(f"    - {a.name} ({cost_str}) [{a.category}]")
        else:
            print("  Attractions: (none fit budget)")

        day_counter = day_end + 1

    # return flight
    if len(result.flights) > len(result.city_order):
        ret = result.flights[-1]
        print(f"\nReturn: {ret.origin} -> {ret.destination}  "
              f"(${ret.price_usd:.0f}, {ret.duration_min / 60:.1f}h)")

    print()
    print("-" * 60)
    print("  COST SUMMARY")
    print("-" * 60)
    print(f"  Flights:      ${result.total_flight_cost:>8.2f}")
    print(f"  Attractions:  ${result.total_attraction_cost:>8.2f}")
    print(f"  ─────────────────────────────")
    print(f"  Total:        ${result.total_cost:>8.2f}  /  ${result.budget_usd:.2f} budget")
    remaining = result.budget_usd - result.total_cost
    print(f"  Remaining:    ${remaining:>8.2f}")
    print()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plan a multi-city trip with hill climbing.")
    p.add_argument("--origin", help="Starting city name (e.g. Boston)")
    p.add_argument("--destinations", help='Comma-separated city names (e.g. "NYC, LA")')
    p.add_argument("--budget", type=float, help="Total budget in USD")
    p.add_argument("--days", type=int, help="Total trip days")
    p.add_argument("--no-return", action="store_true", help="One-way trip (don't fly back)")
    p.add_argument("--restarts", type=int, default=10, help="Hill-climbing restarts")
    p.add_argument("--iterations", type=int, default=2000, help="Max iterations per restart")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output", default="trip_result.json", help="Output JSON path")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.origin and args.destinations and args.budget and args.days:
        origin = _resolve_or_exit(args.origin)
        dest_cities = [_resolve_or_exit(d.strip()) for d in args.destinations.split(",") if d.strip()]
        budget = args.budget
        days = args.days
    else:
        origin, dest_cities, budget, days = prompt_inputs()

    if days < len(dest_cities):
        print(f"Need at least {len(dest_cities)} days for {len(dest_cities)} destinations.")
        sys.exit(1)

    # Build city_map: name -> City for all involved cities
    city_map: Dict[str, City] = {origin.name: origin}
    for c in dest_cities:
        city_map[c.name] = c

    dest_names = [c.name for c in dest_cities]

    request = TripRequest(
        origin=origin.name,
        destinations=dest_names,
        budget_usd=budget,
        total_days=days,
    )

    print(f"\nOptimizing: {origin.name} ({origin.iata}) -> {', '.join(f'{c.name} ({c.iata})' for c in dest_cities)}")
    print(f"Budget: ${budget:.0f}  |  Days: {days}")
    print("Fetching flight prices & attractions from APIs...")
    print("Running first-choice hill climbing...\n")

    result = first_choice_hill_climbing(
        request,
        city_map,
        max_iterations=args.iterations,
        num_restarts=args.restarts,
        return_to_start=not args.no_return,
        seed=args.seed,
    )

    print_result(result)

    # save JSON
    out_path = Path(args.output)
    payload = {
        "origin": result.origin,
        "city_order": result.city_order,
        "days_per_city": result.days_per_city,
        "flights": [
            {"origin": f.origin, "destination": f.destination,
             "price_usd": f.price_usd, "duration_min": f.duration_min}
            for f in result.flights
        ],
        "attractions_by_city": {
            city: [{"name": a.name, "cost_usd": a.cost_usd,
                     "category": a.category, "address": a.address}
                    for a in alist]
            for city, alist in result.attractions_by_city.items()
        },
        "total_flight_cost": result.total_flight_cost,
        "total_attraction_cost": result.total_attraction_cost,
        "total_cost": result.total_cost,
        "budget_usd": result.budget_usd,
        "total_days": result.total_days,
        "score": result.score,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
