from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Attraction:
    name: str
    cost_usd: float
    category: str
    address: str = ""


@dataclass
class City:
    name: str
    iata: str
    lat: float
    lon: float


@dataclass
class Flight:
    origin: str
    destination: str
    price_usd: float
    duration_min: float


@dataclass
class TripRequest:
    origin: str
    destinations: List[str]
    budget_usd: float
    total_days: int


@dataclass
class TripState:
    """A candidate solution: ordered destinations + day allocation."""
    city_order: List[str]
    days_per_city: List[int]


@dataclass
class TripResult:
    origin: str
    city_order: List[str]
    days_per_city: List[int]
    flights: List[Flight]
    total_flight_cost: float
    total_attraction_cost: float
    total_cost: float
    attractions_by_city: Dict[str, List[Attraction]]
    budget_usd: float
    total_days: int
    score: float
