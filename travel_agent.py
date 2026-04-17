"""
Budget Travel Itinerary Planning Agent
First-Choice Hill Climbing with Two Layers of Optimization:
  Layer 1: Choose city visit order and flights using the flight cost and duration as the objective function.
  Layer 2: Choose attraction order for each city using the importance score as the objective function, allocate days/city
           using hill climbing with simulated annealing

Environment variables:
    SERPAPI_KEY         – from https://api.flightapi.io/register
    GOOGLE_PLACES_API_KEY – from https://console.cloud.google.com
"""

"""
GENERATIVE AI USE:

This file was reformatted with Claude AI to remove redundant code and to simplify the structure of our functions.
The planning of the project functionality and key functions necessary to be implemented, as well as the original functions 
were done without the use of generative AI, but the refactoring of the code for readability and debugging of the original code was 
done with the help of Claude AI. The output functions to print the output of our itinerary planning algorithm were obtained using 
Claude AI, with the following prompt:

The html generation code to display the output of our algorithm on the world amp was obtained through Claude AI with the
following prompt:
Make an html page to display the outputs of our algorithm on the world map. The page should include a map with pins for each city on the 
map, with a hover choice to display the flight and hotel rate information for each city. The page should include a side bar to display the 
attraction information for each city, as well as the attractoin costs and days allocated to each city. The page should also include a 
section for a budget breakdown and a summary of the flights to take.

"""

import math
import random
import os
from dataclasses import dataclass, field
from typing import Optional
import urllib.request
import urllib.parse
import json

"""
Obtains the API keys from the .env file, allows user to manually set environment variables in the terminal to run without a .env file
"""
def _load_env() -> None:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key   = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except FileNotFoundError:
        pass


_load_env()


# Import map and flight API data
from output_map import build_map_data, generate_map
from flights_api import (
    Airport, Flight,
    build_flight_data, make_api_key, fetch_hotel_rates,
)


"""
Data classes for the itinerary planning algorithm
"""
# Represents the estimated cost of an attraction based on its price level. 
# The price level is a rating form 0 to 4 that comes from the Google Places API, where 0 means free and 4 means very expensive.
PRICE_LEVEL_COST: dict[int, float] = {
    0: 0.0,    # free  (parks, churches, public squares and landmarks)
    1: 15.0,   # cheap (small museums and minor attractions)
    2: 30.0,   # moderate (larger museums and art galleries)
    3: 60.0,   # expensive (theme parks and attraction tours)
    4: 120.0,  # very expensive (luxury experiences like Disneyland, high-end shows and restaurants)
}

# Represents placeholder prices for major attractions in popular cities.
# Used when the Google Places API returns a price level of 0 for attractions that are 
# actually paid, common for some well known landmarks and museums.
KNOWN_COSTS: dict[str, float] = {
    # Paris
    "louvre":               22.0,
    "eiffel tower":         29.0,
    "arc de triomphe":      16.0,
    "musée d'orsay":        16.0,
    "versailles":           21.0,
    "centre pompidou":      15.0,
    "panthéon":             13.0,
    "sainte-chapelle":      13.0,
    "musée picasso":        14.0,
    # Rome
    "colosseum":            18.0,
    "coliseum":             18.0,
    "vatican museums":      20.0,
    "sistine chapel":       20.0,
    "castel sant'angelo":   15.0,
    "borghese gallery":     15.0,
    "roman forum":          18.0,
    "palatine hill":        18.0,
    # Tokyo
    "tokyo skytree":        22.0,
    "tokyo tower":          18.0,
    "teamlab":              32.0,
    "shinjuku gyoen":        5.0,
    "tokyo disneyland":     85.0,
    "tokyo disney":         85.0,
    "ghibli museum":        16.0,
    "edo-tokyo museum":      7.0,
    "tokyo national museum": 10.0,
    "imperial palace":       0.0,
    # London
    "tower of london":      34.0,
    "buckingham palace":    32.0,
    "kew gardens":          22.0,
    "warner bros":          55.0,
    # New York
    "metropolitan museum":  30.0,
    "museum of modern art":  28.0,
    "one world":            40.0,
    "statue of liberty":    24.0,
    "empire state":         44.0,
    # Barcelona
    "sagrada família":      26.0,
    "park güell":           10.0,
    "casa batlló":          35.0,
    "picasso museum":       14.0,
    # Amsterdam
    "rijksmuseum":          22.0,
    "van gogh museum":      22.0,
    "anne frank":           16.0,
    # General patterns
    "aquarium":             30.0,
    "zoo":                  25.0,
    "theme park":           75.0,
    "escape room":          35.0,
}

