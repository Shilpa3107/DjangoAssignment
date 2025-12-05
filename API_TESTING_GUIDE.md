# API Testing Guide & Backend Overview

This guide provides step-by-step instructions on how to test the Fuel Route API using Postman and includes a high-level overview of the backend logic for your demo.

---

## Part 1: Testing with Postman

### Prerequisites
1.  **Ensure your server is running.**
    *   Open your terminal/command prompt.
    *   Navigate to your project folder.
    *   Run: `python manage.py runserver`
    *   You should see a message saying the server is running at `http://127.0.0.1:8000/`.

2.  **Download & Install Postman** (if you haven't already) from [postman.com](https://www.postman.com/downloads/).

### Step 1: Create a New Request
1.  Open Postman.
2.  Click the **+** button or **"New"** > **"HTTP Request"** to open a new tab.
3.  In the dropdown menu next to the URL bar (which usually says "GET"), ensure **GET** is selected.
4.  In the URL bar, enter your API endpoint:
    ```
    http://127.0.0.1:8000/api/route
    ```

### Step 2: Set Parameters
Since this is a GET request, we pass data using **Query Parameters**.

1.  Click on the **"Params"** tab (below the URL bar).
2.  Add the following Key-Value pairs:
    *   **Key**: `start` | **Value**: `New York, NY`
    *   **Key**: `finish` | **Value**: `Austin, TX`
3.  You will see the URL automatically update to:
    `http://127.0.0.1:8000/api/route?start=New York, NY&finish=Austin, TX`

### Step 3: Send the Request
1.  Click the blue **"Send"** button.
2.  Look at the bottom pane for the **Response**.
3.  Ensure the format is set to **JSON** (it usually auto-detects).

### Step 4: Analyze the Response
**Successful Response (200 OK):**
You should see a JSON object containing:
*   `route_geometry`: A large object containing coordinates (used for mapping).
*   `total_distance_miles`: The total trip distance.
*   `total_fuel_cost`: The estimated cost.
*   `fuel_stops`: A list of recommended stops.

**Example Output:**
```json
{
    "route_geometry": { "type": "LineString", "coordinates": [...] },
    "total_distance_miles": 1742.5,
    "fuel_stops": [
        {
            "station": "Station A",
            "city": "Some City",
            "state": "PA",
            "price_per_gallon": 3.20,
            "gallons": 15.5,
            "cost": 49.60,
            ...
        }
    ],
    "total_fuel_cost": 210.45
}
```

### Step 5: Test Failure Cases
To demonstrate robust error handling, try these scenarios:

**Case A: Missing Parameters**
1.  Uncheck the checkboxes next to `start` and `finish` in the Params tab.
2.  Click **Send**.
3.  **Result**: `400 Bad Request`
    ```json
    { "error": "Start and finish locations are required." }
    ```

**Case B: Invalid Location**
1.  Set `start` to `New York, NY`.
2.  Set `finish` to `AtlantisUnderTheSea`.
3.  Click **Send**.
4.  **Result**: `400 Bad Request`
    ```json
    { "error": "Could not geocode locations." }
    ```

**Case C: No Route Found (e.g., across ocean)**
1.  Set `start` to `New York, NY`.
2.  Set `finish` to `London, UK`.
3.  Click **Send**.
4.  **Result**: `400 Bad Request` or `500 Internal Server Error` (depending on OSRM response).
    ```json
    { "error": "No route found." }
    ```

---

## Part 2: Backend Overview (For Your Demo)

Use this summary to explain how your code works during your presentation.

### 1. The Tech Stack
*   **Framework**: Django & Django REST Framework (Python).
*   **Database**: SQLite (stores fuel station data).
*   **External APIs**:
    *   **Nominatim (OpenStreetMap)**: For converting city names (e.g., "NYC") into coordinates (Lat/Lon).
    *   **OSRM (Open Source Routing Machine)**: For calculating the driving path and distance between points.

### 2. The Logic Flow (How it processes a request)
When a user asks for a route:

1.  **Geocoding**: The API first takes the "Start" and "Finish" text inputs and converts them to latitude/longitude coordinates.
2.  **Route Calculation**: It sends these coordinates to the OSRM routing engine to get the full driving path (a series of thousands of GPS points) and the total distance.
3.  **Fuel Station Search**:
    *   The system looks at the route and filters the database for fuel stations that are within a **10-mile buffer** of the driving path.
    *   It uses a **spatial search** (checking distance from route points) to find valid candidates.
4.  **Optimization Algorithm (The "Brain")**:
    *   The vehicle has a **500-mile range**.
    *   The algorithm simulates driving along the route.
    *   When the fuel gets low (or to ensure we reach the end), it looks ahead at reachable stations.
    *   It picks the **cheapest** station within range to refuel.
    *   This repeats until the destination is reached.
5.  **Response**: Finally, it packages the route shape (GeoJSON), the list of stops, and the total cost into a clean JSON response.

### 3. Key Features
*   **Cost Efficiency**: Always prioritizes cheaper fuel prices.
*   **Range Anxiety**: Ensures stops are planned so the vehicle never runs out of gas (max 500 miles).
*   **Performance**: Uses optimized sampling to process long routes (like NY to CA) quickly.
