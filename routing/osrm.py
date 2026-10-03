"""
Get a driving route from the OSRM routing service/engine
"""
import requests
from django.conf import settings

TIMEOUT_SECONDS = 20
METRES_PER_MILE = 1609.344
POLYLINE_PRECISION = 1e5    # 1e5 = 100,000 OSRM encodes coordinates to 5 decimal, so to compute original co-ords need to divide with this


class RoutingError(Exception):
    """
    Raised when OSRM cannot be reached or finds no route.
    """

def fetch_route(start, finish):
    """
    Return the driving route between two (lat,lon) points.

    Calls the external OSRM routing engine.

    Returns:
        (points, miles): the route as a list of (lat,lon)
    """
    coordinates = f"{start[1]},{start[0]};{finish[1]},{finish[0]}"
    try:
        response = requests.get(
            f"{settings.OSRM_URL}/route/v1/driving/{coordinates}",
            params={"overview": "full", "geometries": "polyline"},  # overview full means detailed route line & geometries polyline means getting whole data in single string format
            timeout=TIMEOUT_SECONDS,
        )
        body = response.json()
    except requests.RequestException as error:
        raise RoutingError(f"The routing service did not answer: {error}")

    if body.get("code") != "Ok" or not body.get("routes"):
        reason = body.get("message") or body.get("code") or "no route"
        raise RoutingError(f"The routing service found no route: {reason}")
    
    route = body["routes"][0]
    return decode_polyline(route["geometry"]), route["distance"] / METRES_PER_MILE

def decode_polyline(encoded):
    """
    Return the list (lat,lon) points of an encoded polyline.

    OSRM sends the whole route as one short string to keep its answer small
    and we need to convert this characters based string into co-ordinates.

    eg:
    "_p~iF~ps|U_u1LnnqC"    ->  [(38.5,-120.2), (40.7, -120.95)]
    
    """
    points = []
    lat = lon = 0
    index = 0

    while index < len(encoded):
        # text holds 2 numbers for every point: how much latitude and longitude
        # changed since previous point
        changes = []
        for _ in ("lat","lon"):
            value = shift = 0
            while True:
                chunk = ord(encoded[index]) - 63    # converting the character as number
                index += 1
                value |= (chunk & 0b11111) << shift
                shift += 5
                if chunk < 32:                      # chink below 32, marks the last character
                    break
            
            # number's last bit is its sign: 1 means it is negative
            changes.append(~(value >> 1) if value & 1 else value >> 1)

        # add the changes to the previous point to get this point
        # then turn it back to degree
        lat += changes[0]
        lon += changes[1]
        points.append((lat / POLYLINE_PRECISION, lon / POLYLINE_PRECISION))

    return points