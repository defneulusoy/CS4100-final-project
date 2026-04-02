from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


DEFAULT_INPUT = "routes_raw.csv"
DEFAULT_OUTPUT = "routes_clean.csv"
DEFAULT_GRAPH_OUTPUT = "route_graph.json"
DEFAULT_META_OUTPUT = "cleaning_meta.json"


def _is_valid_iata(code: str) -> bool:
	return len(code) == 3 and code.isalpha() and code.isupper()


def load_rows(path: str) -> List[Dict[str, str]]:
	with open(path, "r", encoding="utf-8", newline="") as file:
		reader = csv.DictReader(file)
		return list(reader)


def clean_rows(rows: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
	cleaned: Dict[Tuple[str, str], Dict[str, str]] = {}
	dropped_invalid = 0

	for row in rows:
		origin = row.get("origin_iata", "").strip().upper()
		destination = row.get("destination_iata", "").strip().upper()
		if not _is_valid_iata(origin) or not _is_valid_iata(destination) or origin == destination:
			dropped_invalid += 1
			continue

		try:
			distance = float(row.get("distance_km", "0"))
			duration = float(row.get("est_duration_min", "0"))
		except ValueError:
			dropped_invalid += 1
			continue

		if distance <= 0 or duration <= 0:
			dropped_invalid += 1
			continue

		key = (origin, destination)
		candidate = {
			"origin_iata": origin,
			"destination_iata": destination,
			"distance_km": f"{distance:.3f}",
			"est_duration_min": f"{duration:.3f}",
			"optional_price": row.get("optional_price", "").strip(),
			"source": row.get("source", "").strip() or "unknown",
		}

		existing = cleaned.get(key)
		if existing is None or float(candidate["est_duration_min"]) < float(existing["est_duration_min"]):
			cleaned[key] = candidate

	cleaned_list = sorted(cleaned.values(), key=lambda x: (x["origin_iata"], x["destination_iata"]))
	stats = {
		"input_rows": len(rows),
		"clean_rows": len(cleaned_list),
		"dropped_rows": dropped_invalid,
		"deduplicated_rows": len(rows) - dropped_invalid - len(cleaned_list),
	}
	return cleaned_list, stats


def build_graph(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, float]]:
	graph: Dict[str, Dict[str, float]] = defaultdict(dict)
	for row in rows:
		origin = row["origin_iata"]
		destination = row["destination_iata"]
		duration = float(row["est_duration_min"])
		graph[origin][destination] = duration
	return dict(graph)


def write_clean_csv(rows: List[Dict[str, str]], output_path: str) -> None:
	output = Path(output_path)
	output.parent.mkdir(parents=True, exist_ok=True)

	fieldnames = [
		"origin_iata",
		"destination_iata",
		"distance_km",
		"est_duration_min",
		"optional_price",
		"source",
	]

	with output.open("w", encoding="utf-8", newline="") as file:
		writer = csv.DictWriter(file, fieldnames=fieldnames)
		writer.writeheader()
		writer.writerows(rows)


def write_json(payload: Dict, output_path: str) -> None:
	output = Path(output_path)
	output.parent.mkdir(parents=True, exist_ok=True)
	with output.open("w", encoding="utf-8") as file:
		json.dump(payload, file, indent=2, sort_keys=True)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Clean collected flight route data.")
	parser.add_argument("--input", default=DEFAULT_INPUT)
	parser.add_argument("--output", default=DEFAULT_OUTPUT)
	parser.add_argument("--graph-output", default=DEFAULT_GRAPH_OUTPUT)
	parser.add_argument("--meta-output", default=DEFAULT_META_OUTPUT)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	rows = load_rows(args.input)
	cleaned, stats = clean_rows(rows)
	graph = build_graph(cleaned)

	write_clean_csv(cleaned, args.output)
	write_json(graph, args.graph_output)
	write_json(stats, args.meta_output)

	print(f"Cleaned {len(cleaned)} routes -> {args.output}")
	print(f"Graph nodes: {len(graph)} -> {args.graph_output}")
	print(f"Stats -> {args.meta_output}")


if __name__ == "__main__":
	main()
