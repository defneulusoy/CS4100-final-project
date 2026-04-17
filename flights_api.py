"""
This file contains the functions to fetch flight data from SerpAPI and parse it into our data classes. The file also contains
data classes to represent the airports and flights from each airport, as well as a mapping of city names to IATA codes for the
most common cities and functions to fetch hotel rates for the cities in the inputted itinerary.The main function at the bottom 
is for testing the functionality of the API calls and data parsing in this file.

GENERATIVE AI USE:

This file was reformatted with Claude AI to remove redundant code and to simplify the structure of our functions.
The planning of the project functionality and key functions necessary to be implemented, as well as most of the original functions 
were coded without the use of generative AI, but the refactoring of the code for readability and debugging of the original code was 
done with the help of Claude AI. Some of the functions in this file to obtain data from SerpAPI were written with the help of Claude AI,
as indicated above the functions. Copilot was used throughout this file to assist with the autocompletion of individual lines and 
comments on the code.

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
Data class to represent the airports.

Generative AI usage:
The comments on the fields of the data class were generated with the help of Copilot autocompletion.
"""

@dataclass
class Airport:
    iata_code: str      # e.g. "CDG"
    name: str           # e.g. "Paris Charles de Gaulle Airport"
    city: str           # e.g. "Paris"

"""
Data class to represent a flight between two cities, including the origin and destination airports, and airline.

Generative AI usage:
The comments on the fields of the data class were generated with the help of Copilot autocompletion.
"""
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

"""
SerpAPI endpoint for Google Flights search, get request.

Generative AI usage:
The structure of the API request and the error handling for the API call were written with the help Claude AI. Claude AI was also
used to debug the requests.
"""

BASE = "https://serpapi.com/search"


def _get(params: dict) -> dict:
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


"""
Parses flight data from the SerpAPI response and converts data into the Flight dataclass format.
Returns a Flight object or None.

Generative AI usage: 
This function was written with the help of Claude AI to parse the flight data from the SerpAPI response 
and convert it into a structured format using the Flight dataclass. The comment below in the function was generated with the help of
Claude AI and Copilot to explain the structure of the API response.
"""

def _parse_offer(offer: dict, origin_city: str, dest_city: str) -> Optional[Flight]:
    """

    API response structure:
    {
      "flights": [
        {
          "departure_airport": { "name": "...", "id": "CDG", "time": "2025-09-01 08:30" },
          "arrival_airport":   { "name": "...", "id": "JFK", "time": "2025-09-01 11:55" },
          "airline": "Air France",
          "flight_number": "AF 334",
          "duration": 450
        },
        ...
      ],
      "total_duration": 450,
      "price": 389
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



"""
City name to IATA code mapping for common cities to allow users to put in city names instead of airport codes.

Generative AI usage: 
The most common cities and their primary airport codes were obtained through Claude AI with the following prompt: 
Give me a list of the most visited cities in the world and their primary airport IATA codes, formatted as a Python dictionary 
where the keys are city names and the values are the corresponding IATA codes.
"""

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


"""
Converts a city name to the IATA code for the primary airport in that city. Returs the code if the input is already a code.
Generative AI usage: This function was reformatted with the help of Claude AI to simplify the structure, add the ValueError.
"""
def city_to_iata(name: str) -> str:
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


"""
Searches for the cheapest flight between two cities on the given date.
Returns a Flight object or None.

Generative AI usage: 
This function was refactored with the help of Claude AI to simplify the structure and add error handling
with try/except blocks to catch potential errors from the API call and from the city-to-IATA conversion.
"""

def search_flight(
    origin_city: str,
    dest_city: str,
    depart_date: date,
    api_key: str,
) -> Optional[Flight]:

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

    # Pick cheapest flight
    flights = []
    for offer in candidates:
        f = _parse_offer(offer, origin_city, dest_city)
        if f:
            flights.append(f)

    if not flights:
        return None

    return min(flights, key=lambda f: f.price)


"""
Builds flight data for all routes in our itinerary by searching for the cheapest flight between each city pair.

Generative AI usage: 
The contents of this function were separated from the original code, and refactored with the help of Claude AI
into a separate function to build the flight data for the routes in our itinerary. The original code also had the hotel rate lookup mixed
in with building the flight data, which Claude AI helped to separate into two functions.
"""

def build_flight_data(
    start_city: str,
    dest_cities: list[str],
    api_key: str,
    trip_start_date: Optional[date] = None,
) -> tuple[dict[str, Airport], dict[tuple[str, str], Flight]]:

    if trip_start_date is None:
        # Searches for flights departing 30 days from now if there is no start date for the trip, which is for all our calculations
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

            # Populate airports dictionary from what the response gave us
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

        time.sleep(0.5)

    return airports, flights




"""
Gets the median hotel rate for the given city from SerpAPI and calculates the total cost based on the number of days spent in that city.
Uses 30 days from now as the check in date for the search.

Generative AI usage: 
This function was refactored with the help of Claude AI to simplify the structure and add error handling with try/except 
blocks to catch potential errors from the API call. The original code also had the flight data lookup mixed in with building the hotel rate data,
which Claude AI helped to separate into two functions. Claude AI was also used to debug the original code for this function.
"""

def fetch_hotel_rate(
    city: str,
    check_in: date,
    check_out: date,
    api_key: str,
) -> float:

    params = {
        "engine":          "google_hotels",
        "q":               f"hotels in {city}",
        "check_in_date":   check_in.strftime("%Y-%m-%d"),
        "check_out_date":  check_out.strftime("%Y-%m-%d"),
        "adults":          "1",
        "currency":        "USD",
        "hl":              "en",
        "gl":              "us",
        "sort_by":         "3", # 3 is the price sorting option
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

    # Collects nightly rates from the first 5 results for the hotels in a city
    rates = []
    for prop in properties[:5]:
        rpn = prop.get("rate_per_night", {})
        rate = rpn.get("extracted_lowest") or rpn.get("extracted_highest")
        if rate:
            rates.append(float(rate))

    if not rates:
        return 0.0

    # Gets median of all available hotel rates
    rates.sort()
    mid = len(rates) // 2
    if len(rates) % 2 == 0:
        return round((rates[mid - 1] + rates[mid]) / 2, 2)
    return round(rates[mid], 2)


"""
Gets the hotel rates for all itinerary cities and calculates the total cost of the stay in each city based on the number of days
spent and the check in date as 30 days from now. 

Generative AI usage: 
This function was refactored with the help of Claude AI to simplify the structure and add error handling with try/except
blocks to catch potential errors from the API call. The original code also had the flight data lookup mixed in with building the hotel rate data
and getting the rate for each city, which Claude AI helped to separate into three functions. Claude AI was also used to debug the original code 
for this function.
"""
def fetch_hotel_rates(
    cities: list[str],
    check_in: date,
    days_per_city: dict[str, int],
    api_key: str,
) -> dict[str, tuple[float, float]]:
    
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

"""
Gets the API key from the environment variable, raises error if key is not found.

Generative AI usage: 
This function was refactored with the help of Claude AI to add error handling by raising an EnvironmentError.
"""

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


"""
Main function executes flight data fetching for a sample itinerary.

Generative AI usage: 
This function was generated by Claude AI to help us test the functionality of the API calls and data parsing
in this file.
"""

if __name__ == "__main__":
    key = make_api_key()
    airports, flights = build_flight_data(
        start_city="New York",
        dest_cities=["London", "Paris"],
        api_key=key,
    )
    print(f"\n  {len(airports)} airports, {len(flights)} flight legs.")