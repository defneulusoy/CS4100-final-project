"""
flights_api.py  –  Flight data via SerpAPI Google Flights
==========================================================
Uses a single SerpAPI endpoint per route:
    GET https://serpapi.com/search?engine=google_flights
        &departure_id=<IATA>
        &arrival_id=<IATA>
        &outbound_date=<YYYY-MM-DD>
        &type=2          (one-way)
        &currency=USD
        &api_key=<key>

What you get back per route (all from one call):
    - Departure airport name + IATA code
    - Arrival airport name + IATA code
    - Airline name + flight number
    - Departure time + arrival time
    - Duration in minutes → converted to hours
    - Number of stops
    - Price in USD  ← real Google Flights pricing data


Set before running:
    export SERPAPI_KEY=your_api_key

Note: SerpAPI takes city names and resolves them to IATA codes itself,
so no separate airport-lookup call is needed. You can also pass a city
name as departure_id / arrival_id and it will match the nearest airport.
"""

"""
GENERATIVE AI USE:
This file was reformatted with Claude AI to remove redundant code and to simplify the structure of our functions.
The planning of the project functionality and key functions necessary to be implemented, as well as the original functions 
were done without the use of generative AI, but the refactoring of the code for readability and debugging of the original code was 
done with the help of Claude AI. Some of the functions in this file to obtain data from SerpAPI were written with the help of Claude AI,
as indicated above the functions.



"""


import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from dataclasses import dataclass
from datetime import date, timedelta, datetime
from typing import Optional


"""
Data classes to represent the airports and flights from each airport.
"""

@dataclass
class Airport:
    iata_code: str      # e.g. "CDG"
    name: str           # e.g. "Paris Charles de Gaulle Airport"
    city: str           # e.g. "Paris"


@dataclass
class Flight:
    origin: str                   # city name
    destination: str              # city name
    origin_airport: Airport
    destination_airport: Airport
    airline: str                  # e.g. "Air France"
    flight_number: str            # e.g. "AF 334"
    departure_time: str           # e.g. "2025-09-01 08:30"
    arrival_time: str             # e.g. "2025-09-01 11:55"
    duration: float               # hours
    price: float                  # USD
    stops: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Low-level HTTP helper
# ─────────────────────────────────────────────────────────────────────────────

BASE = "https://serpapi.com/search"


def _get(params: dict) -> dict:
    """Fire a GET request to SerpAPI and return parsed JSON."""
    qs = urllib.parse.urlencode(params)
    url = f"{BASE}?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"SerpAPI HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}") from e


# ─────────────────────────────────────────────────────────────────────────────
# Parse a single flight offer from Google Flights JSON
# ─────────────────────────────────────────────────────────────────────────────

def _parse_offer(offer: dict, origin_city: str, dest_city: str) -> Optional[Flight]:
    """
    Extract a Flight from one entry in best_flights or other_flights.

    Google Flights response structure:
    {
      "flights": [                      ← list of legs (1 = direct, 2+ = connecting)
        {
          "departure_airport": { "name": "...", "id": "CDG", "time": "2025-09-01 08:30" },
          "arrival_airport":   { "name": "...", "id": "JFK", "time": "2025-09-01 11:55" },
          "airline": "Air France",
          "flight_number": "AF 334",
          "duration": 450             ← minutes for this leg
        },
        ...
      ],
      "total_duration": 450,           ← total minutes incl. layovers
      "price": 389                     ← USD
    }
    """
    legs = offer.get("flights", [])
    if not legs:
        return None

    price = offer.get("price")
    if not price:
        return None

    total_minutes = offer.get("total_duration") or sum(l.get("duration", 0) for l in legs)
    duration_hours = round(total_minutes / 60, 2)
    stops = len(legs) - 1

    # First leg departure, last leg arrival
    first_leg = legs[0]
    last_leg  = legs[-1]

    dep_ap_raw = first_leg.get("departure_airport", {})
    arr_ap_raw = last_leg.get("arrival_airport", {})

    origin_airport = Airport(
        iata_code=dep_ap_raw.get("id", "???"),
        name=dep_ap_raw.get("name", dep_ap_raw.get("id", "Unknown Airport")),
        city=origin_city.title(),
    )
    dest_airport = Airport(
        iata_code=arr_ap_raw.get("id", "???"),
        name=arr_ap_raw.get("name", arr_ap_raw.get("id", "Unknown Airport")),
        city=dest_city.title(),
    )

    departure_time = dep_ap_raw.get("time", "N/A")
    arrival_time   = arr_ap_raw.get("time", "N/A")

    # Airline + flight number from first leg
    airline       = first_leg.get("airline", "Unknown")
    flight_number = first_leg.get("flight_number", "N/A")

    return Flight(
        origin=origin_city.title(),
        destination=dest_city.title(),
        origin_airport=origin_airport,
        destination_airport=dest_airport,
        airline=airline,
        flight_number=flight_number,
        departure_time=departure_time,
        arrival_time=arrival_time,
        duration=duration_hours,
        price=float(price),
        stops=stops,
    )



