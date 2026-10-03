# Fuel Route API

A Django API that takes a start and a finish inside the USA and returns the
driving route, the cheapest places to refuel along it (500-mile range,
10 miles per gallon), and the total fuel cost.

This file covers how to run it, how to call it, how it works and why it was
built this way. What the project takes as true about the data and the trip
is listed separately in [ASSUMPTIONS.md](ASSUMPTIONS.md).

## Setup

Needs Python 3.12 or newer (Django 6.1). No API key and no sign-up is needed.

```
pip install -r requirements.txt
python manage.py migrate
python manage.py load_stations data/fuel-prices.csv
python manage.py geocode_stations data/2024_Gaz_place_national.txt
python manage.py runserver
```

Two data files go in `data/`:

- `fuel-prices.csv`: the price list supplied with the assignment.
- `2024_Gaz_place_national.txt`: the US Census Bureau Gazetteer "Places"
  file, a free download from
  https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html

The two commands that read them are run once. Restart the server if you run
them again.

## Using it

| Address | Returns |
|---|---|
| `GET /api/route/?start=Dallas, TX&finish=Chicago, IL` | The plan as JSON |
| `GET /map/?start=Dallas, TX&finish=Chicago, IL` | The same plan drawn on a map (open in a browser) |

`start` and `finish` are each written as `City, ST` or `lat,lon`.

The response, shortened to one fuel stop and one route point:

```json
{
  "start": {"name": "Dallas city, TX", "lat": 32.793333, "lon": -96.766513},
  "finish": {"name": "Chicago city, IL", "lat": 41.837045, "lon": -87.684939},
  "distance_miles": 961.0,
  "total_gallons": 46.1,
  "total_cost": 133.07,
  "fuel_stops": [
    {
      "opis_id": 68213,
      "name": "CADOO MILLS",
      "address": "I-30/US-67, EXIT 87 & FM-1903",
      "city": "Caddo Mills",
      "state": "TX",
      "price": 2.801,
      "lat": 33.074543,
      "lon": -96.226924,
      "route_mile": 39.1,
      "miles_off_route": 3.5,
      "gallons": 3.91,
      "cost": 10.95
    }
  ],
  "map_url": "http://127.0.0.1:8000/map/?start=Dallas%2C+TX&finish=Chicago%2C+IL",
  "route": {"type": "LineString", "coordinates": [[-96.76651, 32.79333]]}
}
```

| Field | Meaning |
|---|---|
| `start`, `finish` | The place that was matched and its coordinates |
| `fuel_stops` | Where to buy fuel, in travel order |
| `route_mile` | How far along the route the stop is |
| `miles_off_route` | How far the stop is from the road line |
| `gallons`, `cost` | What is bought at that stop |
| `map_url` | The map page for the same trip |
| `route` | The road line as GeoJSON, `[longitude, latitude]` |

Errors come back as `{"error": "..."}`:

| Status | Meaning |
|---|---|
| 400 | `start` or `finish` is missing, badly written, or a city that was not found |
| 422 | The trip cannot be fuelled: a stretch with no station is longer than the range |
| 502 | The routing service failed or found no road between the two places |

## How it works

At setup, once:

1. `load_stations` reads the price file into the database, one row per station.
2. `geocode_stations` gives each station coordinates from the Census file,
   and saves the Census places for looking up a start or finish later.

On each request:

| Step | File | What it does |
|---|---|---|
| 1 | `routing/locations.py` | Turns the start and finish into coordinates, from the database |
| 2 | `routing/osrm.py` | Asks OSRM for the road line and its length. The only external call |
| 3 | `routing/stations_on_route.py` | Finds the stations near that line and how far along it each one is |
| 4 | `routing/fuel_plan.py` | Chooses where to buy and how much, for the lowest cost |

`routing/planner.py` runs the four steps and caches the result.
`routing/views.py` turns it into the JSON response and the map page.

## Settings

All in `config/settings.py`:

| Setting | Value | Meaning |
|---|---|---|
| `VEHICLE_RANGE_MILES` | 500 | Miles on a full tank |
| `VEHICLE_MPG` | 10 | Miles per gallon |
| `STATION_MAX_DETOUR_MILES` | 10 | How near the route a station must be |
| `START_FUEL_FRACTION` | 1.0 | Fuel at the start: 1.0 is a full tank, 0.0 is empty |
| `OSRM_URL` | public server | Set the `OSRM_URL` environment variable to use your own OSRM server |

## Decisions

Each one lists the options that were considered and why one was chosen.

### 1. Where station coordinates come from

The price file has no coordinates, and a station can only be checked against
a route if it has them. Its `Address` column is a highway direction
("I-44, EXIT 283 & US-69"), not a street address. Every row does have a city
and a state.

| Method | Result when checked | Decision |
|---|---|---|
| Look up the city in the Census places file | 6,213 of 6,626 US stations (93.8%), about 3 seconds, no network | **Chosen** |
| Look up the city with an online geocoder (OpenStreetMap) | Raised coverage to 99.8% when added to the Census file | Rejected: needs network and 10–15 minutes at setup, results can change, sometimes picks a same-named town |
| Look up the address with an online geocoder | 5 of 6 real addresses returned nothing | Rejected: geocoders cannot read highway exits |
| Google Maps | Not run | Rejected: needs a billing account; its terms limit stored coordinates to 30 days and forbid a non-Google map |
| A ready-made dataset (US DOT Truck Stop Parking) | 1,915 public rest areas, no commercial stations | Rejected: nothing to match |
| Look up the exit number in OpenStreetMap data | Not run | Rejected: only about half the addresses have an exit number, and it needs network |

The Census file was chosen because one rule covers every row, it needs no
outside service, it gives the same answer on every run, and the data is
public. What this choice gives up is in ASSUMPTIONS.md, section 2.

