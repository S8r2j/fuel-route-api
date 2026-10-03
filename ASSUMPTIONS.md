# Assumptions

Every assumption the project makes, with the numbers behind it.
Sections 1 and 2 cover the data. Section 3 covers the route endpoint.
Everything described here is built.

Numbers were measured on `fuel-prices.csv` and
`2024_Gaz_place_national.txt` (US Census Bureau Gazetteer, places).

## 1. Fuel price file

| # | Assumption | Numbers |
|---|---|---|
| 1.1 | One station per `OPIS Truckstop ID`. Rows that repeat an ID are the same station. | 8,151 rows, 6,738 unique IDs, 1,413 repeat rows. No repeated ID disagrees on address, city or state. |
| 1.2 | When a station has several prices, the lowest is used. | 597 IDs have more than one price. The gap is usually about $0.06 and at most $0.90. |
| 1.3 | When a station has several names, the name on the kept (lowest-price) row is used. | 227 IDs have more than one name, e.g. "PILOT TRAVEL CENTER #1243" and "PILOT #1243". |
| 1.4 | `Retail Price` is US dollars per gallon and is current. The file has no date or unit. | Prices range from $2.687 to $6.399. |
| 1.5 | Prices are stored to 3 decimal places. | Rounding changes a price by less than $0.001. |
| 1.6 | Stations in Canadian provinces are out of scope, because the assignment limits routes to the USA. They are loaded but get no coordinates. | 112 stations (620 rows) in AB, BC, MB, NB, NS, ON, QC, SK, YT. |

## 2. Station locations

The file has no coordinates. Its `Address` column is a highway direction
("I-44, EXIT 283 & US-69"), not a street address, and map geocoders could not
resolve it: of six real addresses tried, five returned nothing and one
returned a road. So:

| # | Assumption | Numbers |
|---|---|---|
| 2.1 | A station is placed at the centre of its city, taken from the Census places file. It is not placed at its exit. | 6,213 stations located. |
| 2.2 | All stations in the same city share one point. | The 6,213 stations sit on 3,534 distinct points. |
| 2.3 | City names are compared by letters and digits only, inside the station's own state. "Mc Calla" equals "McCalla"; "Oneill" equals "O'Neill". | |
| 2.4 | A city missing from the Census file gets no coordinates. No other source and no online service is used. | 413 US stations in 275 cities. See below. |
| 2.5 | When a municipality and a Census statistical area in one state share a name, the station is in the municipality. | Decides 26 stations. |
| 2.6 | When two municipalities in one state share a name, the station is in the one nearest the other stations with the same `Rack ID`. | Decides 12 stations. |
| 2.7 | The `City` and `State` columns are correct. Errors in the file are not corrected. | Known examples below. |

Stations and user input settle a shared name differently, on purpose. A
station has a Rack ID, which is evidence of where it is (2.6). A start or
finish typed by a user has no such evidence, so the larger place is used (3.9).

**Coverage:** 6,213 of 6,626 US stations have coordinates (93.8%).

**Who the 413 missing stations are**

- Cities the Census lists under a longer official name: Pecos TX (9),
  Augusta GA (8), Macon GA (6), Nashville TN (5), Boise ID (5), Lexington KY (4).
- Cities written "Saint ..." in the fuel file and "St. ..." in the Census
  file: Saint Cloud MN (7), Saint Joseph MO (5), Saint Louis MO (4) and others.
- Townships, New England towns and unincorporated places, which the places
  file does not contain: Mahwah NJ (4), Ruther Glen VA (4), Hope Hull AL (4)
  and others. Coverage is lowest in MA, ME, NH, CT and RI.

**Known wrong or doubtful rows**

- Pleasant Hill, NC (I-95 exit 180) and Ashland, PA (US-22) are probably
  matched to a different place of the same name, roughly 185 and 90 miles off.
- Some rows contradict themselves and are used as written: Natchez, MS is
  listed on I-55, which does not pass through Natchez; Ennis, TX is listed on
  "US-45, EXIT 249", which is I-45.
- A station far from its city's centre is placed far from where it really
  is: Miccosukee Service Plaza is listed under Fort Lauderdale, FL and is
  about 48 miles west of the city's point.

