from __future__ import annotations

import argparse
import csv
import json
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
	budget_penalty_per_dollar: float = 4.0
	cost_per_km_usd: float = DEFAULT_COST_PER_KM_USD
	invalid_leg_penalty_usd: float = 1000.0


class ItineraryGA:
	def __init__(self, cities: List[str], lookup: Dict[str, Dict[str, EdgeData]], config: GAConfig):
		if len(cities) < 2:
			raise ValueError("Need at least two cities.")

		self.start_city = cities[0]
		self.variable_cities = cities[1:]
		self.lookup = lookup
		self.config = config
		self.rng = random.Random(config.seed)

	def _build_full_itinerary(self, variable_order: List[str]) -> List[str]:
		return [self.start_city] + variable_order

	def _fitness(self, variable_order: List[str]) -> float:
		itinerary = self._build_full_itinerary(variable_order)
		duration = route_duration(
			itinerary,
			self.lookup,
			invalid_penalty_min=self.config.invalid_penalty_min,
			return_to_start=self.config.return_to_start,
		)
		if self.config.budget_usd is None:
			return duration

		estimated_cost = route_cost(
			itinerary,
			self.lookup,
			invalid_leg_penalty_usd=self.config.invalid_leg_penalty_usd,
			return_to_start=self.config.return_to_start,
			cost_per_km_usd=self.config.cost_per_km_usd,
		)
		over_budget = max(0.0, estimated_cost - self.config.budget_usd)
		return duration + over_budget * self.config.budget_penalty_per_dollar

	def _initial_population(self) -> List[List[str]]:
		population: List[List[str]] = []
		base = self.variable_cities[:]
		for _ in range(self.config.population_size):
			candidate = base[:]
			self.rng.shuffle(candidate)
			population.append(candidate)
		return population

	def _tournament_select(self, scored_population: List[Tuple[float, List[str]]]) -> List[str]:
		contenders = self.rng.sample(
			scored_population,
			min(self.config.tournament_size, len(scored_population)),
		)
		return min(contenders, key=lambda item: item[0])[1][:]

	def run(self) -> Dict[str, object]:
		population = self._initial_population()
		history_best: List[float] = []

		for _ in range(self.config.generations):
			scored = sorted((self._fitness(chrom), chrom) for chrom in population)
			history_best.append(scored[0][0])

			elites = [chrom[:] for _, chrom in scored[: self.config.elite_count]]
			if self.config.apply_two_opt:
				elites = [
					two_opt(
						chrom,
						self.lookup,
						self.config.invalid_penalty_min,
						self.config.return_to_start,
					)[1:]
					for chrom in (self._build_full_itinerary(e) for e in elites)
				]

			next_population = elites[:]
			while len(next_population) < self.config.population_size:
				parent1 = self._tournament_select(scored)
				parent2 = self._tournament_select(scored)
				child = ordered_crossover(parent1, parent2, self.rng)

				if self.rng.random() < self.config.mutation_rate:
					mutate_swap(child, self.rng)
				if self.rng.random() < self.config.mutation_rate / 2.0:
					mutate_inversion(child, self.rng)

				next_population.append(child)

			population = next_population

		final_scored = sorted((self._fitness(chrom), chrom) for chrom in population)
		best_score, best_variable = final_scored[0]
		best_itinerary = self._build_full_itinerary(best_variable)

		return {
			"best_itinerary": best_itinerary,
			"best_total_duration_min": round(best_score, 3),
			"budget_usd": self.config.budget_usd,
			"return_to_start": self.config.return_to_start,
			"seed": self.config.seed,
			"generations": self.config.generations,
			"history_best_duration_min": [round(v, 3) for v in history_best],
		}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Optimize multi-city flight itinerary via GA.")
	parser.add_argument("--input", default=DEFAULT_INPUT)
	parser.add_argument("--cities", help="Comma-separated IATA codes including start city.")
	parser.add_argument("--start", help="Starting city IATA code for interactive mode.")
	parser.add_argument("--destinations", help="Comma-separated destination IATA codes for interactive mode.")
	parser.add_argument("--budget", type=float, help="Budget in USD (soft constraint).")
	parser.add_argument("--interactive", action="store_true", help="Prompt for inputs in terminal.")
	parser.add_argument("--output", default=DEFAULT_OUTPUT)
	parser.add_argument("--population-size", type=int, default=100)
	parser.add_argument("--generations", type=int, default=200)
	parser.add_argument("--mutation-rate", type=float, default=0.2)
	parser.add_argument("--elite-count", type=int, default=5)
	parser.add_argument("--tournament-size", type=int, default=4)
	parser.add_argument("--invalid-penalty-min", type=float, default=1200.0)
	parser.add_argument("--invalid-leg-penalty-usd", type=float, default=1000.0)
	parser.add_argument("--cost-per-km-usd", type=float, default=DEFAULT_COST_PER_KM_USD)
	parser.add_argument("--budget-penalty-per-dollar", type=float, default=4.0)
	parser.add_argument("--seed", type=int, default=42)
	parser.add_argument("--no-return", action="store_true")
	parser.add_argument("--no-two-opt", action="store_true")
	return parser.parse_args()