### 2. Which routing service

OpenStreetMap is map data and has no routing service of its own; both
engines below are built on its data.

| | OSRM public server | OpenRouteService |
|---|---|---|
| Open source, OpenStreetMap data | Yes | Yes |
| API key | None | Required (free sign-up) |
| Limits | 1 request per second, non-commercial use, no uptime guarantee | Daily quota |

OSRM is chosen because a reviewer can run the project with no sign-up. Its
weakness is that the public server can be unavailable, so the call has a
20-second timeout (`TIMEOUT_SECONDS` in `routing/osrm.py`) and `OSRM_URL`
can point at any other OSRM server.

### 3. How much of the route line to fetch

Measured against the public OSRM server:

| Request | Dallas to Chicago (961 mi) | New York to Los Angeles (2,810 mi) |
|---|---|---|
| Simplified line | 29 points | 53 points |
| Full line as GeoJSON | 9,470 points, 0.7 to 0.85 s | 35,142 points, 1.2 to 2.1 s |
| Full line as encoded polyline | same points, 0.5 to 0.6 s | same points, 0.5 to 0.85 s |

The simplified line is too coarse: with one point every 30 to 50 miles it
cannot show which stations are near the road. The full line is fetched, as
an encoded polyline because that is the faster of the two full formats.

### 4. How the start and finish are given

The brief asks for one call to the routing service if possible.

| Option | External calls per request | Decision |
|---|---|---|
| "City, ST" looked up in the Census places saved at setup, or "lat,lon" | 1 (routing only) | **Chosen** |
| Any address, through an online geocoder | 2 to 3 | Rejected: breaks the one-call target |

A city name shared by several places in one state has to be settled somehow.

| Option | Decision |
|---|---|
| Pick one place by a fixed rule and name it in the response | **Chosen** |
| Refuse, and ask the user to send coordinates | Rejected: never wrong, but costs every such user a second request |

The rule itself is ASSUMPTIONS.md 3.9.

### 5. How the fuel stops are chosen

One rule is applied at every station along the route, in travel order:

- if a cheaper station can be reached on a full tank, buy only enough to
  get to it;
- otherwise fill the tank, because every later gallon would cost more.

The finish counts as cheaper than any station, so the truck never buys more
than it needs to arrive.

| Option | Decision |
|---|---|
| The rule above | **Chosen**: gives the lowest possible cost, in 0.4 ms |
| A general optimiser (linear programming) | Not used in the API: same answer, but slower and one more dependency. Used to check the rule |

The check: on 5,000 random routes the rule and the optimiser agreed on which
routes can be driven at all, and on the cost of every one that can.

Example, Dallas to Chicago, on a saved copy of the real OSRM route (961
miles, 189 stations within 10 miles of it):

| Mile | Station | Price | Gallons | Cost |
|---|---|---|---|---|
| 39.7 | Cadoo Mills, Caddo Mills TX | $2.801 | 3.97 | $11.12 |
| 160.0 | Extra Mile Truck Stop, Hooks TX | $2.817 | 12.03 | $33.89 |
| 172.0 | Quiktrip #7900, Texarkana TX | $2.857 | 1.20 | $3.43 |
| 649.1 | Hucks Food & Fuel #379, Marion IL | $2.929 | 28.90 | $84.66 |
| | **Total** | | **46.10** | **$133.10** |

Prices on that route run from $2.801 to $3.999, with a median of $3.299.
A live request returned $133.07; the few cents come from the stops sitting a
fraction of a mile differently on the live route line.

### 6. How the map is delivered

The brief asks for a map of the route.

| Option | Calls the API makes | Decision |
|---|---|---|
| Send the route line and stops as data, and give a page that draws them with Leaflet on OpenStreetMap tiles | 1 (OSRM) | **Chosen** |
| Ask a static-map service for a picture of the route | 2 | Rejected: a second call, and the free ones need a key |

The route line in the response is thinned to one point per mile. For Dallas
to Chicago that is 962 points and 21 KB, instead of 9,470 points and about
200 KB.

### 7. Where finished plans are cached

| Option | Decision |
|---|---|
| Django's in-memory cache | **Chosen**: nothing to install |
| Redis | Rejected: shares plans between server processes and keeps them across restarts, but a reviewer would have to install and run it |

A plan is stored under the coordinates of its start and finish, so
"Dallas, TX" and "dallas,tx" share one entry. The map page reads the same
entry, so opening the map after calling the API makes no second OSRM call.

## Speed

The one OSRM call takes 0.5 to 0.85 seconds and is outside the project's
control. Everything else is kept to a few hundredths of a second:

| Technique | Where | Effect, measured |
|---|---|---|
| Stations kept in memory (`lru_cache`) | `load_stations` | Read from the database once; every later request 0 ms |
| Route thinned to one point per mile | `stations_near_route` | 35,142 route points become about 2,800 |
| Rough pass, then exact pass | `stations_near_route` | The 6,213 stations are cut to about 200 candidates before the exact check |
| Flat-ground distance instead of the great-circle formula | `nearest_route_point` | Within 0.05 miles of the exact result on a real route |
| Finished plans cached for 24 hours | `plan_trip` | A repeated trip makes no OSRM call |

Measured on the Dallas to Chicago route (9,470 points), with the OSRM call
left out:

| Request | Time |
|---|---|
| First request after the server starts | 90 ms |
| A new trip after that | 16 to 19 ms |
| A trip asked for again | 3 ms |

So a new trip takes the OSRM call plus about 20 ms.

Finding the stations on a 2,810-mile route takes about 25 ms. The plain
approach, every station against every route point with the great-circle
formula, took 560 ms. On a real 395-mile route (Tulsa to St. Louis) the fast
and the plain approach found the same 58 stations.