## 3. Route endpoint

Given by the assignment, so not assumptions: range 500 miles, 10 miles per
gallon, start and finish inside the USA.

| # | Assumption | Where it is set, or numbers |
|---|---|---|
| 3.1 | The vehicle starts with a full tank, so the first 500 miles need no purchase. A trip of 500 miles or less shows no stops and a cost of $0. | `START_FUEL_FRACTION = 1.0` |
| 3.2 | The tank holds 50 gallons (500 miles ÷ 10 mpg), and fuel use is 10 mpg throughout. | `VEHICLE_RANGE_MILES`, `VEHICLE_MPG` |
| 3.3 | A station counts as "on the route" if it is within 10 miles of the route line, measured in a straight line to the nearest route point. Route points are compared at about one-mile spacing, so a station's distance from the route and its position along it are accurate to about half a mile. | `STATION_MAX_DETOUR_MILES = 10`, `routing/stations_on_route.py` |
| 3.4 | Only stations with coordinates are considered. The 413 unlocated US stations and the 112 Canadian ones are ignored. Stations are read into memory once per server process; the server must be restarted after the setup commands are re-run. | `load_stations` |
| 3.5 | The drive from the route to a station and back adds no miles and no fuel. A stop also costs no time, so the cheapest plan may include very small purchases. | `routing/fuel_plan.py` |
| 3.6 | Total cost is the fuel bought along the way. The fuel in the tank at the start is not charged, and the truck arrives with an empty tank: fuel left at the finish would be money spent for nothing. | `routing/fuel_plan.py` |
| 3.7 | One call to the routing service (OSRM public server) per request, asking for the full route line. The driving distance OSRM reports is used as the trip length. | `routing/osrm.py`, `OSRM_URL` |
| 3.8 | Start and finish are given as "City, ST" or "lat,lon". A city is looked up in the Census places saved at setup, so no geocoding service is called and a request makes one external call. | `routing/locations.py` |
| 3.9 | When several places in a state share the name the user typed, an incorporated town is preferred to a Census statistical area, and then the place with the largest land area is used. The larger place is assumed to be the one the user means; the smaller one cannot be reached by name. | 22 names are shared by two or more towns (e.g. Liberty PA, Wilmington IL, Franklin PA); 80 more are shared only by statistical areas. |
| 3.10 | The response names the place that was matched ("Liberty borough, PA") with its coordinates, so a wrong choice is visible to the user. | |
| 3.11 | Names are compared by letters and digits only, so two towns spelled "Lake View" and "Lakeview" in one state count as the same name, and 3.9 picks between them. | 10 such pairs. |
| 3.12 | A city missing from the Census places file, or written "Saint" where the Census writes "St.", is not found and the request is refused with a message. | Nashville TN, Boise ID, Augusta GA, "Saint Louis, MO". Same cause as 2.4. |
| 3.13 | Coordinates given by the user are accepted if they are a valid latitude and longitude. They are not checked to be inside the USA. | |
| 3.14 | Each stop's cost is rounded to the cent, and the total is the sum of those rounded costs. | |
| 3.15 | If a stretch of the route with no station is longer than the truck can drive, the request is refused with a message instead of returning an impossible plan. | `FuelPlanError` |
| 3.16 | A finished plan is reused for 24 hours for the same start and finish. Roads and the price file are assumed not to change in that time. Plans are held in the server's memory, so they are lost on restart and not shared between server processes. Failed requests are not kept. | `CACHE_SECONDS` in `routing/planner.py` |
| 3.17 | The route line in the response has about one point per mile, which is enough to draw the trip. The full line is still used to find the stations. | `ROUTE_LINE_SPACING_MILES`; Dallas to Chicago: 962 of 9,470 points, 21 KB |
| 3.18 | The map page needs internet access in the viewer's browser, which loads Leaflet and the OpenStreetMap tiles. The API itself does not call them. | `routing/templates/routing/map.html` |
| 3.19 | A fuel stop is drawn at its city's centre (2.1), not at its exit, so a pin can sit a few miles from the road. | `miles_off_route` in the response |