def _parse_iata_list(text: str) -> List[str]:
	return [code.strip().upper() for code in text.split(",") if code.strip()]


def prompt_for_inputs(args: argparse.Namespace) -> Tuple[List[str], Optional[float]]:
	if args.interactive or not args.cities:
		default_destinations = args.destinations or ""
		destinations_text = input(
			f"What location(s) would you like to visit? (IATA, comma-separated){' [' + default_destinations + ']' if default_destinations else ''}: "
		).strip()
		if not destinations_text and default_destinations:
			destinations_text = default_destinations

		default_start = args.start or ""
		start_text = input(
			f"Where are you starting from? (IATA){' [' + default_start + ']' if default_start else ''}: "
		).strip()
		if not start_text and default_start:
			start_text = default_start

		default_budget = "" if args.budget is None else str(args.budget)
		budget_text = input(
			f"What is your budget? (USD, optional){' [' + default_budget + ']' if default_budget else ''}: "
		).strip()
		if not budget_text and default_budget:
			budget_text = default_budget

		destinations = _parse_iata_list(destinations_text)
		start = start_text.strip().upper()
		if not start:
			raise ValueError("Start city is required.")

		cities = [start] + [city for city in destinations if city != start]
		budget = None if not budget_text else float(budget_text)
		return cities, budget

	cities = _parse_iata_list(args.cities)
	budget = args.budget
	return cities, budget


def write_result(payload: Dict[str, object], output_path: str) -> None:
	output = Path(output_path)
	output.parent.mkdir(parents=True, exist_ok=True)
	with output.open("w", encoding="utf-8") as file:
		json.dump(payload, file, indent=2)


def main() -> None:
	args = parse_args()
	cities, budget = prompt_for_inputs(args)
	if len(cities) < 2:
		raise ValueError("Provide a start city and at least one destination.")
	if len(set(cities)) != len(cities):
		raise ValueError("Cities list must not contain duplicates.")

	config = GAConfig(
		population_size=args.population_size,
		generations=args.generations,
		mutation_rate=args.mutation_rate,
		elite_count=args.elite_count,
		tournament_size=args.tournament_size,
		invalid_penalty_min=args.invalid_penalty_min,
		invalid_leg_penalty_usd=args.invalid_leg_penalty_usd,
		cost_per_km_usd=args.cost_per_km_usd,
		budget_penalty_per_dollar=args.budget_penalty_per_dollar,
		budget_usd=budget,
		return_to_start=not args.no_return,
		apply_two_opt=not args.no_two_opt,
		seed=args.seed,
	)

	lookup = load_edge_lookup(args.input)
	ga = ItineraryGA(cities=cities, lookup=lookup, config=config)
	result = ga.run()
	result["estimated_total_cost_usd"] = round(
		route_cost(
			result["best_itinerary"],
			lookup,
			invalid_leg_penalty_usd=config.invalid_leg_penalty_usd,
			return_to_start=config.return_to_start,
			cost_per_km_usd=config.cost_per_km_usd,
		),
		2,
	)
	write_result(result, args.output)

	print(f"Best itinerary: {' -> '.join(result['best_itinerary'])}")
	print(f"Best total duration (min): {result['best_total_duration_min']}")
	print(f"Estimated total cost (USD): {result['estimated_total_cost_usd']}")
	if budget is not None:
		print(f"Budget (USD): {budget}")
	print(f"Saved result -> {args.output}")


if __name__ == "__main__":
	main()

