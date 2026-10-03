"""
Choose where to refuel along a route so that fuel costs the least
"""
from django.conf import settings

# Arithmetic on decimal miles can be off by a tiny fraction (492.3 can come out as 
# 492.299999999999995). Distances are compared with this much slack so that such
# diff is not mistaken for running out of fuel
SLACK_MILES = 1e-6


class FuelPlanError(Exception):
    """
    Raised when the stations on the route are too far apart to drive it.
    """

def plan_fuel_stops(stations, route_miles):
    """
    Return the cheapest fuel stops for a route and the total cost

    Truck starts with START_FUEL_FRACTION of a tank and can drive
    VEHICLE_RANGE_MILES on a full one. At every station on the way,
    on rule decides how much to buy:
        - a cheaper station can be reached on a full tank : 
            buy only enough to get to it
        - nothing cheaper within reach :
            fill the tank since every later gallon would cost more

    Args:
        stations: station dicts with route_mile and price
        route_miles: length of the route

    Returns:
        {"stops": [...], "total_gallons": ..., "total_cost": ...}
    """
    tank_miles = settings.VEHICLE_RANGE_MILES
    mpg = settings.VEHICLE_MPG

    # finish is added as a last station that is cheaper than all others
    finish = {"route_mile": route_miles, "price": float("-inf")}
    # A station at the finish is left out: nothing is bought on arrival.
    before_finish = [s for s in stations if s["route_mile"] < route_miles]
    # Stations in the same town share a mile; the cheapest is visited first.
    ahead = sorted(before_finish, key=lambda s: (s["route_mile"], s["price"]))
    ahead.append(finish)

    stops = []
    position = 0.0

    # Fuel is counted as the miles the truck can still drive
    fuel = tank_miles * settings.START_FUEL_FRACTION

    for index,station in enumerate(ahead):
        # drive to this station
        distance = station["route_mile"] - position
        if distance > fuel + SLACK_MILES:
            raise FuelPlanError(
                f"No fuel station between mile {position: .0f} and mile "
                f"{station['route_mile']:.0f}; the truck can drive "
                f"{fuel:.0f} miles from there"
            )
        fuel -= distance
        position = station["route_mile"]
        if station is finish:
            break

        # decide how much to buy here
        cheaper = next_cheaper_station(ahead, index, tank_miles)
        if cheaper:
            wanted = cheaper["route_mile"] - position
        else:
            wanted = tank_miles

        if wanted > fuel + SLACK_MILES:
            gallons = (wanted - fuel) / mpg
            stops.append({
                **station,
                "gallons": round(gallons, 2),
                "cost": round(gallons * station["price"], 2),
            })
            fuel = wanted

    total_gallons = sum((stop["gallons"] for stop in stops), 0.0)
    total_cost = sum((stop["cost"] for stop in stops), 0.0)
    return{
        "stops": stops,
        "total_gallons": round(total_gallons, 2),
        "total_cost": round(total_cost, 2),
    }

def next_cheaper_station(ahead, index, tank_miles):
    """
    Return the first station after ahead[index] that is cheaper than it
    and within a full tank of it or None if there is none
    """
    here = ahead[index]
    for station in ahead[index + 1:]:
        if station["route_mile"] - here["route_mile"] > tank_miles:
            return None
        if station["price"] < here["price"]:
            return station
    return None