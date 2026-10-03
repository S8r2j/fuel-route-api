"""
Two web addresses of route API: JSON plan and map page
"""
from urllib.parse import urlencode

from django.shortcuts import render
from django.urls import reverse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from routing.fuel_plan import FuelPlanError
from routing.locations import LocationError
from routing.osrm import RoutingError
from routing.planner import plan_trip

MISSING_PLACES = (
    "Give both 'start' and 'finish', written as 'City, ST' or 'lat,lon'"
)

ERROR_STATUS = {
    LocationError : 400,
    FuelPlanError : 422,
    RoutingError : 502,
}

def get_plan(request):
    """
    Read 'start' and 'finish' from the request and return (plan, error, status).
    """
    start = request.GET.get("start", "").strip()
    finish = request.GET.get("finish", "").strip()
    if not start or not finish:
        return None, MISSING_PLACES, 400
    
    try:
        return plan_trip(start,finish), None, 200
    except tuple(ERROR_STATUS) as error:
        return None, str(error), ERROR_STATUS[type(error)]
    
@api_view(["GET"])
def route_plan(request):
    """
    Return the route, the fuel stops and the total fuel cost as JSON.
    """
    plan, error, status = get_plan(request)
    if error:
        return Response({"error": error}, status=status)
 
    places = urlencode({
        "start": request.GET["start"],
        "finish": request.GET["finish"],
    })
    map_url = request.build_absolute_uri(f"{reverse('route-map')}?{places}")
 
    # The long route line goes last so the summary is at the top.
    route = plan["route"]
    summary = {key: value for key, value in plan.items() if key != "route"}
    return Response({**summary, "map_url": map_url, "route": route})
 
 
def route_map(request):
    """
    Show the route and its fuel stops on a map.
 
    The plan comes from the same cache as the JSON view, so opening the map
    after calling the API makes no second call to OSRM.
    """
    plan, error, status = get_plan(request)
    return render(
        request, "routing/map.html", {"plan": plan, "error": error},
        status=status,
    )