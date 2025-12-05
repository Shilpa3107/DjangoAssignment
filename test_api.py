import requests
import time

def test_route():
    # Wait for server to start
    time.sleep(5)
    
    url = "http://127.0.0.1:8000/api/route"
    params = {
        "start": "New York, NY",
        "finish": "Chicago, IL"
    }
    
    try:
        print(f"Testing {url} with params {params}")
        resp = requests.get(url, params=params)
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print("Response keys:", data.keys())
            print("Total Distance:", data.get('total_distance_miles'))
            print("Fuel Cost:", data.get('total_fuel_cost'))
            print("Stops:", len(data.get('fuel_stops', [])))
            for stop in data.get('fuel_stops', []):
                print(stop)
        else:
            print("Error:", resp.text)
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_route()
