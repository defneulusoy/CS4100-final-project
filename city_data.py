"""API clients for city resolution, flight pricing, and attractions.

Required environment variables (in .env):
    SERPAPI_KEY          – from https://serpapi.com/          (Google Flights)
    GOOGLE_PLACES_KEY   – from https://console.cloud.google.com/  (Places API)
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

from models import Attraction, City, Flight

load_dotenv()

# ---------------------------------------------------------------------------
# City / airport resolution  (built-in IATA lookup)
# ---------------------------------------------------------------------------

# IATA codes are stable identifiers – like zip codes.  The dynamic data
# (ticket prices, attractions) still comes from live APIs.
_CITY_DB: Dict[str, Tuple[str, str, float, float]] = {
    # key (lowercase) -> (display name, IATA, lat, lon)
    "new york":       ("New York",       "JFK", 40.6413, -73.7781),
    "nyc":            ("New York",       "JFK", 40.6413, -73.7781),
    "new york city":  ("New York",       "JFK", 40.6413, -73.7781),
    "los angeles":    ("Los Angeles",    "LAX", 33.9425, -118.4081),
    "la":             ("Los Angeles",    "LAX", 33.9425, -118.4081),
    "chicago":        ("Chicago",        "ORD", 41.9742, -87.9073),
    "houston":        ("Houston",        "IAH", 29.9902, -95.3368),
    "phoenix":        ("Phoenix",        "PHX", 33.4373, -112.0078),
    "philadelphia":   ("Philadelphia",   "PHL", 39.8744, -75.2424),
    "san antonio":    ("San Antonio",    "SAT", 29.5337, -98.4698),
    "san diego":      ("San Diego",      "SAN", 32.7338, -117.1933),
    "dallas":         ("Dallas",         "DFW", 32.8998, -97.0403),
    "san jose":       ("San Jose",       "SJC", 37.3626, -121.9290),
    "austin":         ("Austin",         "AUS", 30.1975, -97.6664),
    "jacksonville":   ("Jacksonville",   "JAX", 30.4941, -81.6879),
    "san francisco":  ("San Francisco",  "SFO", 37.6213, -122.3790),
    "sf":             ("San Francisco",  "SFO", 37.6213, -122.3790),
    "columbus":       ("Columbus",       "CMH", 39.9999, -82.8919),
    "indianapolis":   ("Indianapolis",   "IND", 39.7173, -86.2944),
    "charlotte":      ("Charlotte",      "CLT", 35.2140, -80.9431),
    "seattle":        ("Seattle",        "SEA", 47.4502, -122.3088),
    "denver":         ("Denver",         "DEN", 39.8561, -104.6737),
    "washington":     ("Washington DC",  "DCA", 38.8512, -77.0402),
    "dc":             ("Washington DC",  "DCA", 38.8512, -77.0402),
    "nashville":      ("Nashville",      "BNA", 36.1263, -86.6774),
    "oklahoma city":  ("Oklahoma City",  "OKC", 35.3931, -97.6007),
    "boston":         ("Boston",         "BOS", 42.3656, -71.0096),
    "portland":       ("Portland",       "PDX", 45.5898, -122.5951),
    "las vegas":      ("Las Vegas",      "LAS", 36.0840, -115.1537),
    "vegas":          ("Las Vegas",      "LAS", 36.0840, -115.1537),
    "memphis":        ("Memphis",        "MEM", 35.0424, -89.9767),
    "louisville":     ("Louisville",     "SDF", 38.1744, -85.7360),
    "baltimore":      ("Baltimore",      "BWI", 39.1774, -76.6684),
    "milwaukee":      ("Milwaukee",      "MKE", 42.9472, -87.8966),
    "albuquerque":    ("Albuquerque",    "ABQ", 35.0402, -106.6091),
    "tucson":         ("Tucson",         "TUS", 32.1161, -110.9410),
    "fresno":         ("Fresno",         "FAT", 36.7762, -119.7181),
    "sacramento":     ("Sacramento",     "SMF", 38.6954, -121.5908),
    "atlanta":        ("Atlanta",        "ATL", 33.6407, -84.4277),
    "miami":          ("Miami",          "MIA", 25.7959, -80.2870),
    "new orleans":    ("New Orleans",    "MSY", 29.9934, -90.2580),
    "tampa":          ("Tampa",          "TPA", 27.9756, -82.5333),
    "orlando":        ("Orlando",        "MCO", 28.4312, -81.3081),
    "minneapolis":    ("Minneapolis",    "MSP", 44.8848, -93.2223),
    "detroit":        ("Detroit",        "DTW", 42.2162, -83.3554),
    "salt lake city": ("Salt Lake City", "SLC", 40.7899, -111.9791),
    "slc":            ("Salt Lake City", "SLC", 40.7899, -111.9791),
    "honolulu":       ("Honolulu",       "HNL", 21.3245, -157.9251),
    "pittsburgh":     ("Pittsburgh",     "PIT", 40.4957, -80.2413),
    "st louis":       ("St. Louis",      "STL", 38.7487, -90.3700),
    "saint louis":    ("St. Louis",      "STL", 38.7487, -90.3700),
    "kansas city":    ("Kansas City",    "MCI", 39.2976, -94.7139),
    "raleigh":        ("Raleigh",        "RDU", 35.8776, -78.7875),
    "cleveland":      ("Cleveland",      "CLE", 41.4058, -81.8539),
    "cincinnati":     ("Cincinnati",     "CVG", 39.0488, -84.6678),
}


def resolve_city_name(text: str) -> Optional[City]:
    """Resolve a city name like 'Boston' or 'NYC' to a City object."""
    key = text.strip().lower()
    entry = _CITY_DB.get(key)
    if entry is None:
        return None
    name, iata, lat, lon = entry
    return City(name=name, iata=iata, lat=lat, lon=lon)

# ---------------------------------------------------------------------------
# Flight search  (SerpApi – Google Flights)
# ---------------------------------------------------------------------------

_flight_cache: Dict[Tuple[str, str], Flight] = {}


def _serpapi_key() -> str:
    key = os.environ.get("SERPAPI_KEY", "")
    if not key:
        raise EnvironmentError(
            "Set SERPAPI_KEY in your .env file.\n"
            "Sign up free at https://serpapi.com/"
        )
    return key


def get_flight(origin_iata: str, dest_iata: str, date: str = "2026-06-15") -> Flight:
    """Get the cheapest one-way flight between two IATA codes.

    Uses SerpApi Google Flights engine.
    Results are cached per city pair for the session.
    """
    cache_key = (origin_iata, dest_iata)
    if cache_key in _flight_cache:
        return _flight_cache[cache_key]

    try:
        resp = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google_flights",
                "departure_id": origin_iata,
                "arrival_id": dest_iata,
                "outbound_date": date,
                "type": "2",          # one-way
                "currency": "USD",
                "hl": "en",
                "gl": "us",
                "api_key": _serpapi_key(),
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Flight search failed {origin_iata}->{dest_iata}: {exc}"
        ) from exc

    # Collect the cheapest from best_flights + other_flights
    all_flights = data.get("best_flights", []) + data.get("other_flights", [])
    if not all_flights:
        raise RuntimeError(
            f"No flights found {origin_iata}->{dest_iata} on {date}. "
            f"Try a different date or city."
        )

    best = min(all_flights, key=lambda f: f.get("price", float("inf")))
    price = float(best.get("price", 0))
    duration_min = float(best.get("total_duration", 0))

    flight = Flight(
        origin=origin_iata,
        destination=dest_iata,
        price_usd=round(price, 2),
        duration_min=round(duration_min, 1),
    )
    _flight_cache[cache_key] = flight
    return flight

# ---------------------------------------------------------------------------
# Attractions  (Google Places API – Text Search)
# ---------------------------------------------------------------------------

_attraction_cache: Dict[str, List[Attraction]] = {}


def _google_places_key() -> str:
    key = os.environ.get("GOOGLE_PLACES_KEY", "")
    if not key:
        raise EnvironmentError(
            "Set GOOGLE_PLACES_KEY in your .env file.\n"
            "Enable Places API at https://console.cloud.google.com/"
        )
    return key


def get_attractions(city: City, limit: int = 10) -> List[Attraction]:
    """Fetch top attractions near a city via Google Places Text Search."""
    cache_key = city.iata
    if cache_key in _attraction_cache:
        return _attraction_cache[cache_key]

    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={
                "query": f"top attractions in {city.name}",
                "location": f"{city.lat},{city.lon}",
                "radius": 30000,
                "type": "tourist_attraction",
                "key": _google_places_key(),
            },
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except requests.RequestException as exc:
        print(f"  [warn] Attractions lookup failed for {city.name}: {exc}")
        _attraction_cache[cache_key] = []
        return []

    attractions: List[Attraction] = []
    for place in results[:limit]:
        name = place.get("name", "Unknown")
        types = place.get("types", [])
        category = types[0].replace("_", " ") if types else "attraction"
        address = place.get("formatted_address", "")

        price = _estimate_attraction_price(category)

        attractions.append(Attraction(
            name=name,
            cost_usd=price,
            category=category,
            address=address,
        ))

    _attraction_cache[cache_key] = attractions
    return attractions


def _estimate_attraction_price(category: str) -> float:
    """Rough admission estimate based on place type."""
    cat_lower = category.lower()
    if any(w in cat_lower for w in ["park", "trail", "garden", "beach", "bridge", "plaza"]):
        return 0.0
    if any(w in cat_lower for w in ["museum", "gallery", "aquarium", "zoo"]):
        return 25.0
    if any(w in cat_lower for w in ["theme park", "amusement"]):
        return 80.0
    if any(w in cat_lower for w in ["tour", "cruise", "boat"]):
        return 45.0
    if any(w in cat_lower for w in ["monument", "memorial", "historic", "landmark", "church", "cathedral"]):
        return 0.0
    return 15.0
