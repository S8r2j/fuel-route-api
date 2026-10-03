"""
Management command : geocode_stations

Assigns latitude/longitude to every FuelStation by matching its (state,city)
against the US Census Bureau Gazetteer places file.

The fuel price CSV has no coordinates and its addresses are highway exits
that geocoders handle poorly, so stations are placed at their city's centre.
This runs once at setup; the API never geocodes during a request.

Usage:
    python3 manage.py geocode_stations data/2024_Gaz_place_national.txt
"""

import csv
import re
import statistics
from collections import Counter, defaultdict, namedtuple
from math import asin, cos, radians, sin, sqrt

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from stations.models import FuelStation, CensusPlace
from stations.names import name_key

UNMATCHED_REPORT_LIMIT = 20

# takes the details of each place individually
Place = namedtuple("Place", ["name","lat","lon","is_statistical", "land_area"])

# Census has most town names with descriptor but a few have no.
# So, comparing the name from CSV to Census in two ways
MATCH_LEVELS = ("without_descriptor", "whole_name")




def place_keys(census_name):
    """
    Return the two comparison forms of a Census place name.
    eg: "Big Cabin town" -> {
            "without_descriptor": "bigcabin",
            "with_descriptor": "bigcabintown
        }

    Bracketed notes are not part of the name and are dropped
    first.
    """
    name = re.sub(r"\([^)]*\)", " ", census_name)
    words = name.split()
    return {
        "without_descriptor": name_key(" ".join(words[:-1])),
        "whole_name": name_key(name),
    }

def find_places(city, state_places):
    """
    Return the Census places whose name matches a station's city.

    The list is empty when the city is not in the file and has 
    several entries when places in the state share the name.

    Args:
        city: city name as written in the fuel price file
        state_places: the lookup for the station's state
    """
    key = name_key(city)

    for level in MATCH_LEVELS:
        places = state_places[level].get(key)
        if places:
            municipalities = [p for p in places if not p.is_statistical]
            return municipalities or places
        
    return []

def miles_between(lat1, lon1, lat2, lon2):
    """
    Return the great-circle distance between two points, in miles.
    """
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    a = (
        sin((lat2 - lat1)/2) ** 2
        +
        cos(lat1) * cos(lat2) * sin((lon2 - lon1)/2) ** 2
    )
    return 2 * settings.EARTH_RADIUS_MILES * asin(sqrt(a))

def nearest_point(centre, points):
    """
    Return the point in `points` closest to `centre`.
    """
    return min(points, key=lambda point: miles_between(*centre, *point))




