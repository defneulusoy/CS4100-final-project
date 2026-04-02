import random
WEIGHTS = {
    "cost": 0.4,
    "travel_time": 0.3,
    "stay_value": 0.3
}

destinations = input("Enter your desired destinations (comma separated): ").split(",") # ask user for desired destinations
destinations = [d.strip() for d in destinations]

budget_limit = int(input("Enter your budget limit: ")) # ask user for budget limit
total_days = int(input("Enter total number of days for the trip: ")) # ask user for total number of days for the trip

# placeholder data for edges between cities, will replcae with real data
edge_data = {
    ("Paris", "Rome"): {"cost": 120, "time": 2.0},
    ("Rome", "Paris"): {"cost": 120, "time": 2.0},

    ("Paris", "Barcelona"): {"cost": 100, "time": 1.8},
    ("Barcelona", "Paris"): {"cost": 100, "time": 1.8},

    ("Rome", "Barcelona"): {"cost": 110, "time": 2.0},
    ("Barcelona", "Rome"): {"cost": 110, "time": 2.0},
}
def split_days_between_cities(num_cities, num_days):
    """Splits the number of days between the cities in a random way."""
    days = [0] * num_cities
    for _ in range(num_days):
        city_index = random.randint(0, num_cities - 1)
        days[city_index] += 1
    return days

def create_set(cities, num_days):
    route = cities[:]
    num_cities = len(cities)
    random.shuffle(route)
    days = split_days_between_cities(num_cities, num_days)
    route_day = {"city": route, "days": days}
    return route_day
    
def calculate_travel_cost_time(route):
    total_cost = 0
    total_time = 0
    for i in range(len(route) - 1):
        leg = (route[i], route[i + 1])
        if leg not in edge_data:
            return float("inf"), float("inf")
        total_cost += edge_data[leg]["cost"]
        total_time += edge_data[leg]["time"]
    return total_cost, total_time

def stay_cost(route, num_days):
    total_cost = 0
    for city, day in zip(route, num_days):
        total_cost += day * 50
    return total_cost

def get_city_value(city):
    data = get_places_data(city) # will replace with real data from api

    num_places = len(data)
    avg_rating = sum(p["rating"] for p in data) / len(data)
    total_reviews = sum(p["user_ratings_total"] for p in data)

    return num_places + avg_rating * 10 + (total_reviews ** 0.3)

def destination_reward(route, num_days):
    reward = 0
    stay_value. = 
    for city, day in zip(route, num_days):
        reward += day * get_city_value(city)
    return reward

def fitness(option):
    route = option["route"]
    num_days = option["days"]

    transition_cost, transition_time = calculate_travel_cost_time(route)
    stay_cost_value = stay_cost(route, num_days)
    total_cost = transition_cost + stay_cost_value
    reward = destination_reward(route, num_days)

    if transition_cost == float("inf"):
        return -10**9
    
        score = 0
    score -= WEIGHTS["cost"] * total_cost
    score -= WEIGHTS["travel_time"] * (transition_time * 100)  # scaled so it matters more
    score += WEIGHTS["stay_value"] * (reward * 50)

    if total_cost > budget_limit:
        score -= (total_cost - budget_limit) * 5  # penalty for going over budget
    return score

# pick best out of n random options
def selection(population, n=3):
    selected = random.sample(population, n)
    selected.sort(key=fitness, reverse=True)
    return selected[0]

# crossover for routes
def route_crossover(parent1, parent2):
    route1 = parent1["route"]
    route2 = parent2["route"]
    num_cities = len(route1)

    start, end = sorted(random.sample(range(num_cities), 2))
    child_route = [None] * num_cities
    child_route[start:end] = route1[start:end]

    p2_index = 0
    for i in range(num_cities):
        if child_route[i] is None:
            while route2[p2_index] in child_route:
                p2_index += 1
            child_route[i] = route2[p2_index]
    
    return child_route

def normalize_days(days, total_days):
    """
    Make sure all entries are >= 1 and sum to total_days.
    """
    days = [max(1, d) for d in days]
    current_sum = sum(days)

    while current_sum > total_days:
        idx = random.choice([i for i, d in enumerate(days) if d > 1])
        days[idx] -= 1
        current_sum -= 1

    while current_sum < total_days:
        idx = random.randint(0, len(days) - 1)
        days[idx] += 1
        current_sum += 1

    return days

def crossover(parent1, parent2):
    child_route = route_crossover(parent1["route"], parent2["route"])

    # Mix days positionally
    child_days = []
    for d1, d2 in zip(parent1["days"], parent2["days"]):
        child_days.append(random.choice([d1, d2]))

    # Fix total days if needed
    child_days = normalize_days(child_days, total_days)

    return {"route": child_route, "days": child_days}


def mutate(option, day_mutation_rate=0.2, route_mutation_rate=0.2):
    route = option["route"][:]
    days = option["days"][:]

    # Mutate route
    if random.random() < route_mutation_rate:
        idx1, idx2 = random.sample(range(len(route)), 2)
        route[idx1], route[idx2] = route[idx2], route[idx1]

    # Mutate days
    for i in range(len(days)):
        if random.random() < day_mutation_rate:
            change = random.choice([-1, 1])
            days[i] = max(1, days[i] + change)

    # Fix total days if needed
    days = normalize_days(days, total_days)

    return {"route": route, "days": days}


def genetic_algorithm(
    destinations,
    total_days,
    population_size=30,
    generations=100,
    elite_size=2
):
    population = [create_set(destinations, total_days) for _ in range(population_size)]

    for generation in range(generations):
        population.sort(key=fitness, reverse=True)

        next_population = population[:elite_size]  # keep best few

        while len(next_population) < population_size:
            parent1 = selection(population)
            parent2 = selection(population)

            child = crossover(parent1, parent2)
            child = mutate(child)

            next_population.append(child)

        population = next_population

    best = max(population, key=fitness)
    return best

def print_solution(solution):
    route = solution["route"]
    days = solution["days"]

    transit_cost, transit_time = calculate_travel_cost_time(route)
    hotel_cost = stay_cost(route, days)
    total_cost = transit_cost + hotel_cost

    print("Best itinerary found:")
    print("Route:", " -> ".join(route))
    print("Days per city:")
    for city, d in zip(route, days):
        print(f"  {city}: {d} day(s)")
    print(f"Transit cost: ${transit_cost}")
    print(f"Lodging cost: ${hotel_cost}")
    print(f"Total cost:   ${total_cost}")
    print(f"Transit time: {transit_time:.1f} hours")
    print(f"Fitness:      {fitness(solution):.2f}")

    

if __name__ == "__main__":
    best_solution = genetic_algorithm(destinations, total_days)
    print_solution(best_solution)