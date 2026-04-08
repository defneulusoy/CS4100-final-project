from __future__ import annotations

import argparse
import csv
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


DEFAULT_INPUT = "routes_clean.csv"
DEFAULT_OUTPUT = "best_itinerary.json"
DEFAULT_COST_PER_KM_USD = 0.12


@dataclass
class EdgeData:
    duration_min: float
    distance_km: float
    optional_price: Optional[float]


def _parse_optional_price(value: str) -> Optional[float]:
    text = value.strip()
    if not text:
        return None
    try:
        price = float(text)
    except ValueError:
        return None
    return price if price > 0 else None


def load_edge_lookup(path: str) -> Dict[str, Dict[str, EdgeData]]:
    lookup: Dict[str, Dict[str, EdgeData]] = {}
    with open(path, "r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            origin = row["origin_iata"].strip().upper()
            destination = row["destination_iata"].strip().upper()
            duration = float(row["est_duration_min"])
            distance = float(row.get("distance_km", "0") or 0)
            optional_price = _parse_optional_price(row.get("optional_price", ""))
            lookup.setdefault(origin, {})[destination] = EdgeData(
                duration_min=duration,
                distance_km=distance,
                optional_price=optional_price,
            )
    return lookup


def resolve_leg(origin: str, destination: str, lookup: Dict[str, Dict[str, EdgeData]]) -> Optional[EdgeData]:
    direct = lookup.get(origin, {}).get(destination)
    if direct is not None:
        return direct
    return lookup.get(destination, {}).get(origin)


def has_all_legs(
    itinerary: Sequence[str],
    lookup: Dict[str, Dict[str, EdgeData]],
    return_to_start: bool,
) -> bool:
    if len(itinerary) < 2:
        return True

    for i in range(len(itinerary) - 1):
        if resolve_leg(itinerary[i], itinerary[i + 1], lookup) is None:
            return False

    if return_to_start:
        if resolve_leg(itinerary[-1], itinerary[0], lookup) is None:
            return False

    return True


def route_duration(
    itinerary: Sequence[str],
    lookup: Dict[str, Dict[str, EdgeData]],
    invalid_penalty_min: float,
    return_to_start: bool,
) -> float:
    if len(itinerary) < 2:
        return 0.0

    total = 0.0
    for i in range(len(itinerary) - 1):
        origin, destination = itinerary[i], itinerary[i + 1]
        edge = resolve_leg(origin, destination, lookup)
        if edge is not None:
            total += edge.duration_min
        else:
            total += invalid_penalty_min

    if return_to_start:
        edge = resolve_leg(itinerary[-1], itinerary[0], lookup)
        if edge is not None:
            total += edge.duration_min
        else:
            total += invalid_penalty_min

    return total


def route_cost(
    itinerary: Sequence[str],
    lookup: Dict[str, Dict[str, EdgeData]],
    invalid_leg_penalty_usd: float,
    return_to_start: bool,
    cost_per_km_usd: float,
) -> float:
    if len(itinerary) < 2:
        return 0.0

    total = 0.0
    for i in range(len(itinerary) - 1):
        edge = resolve_leg(itinerary[i], itinerary[i + 1], lookup)
        if edge is None:
            total += invalid_leg_penalty_usd
        elif edge.optional_price is not None:
            total += edge.optional_price
        else:
            total += max(edge.distance_km * cost_per_km_usd, 0.0)

    if return_to_start:
        edge = resolve_leg(itinerary[-1], itinerary[0], lookup)
        if edge is None:
            total += invalid_leg_penalty_usd
        elif edge.optional_price is not None:
            total += edge.optional_price
        else:
            total += max(edge.distance_km * cost_per_km_usd, 0.0)

    return total


def ordered_crossover(parent1: List[str], parent2: List[str], rng: random.Random) -> List[str]:
    n = len(parent1)
    if n <= 1:
        return parent1[:]

    start, end = sorted(rng.sample(range(n), 2))
    child = [""] * n
    child[start : end + 1] = parent1[start : end + 1]

    remaining = [gene for gene in parent2 if gene not in child]
    write_idx = 0
    for gene in remaining:
        while child[write_idx] != "":
            write_idx += 1
        child[write_idx] = gene

    return child


def mutate_swap(chromosome: List[str], rng: random.Random) -> None:
    if len(chromosome) < 2:
        return
    i, j = rng.sample(range(len(chromosome)), 2)
    chromosome[i], chromosome[j] = chromosome[j], chromosome[i]


def mutate_inversion(chromosome: List[str], rng: random.Random) -> None:
    if len(chromosome) < 2:
        return
    i, j = sorted(rng.sample(range(len(chromosome)), 2))
    chromosome[i : j + 1] = reversed(chromosome[i : j + 1])


def two_opt(
    itinerary: List[str],
    lookup: Dict[str, Dict[str, EdgeData]],
    invalid_penalty_min: float,
    return_to_start: bool,
) -> List[str]:
    best = itinerary[:]
    best_score = route_duration(best, lookup, invalid_penalty_min, return_to_start)
    improved = True

    while improved:
        improved = False
        for i in range(1, len(best) - 1):
            for j in range(i + 1, len(best)):
                candidate = best[:]
                candidate[i : j + 1] = reversed(candidate[i : j + 1])
                score = route_duration(candidate, lookup, invalid_penalty_min, return_to_start)
                if score < best_score:
                    best, best_score = candidate, score
                    improved = True
    return best


def random_day_allocation(num_stops: int, total_days: int, rng: random.Random) -> List[int]:
    if num_stops <= 0:
        return []
    if total_days < num_stops:
        raise ValueError("Total trip days must be at least the number of destination stops.")

    days = [1] * num_stops
    remaining = total_days - num_stops

    for _ in range(remaining):
        days[rng.randrange(num_stops)] += 1

    return days


def normalize_days(days: List[int], total_days: int, rng: random.Random) -> List[int]:
    if not days:
        return []

    days = [max(1, d) for d in days]
    current_sum = sum(days)

    while current_sum > total_days:
        valid = [i for i, d in enumerate(days) if d > 1]
        if not valid:
            break
        idx = rng.choice(valid)
        days[idx] -= 1
        current_sum -= 1

    while current_sum < total_days:
        idx = rng.randrange(len(days))
        days[idx] += 1
        current_sum += 1

    return days


def stay_balance_penalty(days: Sequence[int]) -> float:
    if not days:
        return 0.0
    avg = sum(days) / len(days)
    return sum(abs(day - avg) for day in days)


@dataclass
class GAConfig:
    population_size: int = 100
    generations: int = 200
    mutation_rate: float = 0.2
    elite_count: int = 5
    tournament_size: int = 4
    invalid_penalty_min: float = 1200.0
    return_to_start: bool = True
    apply_two_opt: bool = True
    seed: int = 42
    budget_usd: Optional[float] = None
    total_days: int = 7
    invalid_leg_penalty_usd: float = 1000.0
    cost_per_km_usd: float = DEFAULT_COST_PER_KM_USD
    daily_stay_cost_usd: float = 150.0
    balance_penalty_weight: float = 30.0
    cost_weight: float = 0.10


class ItineraryGA:
    def __init__(self, cities: List[str], lookup: Dict[str, Dict[str, EdgeData]], config: GAConfig):
        if len(cities) < 2:
            raise ValueError("Need at least a start city and one destination.")

        self.start_city = cities[0]
        self.variable_cities = cities[1:]
        self.lookup = lookup
        self.config = config
        self.rng = random.Random(config.seed)

    def _build_full_itinerary(self, variable_order: List[str]) -> List[str]:
        return [self.start_city] + variable_order

    def _lodging_cost(self, days: Sequence[int]) -> float:
        return sum(days) * self.config.daily_stay_cost_usd

    def _create_individual(self) -> Dict[str, List]:
        route = self.variable_cities[:]
        self.rng.shuffle(route)
        days = random_day_allocation(len(route), self.config.total_days, self.rng)
        return {"route": route, "days": days}

    def _fitness(self, individual: Dict[str, List]) -> float:
        variable_order = individual["route"]
        days = individual["days"]
        itinerary = self._build_full_itinerary(variable_order)

        if len(variable_order) != len(self.variable_cities):
            return float("inf")
        if sorted(variable_order) != sorted(self.variable_cities):
            return float("inf")
        if len(days) != len(self.variable_cities):
            return float("inf")
        if any(day < 1 for day in days):
            return float("inf")
        if sum(days) != self.config.total_days:
            return float("inf")

        if not has_all_legs(itinerary, self.lookup, self.config.return_to_start):
            return float("inf")

        duration = route_duration(
            itinerary,
            self.lookup,
            invalid_penalty_min=self.config.invalid_penalty_min,
            return_to_start=self.config.return_to_start,
        )

        transit_cost = route_cost(
            itinerary,
            self.lookup,
            invalid_leg_penalty_usd=self.config.invalid_leg_penalty_usd,
            return_to_start=self.config.return_to_start,
            cost_per_km_usd=self.config.cost_per_km_usd,
        )

        lodging_cost = self._lodging_cost(days)
        total_cost = transit_cost + lodging_cost

        if self.config.budget_usd is not None and total_cost > self.config.budget_usd:
            return float("inf")

        balance_penalty = stay_balance_penalty(days) * self.config.balance_penalty_weight
        return duration + self.config.cost_weight * total_cost + balance_penalty

    def _initial_population(self) -> List[Dict[str, List]]:
        return [self._create_individual() for _ in range(self.config.population_size)]

    def _tournament_select(self, scored_population: List[Tuple[float, Dict[str, List]]]) -> Dict[str, List]:
        contenders = self.rng.sample(
            scored_population,
            min(self.config.tournament_size, len(scored_population)),
        )
        return min(contenders, key=lambda item: item[0])[1]

    def _crossover(self, parent1: Dict[str, List], parent2: Dict[str, List]) -> Dict[str, List]:
        child_route = ordered_crossover(parent1["route"], parent2["route"], self.rng)

        child_days = []
        for d1, d2 in zip(parent1["days"], parent2["days"]):
            child_days.append(self.rng.choice([d1, d2]))

        child_days = normalize_days(child_days, self.config.total_days, self.rng)
        return {"route": child_route, "days": child_days}

    def _mutate(self, individual: Dict[str, List]) -> Dict[str, List]:
        route = individual["route"][:]
        days = individual["days"][:]

        if self.rng.random() < self.config.mutation_rate:
            mutate_swap(route, self.rng)
        if self.rng.random() < self.config.mutation_rate / 2.0:
            mutate_inversion(route, self.rng)

        if days and self.rng.random() < self.config.mutation_rate:
            candidates = [i for i, d in enumerate(days) if d > 1]
            if candidates:
                from_idx = self.rng.choice(candidates)
                to_idx = self.rng.randrange(len(days))
                while to_idx == from_idx:
                    to_idx = self.rng.randrange(len(days))
                days[from_idx] -= 1
                days[to_idx] += 1

        days = normalize_days(days, self.config.total_days, self.rng)
        return {"route": route, "days": days}

    def run(self) -> Dict[str, object]:
        population = self._initial_population()
        history_best: List[Optional[float]] = []

        for _ in range(self.config.generations):
            scored = sorted(
                ((self._fitness(ind), ind) for ind in population),
                key=lambda item: item[0],
            )

            best_score_this_gen = scored[0][0]
            history_best.append(None if math.isinf(best_score_this_gen) else round(best_score_this_gen, 3))

            elites = []
            for score, ind in scored[: self.config.elite_count]:
                if math.isinf(score):
                    continue

                elite = {"route": ind["route"][:], "days": ind["days"][:]}

                if self.config.apply_two_opt:
                    full = self._build_full_itinerary(elite["route"])
                    improved_full = two_opt(
                        full,
                        self.lookup,
                        self.config.invalid_penalty_min,
                        self.config.return_to_start,
                    )
                    elite["route"] = improved_full[1:]

                elites.append(elite)

            next_population = elites[:]

            if not next_population:
                next_population.extend(self._initial_population()[: self.config.elite_count])

            while len(next_population) < self.config.population_size:
                parent1 = self._tournament_select(scored)
                parent2 = self._tournament_select(scored)
                child = self._crossover(parent1, parent2)
                child = self._mutate(child)
                next_population.append(child)

            population = next_population

        final_scored = sorted(
            ((self._fitness(ind), ind) for ind in population),
            key=lambda item: item[0],
        )

        best_score, best_individual = final_scored[0]

        if math.isinf(best_score):
            raise ValueError(
                "No valid itinerary found. This usually means one or more route legs are missing from "
                "routes_clean.csv, or the budget/days settings are too restrictive. Also make sure you "
                "are using actual airport-style IATA codes like BOS, LAX, JFK, LGA, EWR."
            )

        best_itinerary = self._build_full_itinerary(best_individual["route"])

        estimated_transit_cost = route_cost(
            best_itinerary,
            self.lookup,
            invalid_leg_penalty_usd=self.config.invalid_leg_penalty_usd,
            return_to_start=self.config.return_to_start,
            cost_per_km_usd=self.config.cost_per_km_usd,
        )
        estimated_lodging_cost = self._lodging_cost(best_individual["days"])
        estimated_total_cost = estimated_transit_cost + estimated_lodging_cost
        total_duration = route_duration(
            best_itinerary,
            self.lookup,
            self.config.invalid_penalty_min,
            self.config.return_to_start,
        )

        return {
            "best_itinerary": best_itinerary,
            "days_per_stop": best_individual["days"],
            "best_total_duration_min": round(total_duration, 3),
            "estimated_transit_cost_usd": round(estimated_transit_cost, 2),
            "estimated_lodging_cost_usd": round(estimated_lodging_cost, 2),
            "estimated_total_cost_usd": round(estimated_total_cost, 2),
            "budget_usd": self.config.budget_usd,
            "total_days": self.config.total_days,
            "return_to_start": self.config.return_to_start,
            "seed": self.config.seed,
            "generations": self.config.generations,
            "history_best_score": history_best,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize multi-city itinerary via genetic algorithm.")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--cities", help="Comma-separated IATA codes including start city.")
    parser.add_argument("--start", help="Starting city IATA code for interactive mode.")
    parser.add_argument("--destinations", help="Comma-separated destination IATA codes for interactive mode.")
    parser.add_argument("--budget", type=float, help="Budget in USD.")
    parser.add_argument("--days", type=int, help="Total trip days spent across destinations.")
    parser.add_argument("--interactive", action="store_true", help="Prompt for inputs in terminal.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--population-size", type=int, default=60)
    parser.add_argument("--generations", type=int, default=80)
    parser.add_argument("--mutation-rate", type=float, default=0.2)
    parser.add_argument("--elite-count", type=int, default=4)
    parser.add_argument("--tournament-size", type=int, default=4)
    parser.add_argument("--invalid-penalty-min", type=float, default=1200.0)
    parser.add_argument("--invalid-leg-penalty-usd", type=float, default=1000.0)
    parser.add_argument("--cost-per-km-usd", type=float, default=DEFAULT_COST_PER_KM_USD)
    parser.add_argument("--daily-stay-cost-usd", type=float, default=150.0)
    parser.add_argument("--balance-penalty-weight", type=float, default=30.0)
    parser.add_argument("--cost-weight", type=float, default=0.10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-return", action="store_true")
    parser.add_argument("--no-two-opt", action="store_true")
    return parser.parse_args()


def _parse_iata_list(text: str) -> List[str]:
    return [code.strip().upper() for code in text.split(",") if code.strip()]


def prompt_for_inputs(args: argparse.Namespace) -> Tuple[List[str], float, int]:
    if args.interactive or not args.cities:
        default_destinations = args.destinations or ""
        destinations_text = input(
            f"What location(s) would you like to visit? (IATA, comma-separated)"
            f"{' [' + default_destinations + ']' if default_destinations else ''}: "
        ).strip()
        if not destinations_text and default_destinations:
            destinations_text = default_destinations

        default_start = args.start or ""
        start_text = input(
            f"Where are you starting from? (IATA)"
            f"{' [' + default_start + ']' if default_start else ''}: "
        ).strip()
        if not start_text and default_start:
            start_text = default_start

        default_budget = "" if args.budget is None else str(args.budget)
        budget_text = input(
            f"What is your budget? (USD)"
            f"{' [' + default_budget + ']' if default_budget else ''}: "
        ).strip()
        if not budget_text and default_budget:
            budget_text = default_budget

        default_days = "" if args.days is None else str(args.days)
        days_text = input(
            f"How many total days is your trip?"
            f"{' [' + default_days + ']' if default_days else ''}: "
        ).strip()
        if not days_text and default_days:
            days_text = default_days

        destinations = _parse_iata_list(destinations_text)
        start = start_text.strip().upper()
        if not start:
            raise ValueError("Start city is required.")
        if not budget_text:
            raise ValueError("Budget is required.")
        if not days_text:
            raise ValueError("Total trip days are required.")

        budget = float(budget_text)
        total_days = int(days_text)

        cities = [start] + [city for city in destinations if city != start]
        return cities, budget, total_days

    cities = _parse_iata_list(args.cities)
    if args.budget is None or args.days is None:
        raise ValueError("When not using --interactive, provide both --budget and --days.")
    return cities, float(args.budget), int(args.days)


def write_result(payload: Dict[str, object], output_path: str) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)


def main() -> None:
    args = parse_args()
    cities, budget, total_days = prompt_for_inputs(args)

    if len(cities) < 2:
        raise ValueError("Provide a start city and at least one destination.")
    if len(set(cities)) != len(cities):
        raise ValueError("Cities list must not contain duplicates.")
    if total_days < len(cities) - 1:
        raise ValueError("Total days must be at least the number of destinations.")

    config = GAConfig(
        population_size=args.population_size,
        generations=args.generations,
        mutation_rate=args.mutation_rate,
        elite_count=args.elite_count,
        tournament_size=args.tournament_size,
        invalid_penalty_min=args.invalid_penalty_min,
        invalid_leg_penalty_usd=args.invalid_leg_penalty_usd,
        cost_per_km_usd=args.cost_per_km_usd,
        daily_stay_cost_usd=args.daily_stay_cost_usd,
        balance_penalty_weight=args.balance_penalty_weight,
        cost_weight=args.cost_weight,
        budget_usd=budget,
        total_days=total_days,
        return_to_start=not args.no_return,
        apply_two_opt=not args.no_two_opt,
        seed=args.seed,
    )

    lookup = load_edge_lookup(args.input)

    # quick precheck for at least one route permutation if there are few destinations
    if len(cities) <= 8:
        import itertools
        found_any_valid_route = False
        for perm in itertools.permutations(cities[1:]):
            test_itinerary = [cities[0]] + list(perm)
            if has_all_legs(test_itinerary, lookup, config.return_to_start):
                found_any_valid_route = True
                break
        if not found_any_valid_route:
            raise ValueError(
                "No valid route ordering exists in routes_clean.csv for the cities you entered. "
                "Try different airport codes. For example, use LAX instead of LA, and JFK/LGA/EWR instead of NYC if needed."
            )

    ga = ItineraryGA(cities=cities, lookup=lookup, config=config)
    result = ga.run()
    write_result(result, args.output)

    print(f"Best itinerary: {' -> '.join(result['best_itinerary'])}")
    print("Days per stop:")
    for city, days in zip(result["best_itinerary"][1:], result["days_per_stop"]):
        print(f"  {city}: {days} day(s)")
    print(f"Best total duration (min): {result['best_total_duration_min']}")
    print(f"Estimated transit cost (USD): {result['estimated_transit_cost_usd']}")
    print(f"Estimated lodging cost (USD): {result['estimated_lodging_cost_usd']}")
    print(f"Estimated total cost (USD): {result['estimated_total_cost_usd']}")
    print(f"Budget (USD): {result['budget_usd']}")
    print(f"Saved result -> {args.output}")


if __name__ == "__main__":
    main()