"""
Estimates the cost of an attraction based on its price level, obtained from the 
Google Places API and known costs for popular attractions.
"""
def estimate_attraction_cost(attr_name: str, price_level: int) -> float:

    name_lower = attr_name.lower()
    for keyword, cost in KNOWN_COSTS.items():
        if keyword in name_lower:
            return cost
    return PRICE_LEVEL_COST.get(price_level, 0.0)

"""
Data classes to represent attractions in each city and all available information about each city
"""
@dataclass
class Attraction:
    name: str
    rating: float          # 0.0 – 5.0
    review_count: int
    price_level: int       # 0 (free) – 4 (very expensive)
    types: list[str] = field(default_factory=list)
    score: float = 0.0     # computed importance score
    est_cost: float = 0.0  # estimated entry cost in USD

"""
Represents all information for a city, including the flights to get there, the attractions, hotel cost and number of days allocated to it
"""
@dataclass
class CityPlan:
    city: str
    days: int
    flight: Optional[Flight]
    attractions: list[Attraction] = field(default_factory=list)
    attraction_budget_spent: float = 0.0   # total estimated cost of included attractions
    hotel_nightly_rate: float = 0.0        # avg nightly hotel rate in USD
    hotel_total_cost: float = 0.0          # nightly_rate × days

"""
Represents category weights for attraction categories and price penalties for attractions based on their price levels.
0 represents a free attraction, while 4 represents a very expensive attraction, used in the calculation of the importance score.
"""

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

"""
Calculates the importance score of an attraction based on its rating, number of reviews, category and price level,
takes user budget into consideration. Rating, number of reviews, category, and price level are obtained from the Google Places API.
Returns a float value representing the importance score for a city.
Generative AI Usage: This function was tweaked with the help of Claude AI to improve the formula for the importance score, 
and to add the step to steepen the penalty if the budget per day is less than 100 USD.
"""
def attraction_importance(attr: Attraction, budget_per_day: float) -> float:
    if attr.rating == 0 and attr.review_count == 0:
        return 0.0

    # Max weight category for the attraction
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


"""
Optimization Layer 1 – First Choice Hill Climbing: city order
"""

"""
Calculates the flight cost between two cities using the flight data obtained from SerpAPI.
Returns the flight price if the route exists, or a large penalty value if it doesn't.
Generative AI Usage: This function was refactored with the help of Claude AI to simplify the logic and 
to debug the function to add a reverse lookup for routes that might not be found in the original direction.
"""
def flight_cost(origin: str, destination: str, flight_data: dict[tuple, Flight]) -> float:
    key = (origin.lower(), destination.lower())
    if key in flight_data:
        return flight_data[key].price
    # Try reverse (won't be used for routing but avoids KeyError in edge cases)
    return 999_999.0

"""
Calculates the objective function score for a given city order, start city, flight data, total days and budget.
The objective function combines total flight price, a penalty for excessive flight duration relative to trip length, 
and a penalty for exceeding the budget to minimize a total cost.
Generative AI Usage: This function was refactored with the help of Claude AI to simplify the logic and to add a penalty 
for excessive flight duration relative to the total trip length, which was not present in the original code. It was also used for
debugging the function to ensure that it correctly calculates the total flight price and applies the penalties correctly.
"""
def route_objective(
    order: list[str],
    start_city: str,
    flight_data: dict[tuple, Flight],
    total_days: int,
    budget: float,
) -> float:

    cities = [start_city] + order + [start_city]
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

    # Apply heavy penalty if total flight time consumes too much of the trip
    available_hours = total_days * 24
    if total_hours > available_hours * 0.4:
        total_price += (total_hours - available_hours * 0.4) * 50

    # Apply heavy penalty if budget is exceeded
    if total_price > budget:
        total_price += (total_price - budget) * 100

    return total_price