# ─────────────────────────────────────────────────────────────────────────────
# City name → IATA code lookup
# ─────────────────────────────────────────────────────────────────────────────

# Primary airport for the world's most-visited cities.
# If a user's city isn't here, they can type the IATA code directly instead.
CITY_TO_IATA: dict[str, str] = {
    # North America
    "boston": "BOS", "new york": "JFK", "new york city": "JFK", "nyc": "JFK",
    "los angeles": "LAX", "la": "LAX", "chicago": "ORD", "miami": "MIA",
    "san francisco": "SFO", "seattle": "SEA", "washington": "IAD",
    "washington dc": "IAD", "atlanta": "ATL", "dallas": "DFW",
    "houston": "IAH", "denver": "DEN", "las vegas": "LAS", "orlando": "MCO",
    "toronto": "YYZ", "montreal": "YUL", "vancouver": "YVR",
    "mexico city": "MEX", "cancun": "CUN",
    # Europe
    "london": "LHR", "paris": "CDG", "rome": "FCO", "amsterdam": "AMS",
    "berlin": "BER", "madrid": "MAD", "barcelona": "BCN", "lisbon": "LIS",
    "frankfurt": "FRA", "zurich": "ZRH", "geneva": "GVA", "vienna": "VIE",
    "brussels": "BRU", "stockholm": "ARN", "oslo": "OSL", "copenhagen": "CPH",
    "helsinki": "HEL", "athens": "ATH", "istanbul": "IST", "dublin": "DUB",
    "munich": "MUC", "milan": "MXP", "venice": "VCE", "prague": "PRG",
    "budapest": "BUD", "warsaw": "WAW", "kiev": "KBP", "kyiv": "KBP",
    "zurich": "ZRH", "nice": "NCE", "edinburgh": "EDI",
    # Asia
    "tokyo": "NRT", "osaka": "KIX", "beijing": "PEK", "shanghai": "PVG",
    "hong kong": "HKG", "singapore": "SIN", "bangkok": "BKK",
    "seoul": "ICN", "taipei": "TPE", "kuala lumpur": "KUL",
    "jakarta": "CGK", "manila": "MNL", "delhi": "DEL", "mumbai": "BOM",
    "bangalore": "BLR", "dubai": "DXB", "abu dhabi": "AUH", "doha": "DOH",
    "riyadh": "RUH", "tel aviv": "TLV", "karachi": "KHI",
    # Africa
    "cairo": "CAI", "nairobi": "NBO", "johannesburg": "JNB",
    "cape town": "CPT", "casablanca": "CMN", "lagos": "LOS",
    "addis ababa": "ADD", "accra": "ACC",
    # Oceania
    "sydney": "SYD", "melbourne": "MEL", "brisbane": "BNE",
    "auckland": "AKL", "perth": "PER",
    # South America
    "sao paulo": "GRU", "rio de janeiro": "GIG", "rio": "GIG",
    "buenos aires": "EZE", "bogota": "BOG", "lima": "LIM",
    "santiago": "SCL", "caracas": "CCS",
}


