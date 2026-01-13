import requests
import folium
import pandas as pd
from datetime import datetime, timedelta, timezone
import pytz
import os
from dotenv import load_dotenv

load_dotenv()

# === CONFIG ===
API_KEY = os.getenv("TOMTOM_API_KEY")
if not API_KEY:
    raise ValueError("TOMTOM_API_KEY not found in environment variables. Please check your .env file.")
HISTORICAL_FILE = "historical_traffic.csv"
IST = pytz.timezone("Asia/Kolkata")  # Indian Standard Time

# === Geocoding ===
def geocode_location(location):
    url = f"https://api.tomtom.com/search/2/geocode/{location}.json"
    params = {"key": API_KEY}
    r = requests.get(url, params=params).json()
    if r.get("results"):
        pos = r["results"][0]["position"]
        return pos["lat"], pos["lon"]
    return None

# === Routes API ===
def get_routes(start_coords, end_coords, mode, depart_at=None):
    url = f"https://api.tomtom.com/routing/1/calculateRoute/{start_coords[0]},{start_coords[1]}:{end_coords[0]},{end_coords[1]}/json"
    params = {
        "key": API_KEY,
        "traffic": "true",
        "routeType": "fastest",
        "travelMode": mode,
        "maxAlternatives": 4  # fetch up to 4 routes
    }
    if depart_at:
        params["departAt"] = depart_at.isoformat()

    r = requests.get(url, params=params).json()
    if "routes" not in r:
        return None
    return r["routes"]

# === Best Departure Time ===
def find_best_departure(start_coords, end_coords, mode, window_minutes=60, interval_minutes=10):
    now = datetime.now(timezone.utc)
    best_time, best_duration = None, float("inf")

    for mins in range(0, window_minutes + 1, interval_minutes):
        depart_at = now + timedelta(minutes=mins)
        routes = get_routes(start_coords, end_coords, mode, depart_at)
        if routes:
            for route in routes:
                duration = route["summary"]["travelTimeInSeconds"]
                if duration < best_duration:
                    best_duration = duration
                    best_time = depart_at

    return best_time, best_duration