"""
Optimizes city visit order using first choice hill climbing using the route objective function to get a score. Randomly swaps
two cities to find a neighbor, and moves to the neighbor if it has a better score.
Generative AI Usage: This function was refactored with the help of Claude AI to simplify the logic and to add the ability to 
perform sideways moves, which was not present in the original algorithm. It was also used for debugging the function to ensure that it 
correctly generated neighbours and applied the first-choice logic.
"""
def first_choice_hill_climbing_route(
    cities: list[str],
    start_city: str,
    flight_data: dict[tuple, Flight],
    total_days: int,
    budget: float,
    max_iterations: int = 2000,
    max_sideways: int = 50,
) -> list[str]:

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


"""
Optimization Layer 1 – First Choice Hill Climbing: attraction order for each city
"""

"""
Ranks and sorts attractions using the importance score formula, returns the top 10 attractions with the highest importance scores using
first choice hill climbing. Swaps out one attraction for a neighbor with a better score and stops when there are no improving steps left.
Generative AI Usage: This function was refactored with the help of Claude AI to simplify the logic, to debug the function, and to add
simulated annealing to avoid local maxima, which was not present in the original algorithm. The simulated annealing allows the algorithm 
to accept worse neighbors with decaying probability.
"""

def rank_attractions(
    attractions: list[Attraction],
    budget_per_day: float,
    top_n: int = 10,
    max_iterations: int = 1000,
    initial_temp: float = 2.0,
    cooling_rate: float = 0.995,
) -> list[Attraction]:

    for attr in attractions:
        attr.score = attraction_importance(attr, budget_per_day)
 
    if len(attractions) <= top_n:
        return sorted(attractions, key=lambda a: a.score, reverse=True)
 
    # Start with random initial selection
    indices = list(range(len(attractions)))
    random.shuffle(indices)
    chosen   = set(indices[:top_n])
    unchosen = set(indices[top_n:])
    current_score = sum(attractions[i].score for i in chosen)
 
    # Track the best solution seen
    best_chosen = set(chosen)
    best_score  = current_score
 
    temp = initial_temp
 
    for _ in range(max_iterations):
        if temp < 0.01:
            break
 
        # Generate random neighbour
        swap_out = random.choice(list(chosen))
        swap_in  = random.choice(list(unchosen))
 
        neighbour_score = current_score - attractions[swap_out].score + attractions[swap_in].score
        delta = neighbour_score - current_score
 
        if delta > 0:
            accept = True
        else:
            # Accept worse neighbour with probability e^(delta / T)
            accept = random.random() < math.exp(delta / temp)
 
        if accept:
            chosen.remove(swap_out)
            unchosen.add(swap_out)
            chosen.add(swap_in)
            unchosen.remove(swap_in)
            current_score = neighbour_score
 
            # Update best if this is the highest score seen so far
            if current_score > best_score:
                best_score  = current_score
                best_chosen = set(chosen)
 
        # Update temperature
        temp *= cooling_rate
 
    result = [attractions[i] for i in best_chosen]
    return sorted(result, key=lambda a: a.score, reverse=True)






"""
Filters the ranked attraction list by the available budget for attractions in that city, includes as many attractions as possible
without exceeding the budget, and returns the included attractions and total spent on attractions. Uses a Greedy approach to include
attractions in order of their importance score until we run out of budget or reach the top attraction count of ten.
Generative AI Usage: This function was refactored with Claude AI to simplify the logic and debug.
"""

def filter_by_budget(
    ranked_attractions: list[Attraction],
    available_budget: float,
    top_n: int = 10,
) -> tuple[list[Attraction], float]:

    included = []
    spent = 0.0

    for attr in ranked_attractions:
        if len(included) >= top_n:
            break
        cost = estimate_attraction_cost(attr.name, attr.price_level)
        if spent + cost <= available_budget:
            attr.est_cost = cost
            included.append(attr)
            spent += cost

    return included, round(spent, 2)

"""
Allocates the total trip days across the cities using hill climbing with simulated annealing to find an allocation that maximises
total trip value based on the attraction scores and flight hours.
Generative AI Usage: This function was generated using Claude AI based on the following prompt to replace our original implementation
based on proportional allocation:
Write a Python function that distributes a fixed number of trip days across a list of cities using hill climbing with simulated annealing.
Each city needs to get at least 1 day and the total days has to equal the available days. Accept worse neighbors with decreasing probability 
to use simulated annealing. Return the best city/days allocation.
Claude AI was also used to comment this function to explain the logic and steps of the algorithm.
"""

