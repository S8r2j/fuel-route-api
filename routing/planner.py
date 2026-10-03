"""
Plan a trip: the route, the fuel stops along it and what they cost
"""
import numpy as np
from django.core.cache import cache

from routing.fuel_plan import plan_fuel_stops
from routing.locations import resolve_location
from routing.osrm import fetch_route
from routing.stations_on_route import (
    miles_from_start,
    stations_near_route,
    thin,
)

# Caching already finished plan for 24 hours
CACHE_SECONDS = 60 * 60 * 24

# Route line sent back has about one point per mile
ROUTE_LINE_SPACING_MILES= 1

def plan_trip(start_text, finish_text):
    """
    Return the plan for a trip between two places.

    Args: 
        start_text : the start city
        finish_text : the last city
    """
    start = resolve_location(start_text)
    finish = resolve_location(finish_text)

    # key uses coordinates for caching
    key = "trip:{:.5f},{:.5f},{:.5f},{:.5f}".format(*start[:2], *finish[:2])
    plan = cache.get(key)
    if plan is None:
        plan = build_plan(start, finish)
        cache.set(key, plan, CACHE_SECONDS)
    return plan


def build_plan(start,finish):
    """
    Work out a plan from scratch.

    Args:
        start: (lat, lon, name) of start point
        finish: (lat, lon, name) of finish point
    """
    start_lat, start_lon, start_name = start
    finish_lat, finish_lon, finish_name = finish

    points, miles = fetch_route((start_lat, start_lon), (finish_lat,  finish_lon))
    stations = stations_near_route(points, miles)
    fuel = plan_fuel_stops(stations,miles)

    return {
        "start": { "name": start_name, "lat": start_lat, "lon": start_lon},
        "finish": {"name": finish_name, "lat": finish_lat, "lon": finish_lon},
        "distance_miles": round(miles, 1),
        "total_gallons": fuel["total_gallons"],
        "total_cost": fuel["total_cost"],
        "fuel_stops": fuel["stops"],
        "route": route_line(points, miles),
    }

def route_line(points, route_miles):
    """
    Return the route as a GeoJSON line with about one point per mile.
    """
    if len(points) == 0:
        return {"type": "LineString", "coordinates":[]}
    
    route = np.radians(np.asarray(points, dtype=np.float64))
    mile = miles_from_start(route[:, 0], route[:, 1], route_miles)
    kept = thin(mile, ROUTE_LINE_SPACING_MILES)

    return {
        "type": "LineString",
        "coordinates": [[points[i][1], points[i][0]] for i in kept],
    }