class Command(BaseCommand):
    help = "Fill FuelStation lat/lon from a Census Gazetteer places file"

    def locate_columns(self, header, file_format):
        """
        Return the index of each required column in header row
        """
        columns = {}
        for field in ("state", "name", "lat", "lon", "status", "area"):
            column_name = file_format[f"{field}_column"]
            if column_name not in header:
                raise CommandError(
                    f"Gaxetteer file has no '{column_name}' column. Found: {header}"
                )
            columns[field] = header.index(column_name)
        return columns
    
    def rack_centres(self, located):
        """
        Return the median position of each rack's located stations.

        Rack is a terminal that supplies a station, so stations sharing a
        rack id are close together

        Returns:
            {rack id : (lat,lon)}
        """
        points_by_rack = defaultdict(list)
        for station, coords in located.items():
            points_by_rack[station.rack_id].append(coords)

        return {
            rack_id: (
                statistics.median(lat for lat,lon in points),
                statistics.median(lon for lat,lon in points),
            )
            for rack_id, points in points_by_rack.items()
            if rack_id is not None
        }
    
    def load_gazetteer(self, path):
        """
        Read the Gazetteer file into per-state lookup.

        Returns:
            (places_by_state,place_counts) where places_by_state is
            {state: {match_level: {key: [Place, ...]}}}
        """
        file_format = settings.GAZETTEER_FORMAT
        places_by_state = {}
        place_count = 0

        try:
            f = open(path, newline="", encoding=file_format["encoding"])
        except OSError as error:
            raise CommandError(f"Cannot open gazetteer file: {error}")
        
        with f:
            reader = csv.reader(f, delimiter=file_format["delimiter"], quoting=csv.QUOTE_NONE)
            header = [column.strip() for column in next(reader,[])]
            columns = self.locate_columns(header, file_format)

            for row in reader:
                if len(row) < len(header):
                    continue
                
                try:
                    lat = float(row[columns["lat"]])
                    lon = float(row[columns["lon"]])
                    land_area = float(row[columns["area"]])
                except ValueError:
                    raise CommandError(
                        f"Gazetteer file line {reader.line_num}: "
                        f"latitude/longitude is not a number"
                    )
                
                place = Place(
                    name=row[columns["name"]].strip(),
                    lat=lat,
                    lon=lon,
                    is_statistical=(
                        row[columns["status"]].strip() == file_format["statistical_status"]
                    ),
                    land_area=land_area,
                )
                place_count += 1

                state = row[columns["state"]].strip()
                state_places = places_by_state.setdefault(
                    state, {level: defaultdict(list) for level in MATCH_LEVELS}
                )
                for level, key in place_keys(place.name).items():
                    if key:
                        state_places[level][key].append(place)

            if place_count == 0:
                raise CommandError("Gazetteer file contains no places")
            
            return places_by_state, place_count
        
    def save_places(self, places_by_state):
        """
        Replace the CensusPlace table with the places just read
        """
        rows = []
        for state, levels in places_by_state.items():
            for places in levels["whole_name"].values():
                for place in places:
                    keys = place_keys(place.name)
                    rows.append(CensusPlace(
                        state=state,
                        name=place.name,
                        key=keys["without_descriptor"],
                        whole_key=keys["whole_name"],
                        lat=place.lat,
                        lon=place.lon,
                        is_statistical=place.is_statistical,
                        land_area=place.land_area,
                    ))
        
        with transaction.atomic():
            CensusPlace.objects.all().delete()
            CensusPlace.objects.bulk_create(
                rows, batch_size=settings.DB_BATCH_SIZE
            )
        
    def report(self, total, matched, outside, missing):
        """
        Print how many stations were located and why the others were not.
        """
        self.stdout.write(self.style.SUCCESS(
            f"Located {matched} of {total} stations"
        ))

        if outside:
            self.stdout.write(
                f"Not in the gazetteer's states: {sum(outside.values())} "
                f"stations ({', '.join(sorted(outside))})"
            )

        if missing:
            limit = UNMATCHED_REPORT_LIMIT
            self.stdout.write(
                f"City not found: {sum(missing.values())} stations in "
                f"{len(missing)} cities. Top {min(limit, len(missing))}:"
            )
            for (city,state), count in missing.most_common(limit):
                self.stdout.write(f"    {city}, {state}: {count}")

    def add_arguments(self, parser):
        parser.add_argument(
            "gazetteer_path",
            help = "Path to the Census Gazetteer places file",
        )

    def handle(self, *args, **options):
        places_by_state, place_count = self.load_gazetteer(
            options["gazetteer_path"]
        )
        self.stdout.write(
            f"Gazetteer: {place_count} places in {len(places_by_state)} states"
        )

        self.save_places(places_by_state)

        stations = list(FuelStation.objects.all())

        found = {}
        located = {}
        shared_name = []
        missing = Counter()
        outside = Counter()

        for station in stations:
            if station.state not in places_by_state:
                outside[station.state] += 1
                continue

            city = (station.city, station.state)
            if city not in found:
                found[city] = find_places(
                    station.city, places_by_state[station.state]
                )

            points = [(place.lat, place.lon) for place in found[city]]
            if not points:
                missing[city] +=1
            elif len(points) == 1:
                located[station] = points[0]
            else:
                shared_name.append((station,points))

        
        # Located stations show where each rack operates and the candidate nearest
        # to it is shown
        rack_centres = self.rack_centres(located)

        for station,points in shared_name:
            centre = rack_centres.get(station.rack_id)
            if centre is None:
                missing[(station.city, station.state)] += 1
            else:
                located[station] = nearest_point(centre, points)

        # write every station so that one which don't match won't keep coordinates
        for station in stations:
            station.lat, station.lon = located.get(station, (None, None))

        FuelStation.objects.bulk_update(
            stations, ["lat","lon"], batch_size=settings.DB_BATCH_SIZE
        )

        self.report(len(stations), len(located), outside, missing)