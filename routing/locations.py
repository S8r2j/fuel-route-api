"""
Turn a start or finish given by API user into coordinates
"""
from stations.models import CensusPlace
from stations.names import name_key

class LocationError(ValueError):
    """Raised when a start or finish cannot be turned into coordinates"""

def _find_city(city,state):
    """
    Return (lat,lon,label) for one city
    """
    key = name_key(city)
    in_state = CensusPlace.objects.filter(state=state)

    places = list(in_state.filter(key=key))
    if not places:
        places = list(in_state.filter(whole_key=key))
    places = [p for p in places if not p.is_statistical] or places

    if not places:
        raise LocationError(f"'{city}, {state}' was not found")
    
    place = max(places, key=lambda place: place.land_area)
    return place.lat, place.lon, f"{city}, {state}"

def resolve_location(text):
    """
    Return (lat,lon,label) for a text based location

    City is looked up in CensusPlace to reduce the dependency on external API
    """
    first, comma, second = text.rpartition(",")
    first, second = first.strip(), second.strip()
    if not comma or not first or not second:
        raise LocationError(
            f"'{text}' must be written as 'City, ST' or 'lat,lon'"
        )
    try:
        lat, lon = float(first), float(second)
    except ValueError:
        return _find_city(first, second.upper())
    
    if not (-90 <= lat <=90 and -180 <= lon <= 180):
        raise LocationError(f"'{text}' is not a valid latitude,longitude")
    return lat,lon, f"{lat}, {lon}"