def allocate_days(
    ordered_cities: list[str],
    city_attractions: dict[str, list[Attraction]],
    total_days: int,
    flight_hours: dict[str, float],
    max_iterations: int = 2000,
    initial_temp: float = 1.0,
    cooling_rate: float = 0.995,
) -> dict[str, int]:
    n = len(ordered_cities)
    if n == 0:
        return {}
 
    available = total_days
 
    # Precompute attraction score weights — floor at 1 so every city is valued
    weights: dict[str, float] = {
        city: sum(a.score for a in city_attractions.get(city, [])) or 1.0
        for city in ordered_cities
    }
 
    def objective(alloc: dict[str, int]) -> float:
        # sqrt gives diminishing returns while still rewarding more days in
        # richer cities — log was too flat and converged to equal distribution
        return sum(weights[c] * math.sqrt(alloc[c]) for c in ordered_cities)
 
    # Initial state: give every city 1 day, then distribute ALL remaining days
    # by cycling through cities in weight order until remainder is fully used
    alloc = {c: 1 for c in ordered_cities}
    remainder = available - n
    cities_by_weight = sorted(ordered_cities, key=lambda c: weights[c], reverse=True)
    while remainder > 0:
        for city in cities_by_weight:
            if remainder <= 0:
                break
            alloc[city] += 1
            remainder -= 1
 
    current_score = objective(alloc)
    best_alloc    = dict(alloc)
    best_score    = current_score
    temp          = initial_temp
 
    for _ in range(max_iterations):
        if temp < 0.01:
            break
 
        # Neighbour: move 1 day from one city to another
        # Only cities with more than 1 day can give a day away
        donors = [c for c in ordered_cities if alloc[c] > 1]
        if not donors:
            break
        give = random.choice(donors)
        take = random.choice([c for c in ordered_cities if c != give])
 
        alloc[give] -= 1
        alloc[take] += 1
        neighbour_score = objective(alloc)
        delta = neighbour_score - current_score
 
        if delta > 0 or random.random() < math.exp(delta / temp):
            # Accept — improvement always accepted, worse accepted with
            # probability e^(delta/T) that shrinks as temperature cools
            current_score = neighbour_score
            if current_score > best_score:
                best_score = current_score
                best_alloc = dict(alloc)
        else:
            # Reject — undo the move
            alloc[give] += 1
            alloc[take] -= 1
 
        temp *= cooling_rate
 
    return best_alloc
 

"""
Fetches attraction data from Google Places API for a given city, returns a list of Attraction objects with the needed information 
extracted from the API response.
Generative AI Usage: This function was debugged and revised with the help of Claude AI to replace our original implementation, which
did not correcly return an Attraction object and did not handle API errors.
"""

def fetch_attractions_google(city: str, api_key: str) -> list[Attraction]:
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

"""
Generates some mock attraction data for a city when the api key is not found to prevent crashes.
"""
def mock_attractions(city: str) -> list[Attraction]:
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

"""
Helper functions to get user input for the starting city, itinerary cities, budget and trip duration.
Generative AI Usage: Claude AI was used to refactor these functions to simplify the logic.
"""
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



"""
Prints the final itinerary including city order, days per city, flight details, hotel costs and attraction details.
Generative AI Usage: This function was generated using Claude AI based on the following prompt to create a clear CLI output
for users:
    Create a Python function that takes in a starting city, the city order, a plan for each city and a return flight, and prints a clear
    itinerary to the console including all information on flights, hotels and attractions per city.
"""
SEPARATOR = "─" * 60