def city_to_iata(name: str) -> str:
    """
    Convert a city name to its primary airport IATA code.
    If the input is already a 3-letter uppercase code, returns it as-is.
    Raises ValueError if the city isn't in the lookup table.
    """
    # Already an IATA code
    if len(name) == 3 and name.isupper():
        return name

    key = name.strip().lower()
    if key in CITY_TO_IATA:
        return CITY_TO_IATA[key]

    raise ValueError(
        f"Unknown city '{name}'. "
        f"Either add it to CITY_TO_IATA in flights_api.py, "
        f"or enter the IATA code directly (e.g. 'BOS' for Boston)."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Single route search
# ─────────────────────────────────────────────────────────────────────────────

def search_flight(
    origin_city: str,
    dest_city: str,
    depart_date: date,
    api_key: str,
) -> Optional[Flight]:
    """
    Search Google Flights for the cheapest one-way option between two cities.
    City names are passed directly — SerpAPI resolves them to IATA codes.
    Returns a Flight object or None if no results found.
    """
    try:
        dep_iata = city_to_iata(origin_city)
        arr_iata = city_to_iata(dest_city)
    except ValueError as e:
        print(f"    [!] {e}")
        return None

    params = {
        "engine":        "google_flights",
        "departure_id":  dep_iata,
        "arrival_id":    arr_iata,
        "outbound_date": depart_date.strftime("%Y-%m-%d"),
        "type":          "2",          # 1 = round trip, 2 = one-way
        "currency":      "USD",
        "hl":            "en",
        "api_key":       api_key,
    }

    try:
        data = _get(params)
    except RuntimeError as e:
        print(f"    [!] {origin_city} → {dest_city}: {e}")
        return None

    # best_flights are Google's top picks; other_flights are the rest
    candidates = data.get("best_flights", []) + data.get("other_flights", [])
    if not candidates:
        return None

    # Pick cheapest by price
    flights = []
    for offer in candidates:
        f = _parse_offer(offer, origin_city, dest_city)
        if f:
            flights.append(f)

    if not flights:
        return None

    return min(flights, key=lambda f: f.price)


# ─────────────────────────────────────────────────────────────────────────────
# High-level builder  (called by travel_agent.py)
# ─────────────────────────────────────────────────────────────────────────────

def build_flight_data(
    start_city: str,
    dest_cities: list[str],
    api_key: str,
    trip_start_date: Optional[date] = None,
) -> tuple[dict[str, Airport], dict[tuple[str, str], Flight]]:
    """
    Fetch the cheapest one-way flight for every ordered city pair that could
    appear in the itinerary.

    SerpAPI credit cost: 1 per route.
    Example — 4 cities (1 start + 3 destinations) = 12 routes = 12 credits.

    Returns:
        airports : dict[city_lower → Airport]   (populated from flight results)
        flights  : dict[(orig_lower, dest_lower) → Flight]
    """
    if trip_start_date is None:
        # Default: 30 days from today so prices are realistic
        trip_start_date = date.today() + timedelta(days=30)

    all_cities = [start_city] + dest_cities

    airports: dict[str, Airport] = {}
    flights:  dict[tuple[str, str], Flight] = {}

    legs = [
        (o, d)
        for o in all_cities
        for d in all_cities
        if o.lower() != d.lower()
    ]

    print(f"\n  Fetching flight prices for {len(legs)} route(s) "
          f"(departure ~{trip_start_date})...")

    for orig, dest in legs:
        label = f"{orig} → {dest}"
        flight = search_flight(orig, dest, trip_start_date, api_key)
        if flight:
            key = (orig.lower(), dest.lower())
            flights[key] = flight

            # Populate airports dict from what the response gave us
            airports[orig.lower()] = flight.origin_airport
            airports[dest.lower()] = flight.destination_airport

            stops_label = f"{flight.stops} stop{'s' if flight.stops != 1 else ''}" \
                          if flight.stops else "non-stop"
            print(
                f"    {label:30s}  ${flight.price:>7.2f}  "
                f"{flight.duration:>4.1f}h  {stops_label:<10}  "
                f"{flight.flight_number}  ({flight.airline})"
            )
        else:
            print(f"    {label:30s}  no results")

        time.sleep(0.5)   # be polite to the API

    return airports, flights



# ─────────────────────────────────────────────────────────────────────────────
# Hotel rate lookup  (Google Hotels via SerpAPI)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_hotel_rate(
    city: str,
    check_in: date,
    check_out: date,
    api_key: str,
) -> float:
    """
    Fetch the median nightly hotel rate for a city using the Google Hotels API.

    Searches for hotels sorted by lowest price, takes the cheapest 5 results,
    and returns their median rate — giving a representative mid-range cost
    rather than an outlier cheapest or most expensive option.

    SerpAPI credit cost: 1 per call.

    Returns 0.0 if no results or on error.
    """
    params = {
        "engine":          "google_hotels",
        "q":               f"hotels in {city}",
        "check_in_date":   check_in.strftime("%Y-%m-%d"),
        "check_out_date":  check_out.strftime("%Y-%m-%d"),
        "adults":          "1",
        "currency":        "USD",
        "hl":              "en",
        "gl":              "us",
        "sort_by":         "3",   # 3 = lowest price
        "api_key":         api_key,
    }
    try:
        data = _get(params)
    except RuntimeError as e:
        print(f"    [!] Hotel rate fetch failed for {city}: {e}")
        return 0.0

    properties = data.get("properties", [])
    if not properties:
        return 0.0

    # Collect nightly rates from the first 5 results
    rates = []
    for prop in properties[:5]:
        rpn = prop.get("rate_per_night", {})
        rate = rpn.get("extracted_lowest") or rpn.get("extracted_highest")
        if rate:
            rates.append(float(rate))

    if not rates:
        return 0.0

    # Median of available rates
    rates.sort()
    mid = len(rates) // 2
    if len(rates) % 2 == 0:
        return round((rates[mid - 1] + rates[mid]) / 2, 2)
    return round(rates[mid], 2)


