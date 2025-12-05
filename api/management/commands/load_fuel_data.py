import csv
from django.core.management.base import BaseCommand
from api.models import FuelStation
import os
import geonamescache

class Command(BaseCommand):
    help = 'Load fuel prices from CSV'

    def handle(self, *args, **kwargs):
        file_path = 'fuel-prices-for-be-assessment.csv'
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'File {file_path} not found.'))
            return

        # Build City Lookup
        gc = geonamescache.GeonamesCache()
        cities = gc.get_cities()
        city_lookup = {}
        for cid, data in cities.items():
            if data['countrycode'] == 'US':
                key = (data['name'].lower(), data['admin1code'])
                city_lookup[key] = (data['latitude'], data['longitude'])
        
        self.stdout.write(f"Loaded {len(city_lookup)} US cities for lookup.")

        with open(file_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            stations = []
            seen_ids = set()
            missing_geo = 0
            for row in reader:
                try:
                    opis_id = int(row['OPIS Truckstop ID'])
                    if opis_id in seen_ids:
                        continue
                    seen_ids.add(opis_id)

                    city = row['City'].strip()
                    state = row['State'].strip()
                    key = (city.lower(), state)
                    
                    lat, lng = None, None
                    if key in city_lookup:
                        lat, lng = city_lookup[key]
                    else:
                        # Try simple variations?
                        pass
                    
                    if lat is None:
                        missing_geo += 1
                        # self.stdout.write(f"Missing geo for {city}, {state}")
                        continue # Skip if no location? Or save without? 
                        # If I save without, I can't use it for routing.
                        # Better to skip for this assignment than have broken data.

                    station = FuelStation(
                        opis_id=int(row['OPIS Truckstop ID']),
                        name=row['Truckstop Name'],
                        address=row['Address'],
                        city=city,
                        state=state,
                        # zip_code=row['Zip'], # Not in CSV
                        latitude=lat,
                        longitude=lng,
                        retail_price=float(row['Retail Price'])
                    )
                    stations.append(station)
                except (ValueError, KeyError) as e:
                    self.stdout.write(self.style.WARNING(f"Skipping row due to error: {e}"))

            FuelStation.objects.all().delete()
            FuelStation.objects.bulk_create(stations)
            self.stdout.write(self.style.SUCCESS(f'Successfully loaded {len(stations)} stations. Skipped {missing_geo} due to missing location.'))