def print_itinerary(start: str, ordered_cities: list[str], city_plans: dict[str, CityPlan], return_flight=None):
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

        # Hotel cost
        if plan.hotel_nightly_rate:
            print(f"\n  🏨  Hotel:    ~${plan.hotel_nightly_rate:.2f}/night × {plan.days} nights = ${plan.hotel_total_cost:.2f}")
        else:
            print(f"\n  🏨  Hotel:    no rate data")

        # Attractions
        print(f"\n  🗺  Top Attractions (ranked by importance):\n")
        if plan.attractions:
            for rank, attr in enumerate(plan.attractions, 1):
                stars = "★" * round(attr.rating) + "☆" * (5 - round(attr.rating))
                price_str = ["Free", "$", "$$", "$$$", "$$$$"][attr.price_level]
                cost_str  = "Free" if attr.est_cost == 0 else f"~${attr.est_cost:.0f}"
                print(f"    {rank:>2}. {attr.name}")
                print(f"        {stars}  {attr.rating:.1f}  |  {attr.review_count:,} reviews"
                      f"  |  {price_str} ({cost_str})  |  score: {attr.score:.2f}")
            print(f"\n        💸 Est. attraction spend: ${plan.attraction_budget_spent:.2f}")
        else:
            print("    No attraction data available.")

        print()

    # Return home
    print(f"  Return: {ordered_cities[-1]} → {start}")
    print(f"  {SEPARATOR}")
    if return_flight:
        stops_str = f"{return_flight.stops} stop{'s' if return_flight.stops != 1 else ''}" if return_flight.stops else "non-stop"
        print(f"  ✈  Flight:   {return_flight.origin_airport.name} ({return_flight.origin_airport.iata_code})")
        print(f"              → {return_flight.destination_airport.name} ({return_flight.destination_airport.iata_code})")
        print(f"      Airline:   {return_flight.airline}  |  {return_flight.flight_number}")
        print(f"      Departs:   {return_flight.departure_time}")
        print(f"      Arrives:   {return_flight.arrival_time}")
        print(f"      Duration:  {return_flight.duration:.1f} hrs  ({stops_str})")
        print(f"      Price:     ${return_flight.price:.2f}")
    else:
        print(f"  No return flight data found.")
    print()

    print(f"{'═'*60}\n")


"""
The main function gets the user input, runs the itinerary planning algorithm, and prints the final itinerary to the console.
The function also gets the flight data and calls the map generation functions to create the output map and generate the html file
to display the results on a world map. 
Generative AI Usage: This function was refactored with the help of Claude AI to debug the entire flow of the itinerary plannig algorithm,
and to get suggestions on the structure of the code in this section to make sure we called the functions in the right order. Claude AI was
also used to simplify the logic. It was also used to make sure that the function correctly integrated all the parts of the itinerary planning 
algorithm and produces a clear and readable output for the user.
"""

