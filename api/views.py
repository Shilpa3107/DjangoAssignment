from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import requests
from .models import FuelStation
from geopy.distance import geodesic
import polyline

class RouteView(APIView):
    def get(self, request):
        start = request.query_params.get('start')
        finish = request.query_params.get('finish')
        
        if not start or not finish:
            return Response({"error": "Start and finish locations are required."}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Geocode start and finish
        def geocode(query):
            url = "https://nominatim.openstreetmap.org/search"
            params = {'q': query, 'format': 'json', 'limit': 1}
            headers = {'User-Agent': 'FuelRouteApp/1.0'}
            try:
                resp = requests.get(url, params=params, headers=headers)
                if resp.status_code == 200 and resp.json():
                    return float(resp.json()[0]['lat']), float(resp.json()[0]['lon'])
            except Exception as e:
                print(f"Geocoding error: {e}")
            return None, None

        start_lat, start_lon = geocode(start)
        finish_lat, finish_lon = geocode(finish)
        
        if start_lat is None or finish_lat is None:
             return Response({"error": "Could not geocode locations."}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Get Route from OSRM
        osrm_url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{finish_lon},{finish_lat}?overview=full&geometries=geojson"
        try:
            route_resp = requests.get(osrm_url)
            if route_resp.status_code != 200:
                 return Response({"error": "Could not fetch route from OSRM."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            route_data = route_resp.json()
            if route_data['code'] != 'Ok':
                return Response({"error": "No route found."}, status=status.HTTP_400_BAD_REQUEST)

            route = route_data['routes'][0]
            distance_meters = route['distance']
            distance_miles = distance_meters * 0.000621371
            geometry = route['geometry'] # GeoJSON
            
            # Decode polyline if needed, but we requested geojson
            # coordinates are [lon, lat]
            coords = geometry['coordinates']
            path_points = [(p[1], p[0]) for p in coords] # lat, lon

        except Exception as e:
            return Response({"error": f"Routing error: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 3. Fuel Stop Logic
        
        # Constants
        MAX_RANGE_MILES = 500
        MPG = 10
        TANK_CAPACITY = MAX_RANGE_MILES / MPG # 50 gallons
        
        # We assume starting with full tank? 
        # "The vehicle can travel a maximum of 500 miles on a full tank"
        # "Total fuel cost for the trip"
        # Let's assume we start full.
        
        stops = []
        total_fuel_cost = 0.0
        
        # Get all stations with valid coordinates
        all_stations = list(FuelStation.objects.filter(latitude__isnull=False, longitude__isnull=False).values('id', 'name', 'city', 'state', 'retail_price', 'latitude', 'longitude'))
        
        # Optimization: Filter by bounding box
        lats = [p[0] for p in path_points]
        lons = [p[1] for p in path_points]
        min_lat, max_lat = min(lats) - 0.5, max(lats) + 0.5
        min_lon, max_lon = min(lons) - 0.5, max(lons) + 0.5
        
        candidate_stations = [
            s for s in all_stations 
            if min_lat <= s['latitude'] <= max_lat and min_lon <= s['longitude'] <= max_lon
        ]
        
        # Map stations to route distance?
        # This is the hard part. We need to know "how far along the route" each station is.
        # Simple approach:
        # Calculate cumulative distance for each point in path.
        # For each candidate station, find the closest point in path.
        # Assign station distance = path_point_distance.
        
        # Sample path points to reduce computation
        # Target around 1000 points max
        step = max(1, len(path_points) // 1000)
        sampled_points = path_points[::step]
        
        # Calculate cumulative distances for sampled points
        cum_dist = [0.0]
        for i in range(1, len(sampled_points)):
            d = geodesic(sampled_points[i-1], sampled_points[i]).miles
            cum_dist.append(cum_dist[-1] + d)
            
        total_route_dist = cum_dist[-1]
        
        station_on_route = []
        for s in candidate_stations:
            s_loc = (s['latitude'], s['longitude'])
            
            # Quick filter using simple Euclidean on lat/lon (approx)
            # 1 degree ~ 69 miles. 10 miles ~ 0.15 degrees.
            # If station is > 0.2 degrees from ANY point, skip?
            # That's still O(S*P).
            
            # Find closest point in sampled_points
            min_d = float('inf')
            closest_idx = -1
            
            for i, p in enumerate(sampled_points):
                # Simple check first
                if abs(p[0] - s_loc[0]) > 0.2 or abs(p[1] - s_loc[1]) > 0.2:
                    continue
                
                d = geodesic(s_loc, p).miles
                if d < min_d:
                    min_d = d
                    closest_idx = i
            
            if min_d <= 10 and closest_idx != -1: # 10 miles buffer
                station_on_route.append({
                    'station': s,
                    'dist_from_start': cum_dist[closest_idx],
                    'dist_from_route': min_d
                })
        
        # Sort stations by distance from start
        station_on_route.sort(key=lambda x: x['dist_from_start'])
        
        # Greedy Strategy
        current_pos = 0.0 # miles from start
        current_fuel = MAX_RANGE_MILES # miles
        
        # We need to reach total_route_dist
        
        while current_pos + current_fuel < total_route_dist:
            # We can't make it to the end. We must refuel.
            # Look for reachable stations:
            # Station dist must be > current_pos (we don't go back)
            # Station dist must be <= current_pos + current_fuel
            
            reachable = [
                s for s in station_on_route 
                if current_pos < s['dist_from_start'] <= current_pos + current_fuel
            ]
            
            if not reachable:
                return Response({
                    "error": "Ran out of fuel! No stations in range.",
                    "route_geometry": geometry,
                    "partial_stops": stops
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Pick the cheapest one
            best_stop = min(reachable, key=lambda x: x['station']['retail_price'])
            
            # Drive to best_stop
            dist_traveled = best_stop['dist_from_start'] - current_pos
            current_fuel -= dist_traveled
            current_pos = best_stop['dist_from_start']
            
            # Refill
            # How much? To full?
            # Cost = gallons * price
            gallons_needed = (MAX_RANGE_MILES - current_fuel) / MPG
            cost = gallons_needed * best_stop['station']['retail_price']
            
            stops.append({
                "station": best_stop['station']['name'],
                "city": best_stop['station']['city'],
                "state": best_stop['station']['state'],
                "price_per_gallon": best_stop['station']['retail_price'],
                "gallons": round(gallons_needed, 2),
                "cost": round(cost, 2),
                "location": {"lat": best_stop['station']['latitude'], "lon": best_stop['station']['longitude']}
            })
            
            total_fuel_cost += cost
            current_fuel = MAX_RANGE_MILES # Full tank
            
        # If we can reach the end, we are done.
        
        return Response({
            "route_geometry": geometry,
            "total_distance_miles": round(distance_miles, 2),
            "fuel_stops": stops,
            "total_fuel_cost": round(total_fuel_cost, 2)
        })