# === Map Drawing ===
def draw_routes_on_map(start_coords, end_coords, routes, original_mode, used_mode, departure_time=None, selected_route=None):
    m = folium.Map(location=start_coords, zoom_start=14)

    # Markers
    folium.Marker(start_coords, tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(end_coords, tooltip="End", icon=folium.Icon(color="red")).add_to(m)

    for i, route in enumerate(routes):
        if selected_route is not None and i != selected_route:
            continue  # skip other routes

        points = [(p["latitude"], p["longitude"]) for leg in route["legs"] for p in leg["points"]]
        summary = route.get("summary", {})
        traffic_delay = summary.get("trafficDelayInSeconds", 0)
        travel_time = summary.get("travelTimeInSeconds", 0)
        distance = summary.get("lengthInMeters", 0) / 1000  # km

        # Color logic
        if selected_route is not None:  
            color, weight = "red", 8  # Highlight selected route
        else:
            if traffic_delay < 300:
                color = "blue"
            elif traffic_delay < 900:
                color = "orange"
            else:
                color = "darkred"
            weight = 6

        # Mode info
        mode_info = used_mode.capitalize()
        if original_mode == "bike" and used_mode == "car":
            mode_info = "Bike (fallback → Car)"

        # Arrival time in IST
        if departure_time:
            arrival_time = departure_time + timedelta(seconds=travel_time)
        else:
            arrival_time = datetime.now(timezone.utc) + timedelta(seconds=travel_time)
        arrival_ist = arrival_time.astimezone(IST).strftime("%H:%M")

        # Popup
        popup_text = (
            f"<b>Route {i+1}</b><br>"
            f"Mode: {mode_info}<br>"
            f"Distance: {distance:.2f} km<br>"
            f"Duration: {travel_time//60} mins<br>"
            f"Traffic Delay: {traffic_delay//60} mins<br>"
            f"Arrival Time: {arrival_ist} (IST)"
        )

        folium.PolyLine(
            points, color=color, weight=weight, opacity=0.8,
            popup=folium.Popup(popup_text, max_width=300)
        ).add_to(m)

    # Fallback note
    if original_mode == "bike" and used_mode == "car":
        folium.map.Marker(
            start_coords,
            icon=folium.DivIcon(
                html="<div style='font-size:12px; color:red;'>⚠️ Bike not available – showing Car routes</div>"
            )
        ).add_to(m)

    # Legend
    legend_html = """
    <div style="
        position: fixed; 
        bottom: 30px; left: 30px; width: 180px; height: 120px; 
        border:2px solid grey; z-index:9999; font-size:14px;
        background-color:white; padding: 10px;">
        <b>Traffic Legend</b><br>
        <i style="color:blue;">■■■</i> Smooth<br>
        <i style="color:orange;">■■■</i> Moderate<br>
        <i style="color:darkred;">■■■</i> Heavy
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    m.save("routes_map.html")
    print("🗺️ Map saved as routes_map.html – open it in your browser.")

# === Main ===
def main():
    start = input("Enter starting location: ")
    end = input("Enter destination: ")
    mode = input("Select mode (car/bike): ").strip().lower()

    start_coords = geocode_location(start)
    end_coords = geocode_location(end)

    if not start_coords or not end_coords:
        print(f"Could not geocode one of the locations: {start} or {end}")
        return

    print(f"Start coords: {start_coords} End coords: {end_coords}")
    print(f"\n⏰ Current IST Time: {datetime.now(IST).strftime('%H:%M')}")

    use_best = input("Do you want to find the best departure time? (yes/no): ").strip().lower() == "yes"

    # Historical data optional
    try:
        historical_df = pd.read_csv(HISTORICAL_FILE)
        print("📂 Historical data loaded.")
    except FileNotFoundError:
        print("⚠️ No historical data file found. Skipping historical traffic...")

    routes, used_mode, departure_time = None, mode, None

    if use_best:
        window = int(input("Enter time window in minutes (default 60): ") or "60")
        interval = int(input("Enter check interval in minutes (default 10): ") or "10")

        best_time, best_duration = find_best_departure(start_coords, end_coords, mode, window, interval)
        if best_time:
            best_ist = best_time.astimezone(IST).strftime("%H:%M")
            arrival_time = best_time + timedelta(seconds=best_duration)
            arrival_ist = arrival_time.astimezone(IST).strftime("%H:%M")

            print(f"✅ Best departure: {best_ist} (IST) → {best_duration//60} mins")
            print(f"   Expected arrival: {arrival_ist} (IST)")

            departure_time = best_time
            routes = get_routes(start_coords, end_coords, mode, best_time)
        else:
            print("⚠️ No route found for this time window.")
            return
    else:
        departure_time = datetime.now(timezone.utc)
        routes = get_routes(start_coords, end_coords, mode)

    # Bike fallback
    if not routes and mode == "bike":
        print("⚠️ No bike route found. Trying car instead...")
        routes = get_routes(start_coords, end_coords, "car")
        used_mode = "car"

    if not routes:
        print("⚠️ No routes found.")
        return

    # Show all routes first
    draw_routes_on_map(start_coords, end_coords, routes, mode, used_mode, departure_time)

    # Ask user if they want only one route
    choice = input("Do you want to view only one route? (yes/no): ").strip().lower()
    if choice == "yes":
        try:
            route_num = int(input(f"Enter route number (1-{len(routes)}): ")) - 1
            if 0 <= route_num < len(routes):
                draw_routes_on_map(start_coords, end_coords, routes, mode, used_mode, departure_time, selected_route=route_num)
                print(f"✅ Showing only Route {route_num+1}")
            else:
                print("⚠️ Invalid route number. Showing all routes instead.")
        except ValueError:
            print("⚠️ Invalid input. Showing all routes instead.")

if __name__ == "__main__":
    main()
