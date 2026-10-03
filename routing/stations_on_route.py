"""
Find fuel stations that lie along a route.
"""
from functools import lru_cache

import numpy as np
from django.conf import settings

from stations.models import FuelStation

# OSRM provides the route points within about 400 feet.
# So, thinning the route points for every 8 miles only
COARSE_SPACING_MILES = 8
FINE_SPACING_MILES = 1

@lru_cache(maxsize=1)
def load_stations():
    """
    Return every station that has coordinates

    The stations are read from db once and then kept in memory as
    its only changed when the setup commands are run.

    Returns:
        (stations, lat, lon): a list of station dicts and their 
        coordinates
    """
    stations = list(
        FuelStation.objects.filter(lat__isnull=False).values(
            "opis_id", "name", "address", "city", "state", "price", "lat", "lon",
        )
    )
    for station in stations:
        station["price"] = float(station["price"])

    lat = np.radians([s["lat"] for s in stations], dtype=np.float32)
    lon = np.radians([s["lon"] for s in stations], dtype=np.float32)

    return stations, lat, lon


def stations_near_route(points, route_miles):
    """
    Return the stations close to ta route, in the order they are passed.

    Station counts as close when it is within STATION_MAX_DETOUR_MILES of
    the route, measured in a straight line.

    Args:
        points: the route as a list of coords
        route_miles: the length of the route

    Returns:
        A list of station dicts
    """
    stations, station_lat, station_lon = load_stations()
    if not stations or len(points) == 0 :
        return []
    
    route = np.radians(np.asarray(points, dtype=np.float64))
    route_lat, route_lon = route[:, 0], route[:, 1]
    mile = miles_from_start(route_lat, route_lon, route_miles)
    limit = settings.STATION_MAX_DETOUR_MILES

    # Pass 1: Keep the stations that could be within the limit. Station
    # within limit of route is at most one coarse step further
    # from nearest coarse point
    coarse = thin(mile, COARSE_SPACING_MILES)
    _, off_route = nearest_route_point(
        station_lat, station_lon, route_lat[coarse], route_lon[coarse]
    )
    candidates = np.flatnonzero(off_route <= limit + COARSE_SPACING_MILES)

    # Exact pass over the candidates
    fine = thin(mile, FINE_SPACING_MILES)
    nearest, off_route = nearest_route_point(
        station_lat[candidates], station_lon[candidates], route_lat[fine], route_lon[fine],
    )

    found = []

    for station_index, point, miles_off in zip(candidates, nearest, off_route):
        if miles_off <= limit:
            found.append({
                **stations[station_index],
                "route_mile": round(float(mile[fine[point]]), 1),
                "miles_off_route": round(float(miles_off), 1),
            })

    found.sort(key = lambda station: station["route_mile"])
    return found


def miles_from_start(route_lat, route_lon, route_miles):
    """
    Return how far along the route each point is, in miles.

    Distances between neighbouring points are added up, then
    scaled so the last point is exactly at route_miles
    """
    lat1, lat2 = route_lat[:-1], route_lat[1:]
    lon1, lon2 = route_lon[:-1], route_lon[1:]
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        +
        np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2 ) ** 2
    )
    steps = 2 * settings.EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))

    mile = np.concatenate(([0.0], np.cumsum(steps)))
    if mile[-1] > 0:
        mile *= route_miles / mile[-1]

    return mile

def thin(mile, spacing):
    """
    Return the indexes of route points about `spacing` miles apart

    First & last points are always included
    """
    marks = np.arange(0, mile[-1], spacing)
    indexes = np.searchsorted(mile,marks)
    return np.unique(np.append(indexes, len(mile)-1))


def nearest_route_point(station_lat, station_lon, route_lat, route_lon):
    """
    For each station, return the nearest route point and the miles to it.

    All inputs are in radians. Distances treat the fround as flat, which
    is accurate to a few feet at the short distances that matter here

    Returns:
        (indexes, miles): two arrays with one entry per station
    """
    route_lat = route_lat.astype(np.float32)
    route_lon = route_lon.astype(np.float32)

    # One row per station and one column per route point
    north = station_lat[:, None] - route_lat[None, :]
    east = station_lon[:, None] - route_lon[None, :]
    east = east * np.cos(station_lat)[:, None]
    squared = north * north + east * east

    indexes = squared.argmin(axis=1)
    nearest_squared = squared[np.arange(len(indexes)), indexes]
    return indexes, settings.EARTH_RADIUS_MILES * np.sqrt(nearest_squared)