from __future__ import annotations

import argparse
import csv
import math
import random
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse
from urllib.request import urlopen


DEFAULT_AIRPORTS_SOURCE = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
DEFAULT_ROUTES_SOURCE = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat"
DEFAULT_OUTPUT = "routes_raw.csv"


def _read_source_lines(source: str) -> Iterable[str]:
	parsed = urlparse(source)
	if parsed.scheme in {"http", "https"}:
		with urlopen(source) as response:
			payload = response.read().decode("utf-8", errors="replace")
		return payload.splitlines()

	with open(source, "r", encoding="utf-8", newline="") as file:
		return file.read().splitlines()


def load_airports(source: str) -> Dict[str, Tuple[float, float]]:
	airports: Dict[str, Tuple[float, float]] = {}
	reader = csv.reader(_read_source_lines(source))
	for row in reader:
		if len(row) < 8:
			continue
		iata = row[4].strip().upper()
		if len(iata) != 3 or iata == "\\N":
			continue
		try:
			latitude = float(row[6])
			longitude = float(row[7])
		except ValueError:
			continue
		airports[iata] = (latitude, longitude)
	return airports


def haversine_km(origin: Tuple[float, float], destination: Tuple[float, float]) -> float:
	lat1, lon1 = origin
	lat2, lon2 = destination
	phi1, phi2 = math.radians(lat1), math.radians(lat2)
	dphi = math.radians(lat2 - lat1)
	dlambda = math.radians(lon2 - lon1)

	a = (
		math.sin(dphi / 2.0) ** 2
		+ math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
	)
	return 2.0 * 6371.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def estimate_duration_min(distance_km: float) -> float:
	cruise_speed_kmh = 820.0
	fixed_overhead_min = 35.0
	return fixed_overhead_min + (distance_km / cruise_speed_kmh) * 60.0


def collect_routes(
	airports_source: str,
	routes_source: str,
	max_routes: Optional[int] = None,
	seed: int = 42,
) -> List[Dict[str, str]]:
	airports = load_airports(airports_source)
	all_valid: List[Dict[str, str]] = []
	seen_pairs: set[Tuple[str, str]] = set()

	reader = csv.reader(_read_source_lines(routes_source))
	for row in reader:
		if len(row) < 6:
			continue
		origin = row[2].strip().upper()
		destination = row[4].strip().upper()
		if len(origin) != 3 or len(destination) != 3:
			continue
		if origin not in airports or destination not in airports:
			continue
		if origin == destination:
			continue
		pair = (origin, destination)
		if pair in seen_pairs:
			continue

		distance_km = haversine_km(airports[origin], airports[destination])
		duration_min = estimate_duration_min(distance_km)

		all_valid.append(
			{
				"origin_iata": origin,
				"destination_iata": destination,
				"distance_km": f"{distance_km:.3f}",
				"est_duration_min": f"{duration_min:.3f}",
				"optional_price": "",
				"source": "openflights",
			}
		)
		seen_pairs.add(pair)

	if max_routes is None or max_routes >= len(all_valid):
		return all_valid

	rng = random.Random(seed)
	return rng.sample(all_valid, k=max_routes)


def write_routes_csv(rows: List[Dict[str, str]], output_path: str) -> None:
	fieldnames = [
		"origin_iata",
		"destination_iata",
		"distance_km",
		"est_duration_min",
		"optional_price",
		"source",
	]
	output = Path(output_path)
	output.parent.mkdir(parents=True, exist_ok=True)

	with output.open("w", encoding="utf-8", newline="") as file:
		writer = csv.DictWriter(file, fieldnames=fieldnames)
		writer.writeheader()
		writer.writerows(rows)
  
def write_airports_csv(rows: List[Dict[str, str]], output_path: str) -> None:
	fieldnames = [
		"iata",
		"latitude",
		"longitude",
	]

	output = Path(output_path)
	output.parent.mkdir(parents=True, exist_ok=True)

	with output.open("w", encoding="utf-8", newline="") as file:
		writer = csv.DictWriter(file, fieldnames=fieldnames)
		writer.writeheader()
		writer.writerows(rows)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Collect offline flight route data.")
	parser.add_argument("--airports-source", default=DEFAULT_AIRPORTS_SOURCE)
	parser.add_argument("--routes-source", default=DEFAULT_ROUTES_SOURCE)
	parser.add_argument("--output", default=DEFAULT_OUTPUT)
	parser.add_argument("--max-routes", type=int, default=5000)
	parser.add_argument("--seed", type=int, default=42)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	airports = load_airports(args.airports_source)
	airport_rows = [
		{
			"iata": iata,
			"latitude": f"{lat:.6f}",
			"longitude": f"{lon:.6f}",
		}
		for iata, (lat, lon) in airports.items()
	]
	write_airports_csv(airport_rows, "airports_raw.csv")
	print(f"Collected {len(airport_rows)} airports -> airports_raw.csv")
	routes = collect_routes(
		airports_source=args.airports_source,
		routes_source=args.routes_source,
		max_routes=args.max_routes,
		seed=args.seed,
	)
	write_routes_csv(routes, args.output)
	print(f"Collected {len(routes)} routes -> {args.output}")


if __name__ == "__main__":
	main()