def fetch_hotel_rates(
    cities: list[str],
    check_in: date,
    days_per_city: dict[str, int],
    api_key: str,
) -> dict[str, tuple[float, float]]:
    """
    Fetch nightly hotel rates for all destination cities.

    Returns:
        dict[city_lower → (nightly_rate, total_stay_cost)]
    """
    results: dict[str, tuple[float, float]] = {}
    print(f"\n  Fetching hotel rates for {len(cities)} city/cities...")

    for city in cities:
        days = days_per_city.get(city.lower(), 1)
        check_out = check_in + timedelta(days=days)
        rate = fetch_hotel_rate(city, check_in, check_out, api_key)
        total = round(rate * days, 2)
        results[city.lower()] = (rate, total)
        if rate:
            print(f"    {city:20s}  ${rate:.2f}/night × {days} nights = ${total:.2f}")
        else:
            print(f"    {city:20s}  no hotel data")
        time.sleep(0.5)

    return results

# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────

def make_api_key(key: str = "") -> str:
    """Return key from argument or SERPAPI_KEY env var."""
    k = key or os.environ.get("SERPAPI_KEY", "")
    if not k:
        raise EnvironmentError(
            "SerpAPI key not found.\n"
            "  Set the SERPAPI_KEY environment variable, or\n"
            "  sign up free (100 searches/month) at https://serpapi.com/users/sign_up"
        )
    return k


# ─────────────────────────────────────────────────────────────────────────────
# Quick standalone test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    key = make_api_key()
    airports, flights = build_flight_data(
        start_city="New York",
        dest_cities=["London", "Paris"],
        api_key=key,
    )
    print(f"\n  {len(airports)} airports, {len(flights)} flight legs.")