def main():
    print("\n╔════════════════════════════════════════════╗")
    print("║   Budget Travel Itinerary Planning Agent   ║")
    print("╚════════════════════════════════════════════╝\n")

    # Get user input
    start_city, dest_cities = get_cities()
    budget = get_budget()
    total_days = get_days()
    budget_per_day = budget / max(total_days, 1)

    google_api_key  = os.environ.get("GOOGLE_PLACES_API_KEY", "")
    use_real_attractions = bool(google_api_key)

    # Grab flight data from SerpAPI
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

    # Get and determine flights with hill climbing
    print("⏳ Optimising route (Layer 1 – Hill Climbing on flights)...")
    optimised_order = first_choice_hill_climbing_route(
        dest_cities, start_city, flight_data, total_days, budget
    )

    from datetime import date as _date, timedelta as _timedelta
    trip_start_date = _date.today() + _timedelta(days=30)

    # Get and determine attractions with hill climbing
    print("⏳ Ranking attractions per city (Layer 2 – Hill Climbing on importance)...\n")
    city_raw_attractions: dict[str, list] = {}

    for city in optimised_order:
        if use_real_attractions:
            raw = fetch_attractions_google(city, google_api_key)
        else:
            raw = mock_attractions(city)
        ranked = rank_attractions(raw, budget_per_day, top_n=10)
        city_raw_attractions[city] = ranked

    # Get return flight
    last_city = optimised_order[-1]
    return_flight = flight_data.get((last_city.lower(), start_city.lower()))

    # Allocate days using hill climbing
    flight_hours = {
        city: flight_data[(optimised_order[i - 1].lower() if i > 0 else start_city.lower(),
                           city.lower())].duration
        if (optimised_order[i - 1].lower() if i > 0 else start_city.lower(),
            city.lower()) in flight_data else 0.0
        for i, city in enumerate(optimised_order)
    }
    flight_hours["__return__"] = return_flight.duration if return_flight else 0.0
    day_alloc = allocate_days(optimised_order, city_raw_attractions, total_days, flight_hours)

    # Calculate budget remaining after all flights 
    outbound_cost = sum(
        flight_data.get(
            (optimised_order[i - 1].lower() if i > 0 else start_city.lower(), city.lower()),
            None
        ).price
        if flight_data.get(
            (optimised_order[i - 1].lower() if i > 0 else start_city.lower(), city.lower())
        ) else 0.0
        for i, city in enumerate(optimised_order)
    )
    return_cost = return_flight.price if return_flight else 0.0
    flight_cost_estimate = outbound_cost + return_cost

    # Fetch real hotel rates for each destination city
    hotel_rates = fetch_hotel_rates(
        cities=optimised_order,
        check_in=trip_start_date,
        days_per_city={city.lower(): day_alloc[city] for city in optimised_order},
        api_key=flight_api_key,
    )
    hotel_cost_estimate = sum(total for _, total in hotel_rates.values())

    # Calculate remaining budget after flights and hotels, then split across cities for attractions
    attraction_budget = max(0.0, budget - flight_cost_estimate - hotel_cost_estimate)
    per_city_attraction_budget = attraction_budget / max(len(optimised_order), 1)

    city_plans: dict[str, CityPlan] = {}
    prev_city = start_city
    for city in optimised_order:
        key = (prev_city.lower(), city.lower())
        flight = flight_data.get(key)
        nightly, total_hotel = hotel_rates.get(city.lower(), (0.0, 0.0))
        filtered, spent = filter_by_budget(
            city_raw_attractions[city],
            per_city_attraction_budget,
            top_n=10,
        )
        city_plans[city] = CityPlan(
            city=city,
            days=day_alloc[city],
            flight=flight,
            attractions=filtered,
            attraction_budget_spent=spent,
            hotel_nightly_rate=nightly,
            hotel_total_cost=total_hotel,
        )
        prev_city = city

    # Print the itinerary
    print_itinerary(start_city, optimised_order, city_plans, return_flight=return_flight)

    outbound_flight_cost   = sum(city_plans[c].flight.price for c in optimised_order if city_plans[c].flight)
    return_flight_cost     = return_flight.price if return_flight else 0.0
    total_flight_cost      = outbound_flight_cost + return_flight_cost
    total_hotel_cost       = sum(city_plans[c].hotel_total_cost for c in optimised_order)
    total_attraction_spend = sum(city_plans[c].attraction_budget_spent for c in optimised_order)
    total_spent            = total_flight_cost + total_hotel_cost + total_attraction_spend
    remaining_budget       = budget - total_spent

    print(f"  💰 Outbound flights:        ${outbound_flight_cost:.2f}")
    print(f"  💰 Return flight:           ${return_flight_cost:.2f}")
    print(f"  💰 Total flight cost:       ${total_flight_cost:.2f}")
    print(f"  💰 Hotel stays:             ${total_hotel_cost:.2f}")
    print(f"  💰 Est. attraction spend:   ${total_attraction_spend:.2f}")
    print(f"  ─────────────────────────────────────────")
    print(f"  💰 Total estimated spend:   ${total_spent:.2f}")
    print(f"  💰 Remaining budget:        ${remaining_budget:.2f}")
    print(f"  📅 Day breakdown:")
    for city in optimised_order:
        d = city_plans[city].days
        h = city_plans[city].hotel_total_cost
        s = city_plans[city].attraction_budget_spent
        print(f"       {city}: {d} day{'s' if d != 1 else ''}  |  hotel ~${h:.2f}  |  attractions ~${s:.2f}")
    if return_flight:
        print(f"       Return ({last_city} → {start_city}): {return_flight.duration:.1f}h travel")
    if total_spent > budget:
        print(f"\n  ⚠  OVER BUDGET: trip costs ${total_spent:.2f} but your budget is ${budget:.2f}.")
        print(f"     Minimum budget required: ${total_spent:.2f}")
    if not use_real_attractions:
        print("\n  ⚠  Attraction data is mocked. Set GOOGLE_PLACES_API_KEY to use real data.")
    print()

    # Call functions to generate the html map
    print("⏳ Generating map...")
    map_data = build_map_data(
        start_city=start_city,
        optimised_order=optimised_order,
        city_plans=city_plans,
        return_flight=return_flight,
        budget=budget,
        outbound_flight_cost=outbound_flight_cost,
        return_flight_cost=return_flight_cost,
        total_flight_cost=total_flight_cost,
        total_hotel_cost=total_hotel_cost,
        total_attraction_spend=total_attraction_spend,
        total_spent=total_spent,
        remaining_budget=remaining_budget,
    )
    generate_map(map_data)


if __name__ == "__main__":
    main()