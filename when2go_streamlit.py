import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
import pandas as pd
from datetime import datetime, timedelta, timezone
import pytz
import plotly.express as px
import os
from dotenv import load_dotenv

load_dotenv()

# CONFIG & UTILS 
API_KEY = os.getenv("TOMTOM_API_KEY")
if not API_KEY:
    raise ValueError("TOMTOM_API_KEY not found in environment variables. Please check your .env file.")
IST = pytz.timezone("Asia/Kolkata")
HISTORY_FILE = "historical_journeys.csv"

st.set_page_config(
    page_title="WHEN_TO_GO",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #ddd; }
    .header-style { color: #ff69b4; font-size: 36px; font-weight: 700; text-align: left; padding-bottom: 10px; border-bottom: 2px solid #262730; margin-bottom: 20px; }
    .route-card { background-color: #1e2026; padding: 15px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 4px 8px 0 rgba(0, 0, 0, 0.2); }
    .card-title { color: #6a0dad; font-size: 20px; font-weight: 600; margin-top: 0; margin-bottom: 5px; }
    .st-dg, .stTextInput>div>div>input, .stSelectbox>div>div>select { background-color: #262730; color: #ddd; }
    .stButton>button { background-color: #6a0dad; color: white; border-radius: 5px; border: none; padding: 10px 20px; font-weight: bold; }
    .stButton>button:hover { background-color: #7b2edc; }
    .alternative-card { background-color: #262a33; padding: 10px; border-radius: 5px; margin-top: 10px; border: 1px solid #3d414d; }
    .alternative-card-selected { background-color: #3f1f5f; padding: 10px; border-radius: 5px; margin-top: 10px; border: 2px solid #ff69b4; box-shadow: 0 0 10px rgba(255, 105, 180, 0.5); }
</style>
""", unsafe_allow_html=True)

# API FUNCTIONS 
@st.cache_data(ttl=3600)
def geocode_location(location):
    url = f"https://api.tomtom.com/search/2/geocode/{location}.json"
    params = {"key": API_KEY}
    r = requests.get(url, params=params).json()
    if r.get("results"):
        pos = r["results"][0]["position"]
        return pos["lat"], pos["lon"]
    return None

@st.cache_data(ttl=60)
def get_routes(start_coords, end_coords, mode, depart_at=None, route_type="fastest"):
    url = f"https://api.tomtom.com/routing/1/calculateRoute/{start_coords[0]},{start_coords[1]}:{end_coords[0]},{end_coords[1]}/json"
    
    # Map Streamlit's route_type to TomTom API's routeType
    tomtom_route_type = "fastest" # Default
    if route_type == "shortest":
        tomtom_route_type = "shortest"
    elif route_type == "eco-friendly":
        tomtom_route_type = "eco" # TomTom API uses "eco" for eco-friendly

    params = {
        "key": API_KEY,
        "traffic": "true",
        "routeType": tomtom_route_type, 
        "travelMode": mode,
        "maxAlternatives": 3 
    }
    if depart_at:
        params["departAt"] = depart_at.isoformat(timespec='seconds')
    r = requests.get(url, params=params).json()
    return r.get("routes", None)

def extract_route_points(route):
    points = []
    for leg in route.get("legs", []):
        for p in leg.get("points", []):
            points.append((p["latitude"], p["longitude"]))
    return points

# Modified to return a list of dictionaries for each alternative route
def find_best_departure_with_alternatives(start_coords, end_coords, mode, window_minutes=60, interval_minutes=10, route_type="fastest"):
    now_utc = datetime.now(timezone.utc)
    start_time_utc = now_utc + timedelta(minutes=1) 
    
    all_departure_options = []

    for mins in range(0, window_minutes + 1, interval_minutes):
        depart_at_utc = start_time_utc + timedelta(minutes=mins)
        routes_response = get_routes(start_coords, end_coords, mode, depart_at_utc, route_type) 
        
        if routes_response:
            # Stores all alternatives for this departure time
            alternative_routes_for_this_departure = []
            for i, route in enumerate(routes_response):
                duration = route["summary"]["travelTimeInSeconds"]
                traffic_delay = route["summary"].get("trafficDelayInSeconds", 0)
                distance = route["summary"].get("lengthInMeters", 0)/1000
                
                alternative_routes_for_this_departure.append({
                    "alt_idx": i,
                    "travel_time_min": duration // 60,
                    "traffic_delay_min": traffic_delay // 60,
                    "distance_km": distance,
                    "route_points": extract_route_points(route)
                })
            
            # Find the best alternative for this specific departure time (usually the first one, but confirm)
            # Or, we can just take the primary route as the 'main' for the card
            primary_route_summary = alternative_routes_for_this_departure[0] if alternative_routes_for_this_departure else {}
            
            all_departure_options.append({
                "depart_at_utc": depart_at_utc,
                "depart_at_ist": depart_at_utc.astimezone(IST).strftime("%I:%M %p"),
                "primary_travel_time_min": primary_route_summary.get("travel_time_min", 0),
                "primary_traffic_delay_min": primary_route_summary.get("traffic_delay_min", 0),
                "primary_arrival_ist": (depart_at_utc + timedelta(seconds=primary_route_summary.get("travel_time_min",0)*60)).astimezone(IST).strftime("%I:%M %p"),
                "alternatives": alternative_routes_for_this_departure
            })
    
    df_all_options = pd.DataFrame(all_departure_options)
    
    # Identify the overall best departure time based on the primary route's travel time
    if not df_all_options.empty:
        overall_best_idx = df_all_options['primary_travel_time_min'].idxmin()
        overall_best_depart_at_utc = df_all_options.loc[overall_best_idx, 'depart_at_utc']
    else:
        overall_best_idx = None
        overall_best_depart_at_utc = None

    return overall_best_depart_at_utc, df_all_options

def draw_map(start_coords, end_coords, route_points, alternative_points=None):
    # Changed to OpenStreetMap tiles and a more regional zoom level
    m = folium.Map(location=start_coords, zoom_start=10, tiles='OpenStreetMap') 
    folium.Marker(start_coords, tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(end_coords, tooltip="End", icon=folium.Icon(color="red")).add_to(m)

    if route_points:
        folium.PolyLine(route_points, color="#ff69b4", weight=8, opacity=0.8,
                         tooltip="Selected Optimal Route").add_to(m)
    
    if alternative_points:
        for i, alt_route_points in enumerate(alternative_points):
            if alt_route_points != route_points: # Don't draw the selected one again
                folium.PolyLine(alt_route_points, color="#800080", weight=5, opacity=0.5, dash_array="5, 5",
                                 tooltip=f"Alternative Route {i+1}").add_to(m)
    
    return m

# HISTORICAL DATA FUNCTIONS
def initialize_history_file():
    if not os.path.exists(HISTORY_FILE):
        df = pd.DataFrame(columns=[
            "start_location", "end_location", "departure_time_ist", 
            "travel_time_min", "traffic_delay_min", "route_type", "mode", "timestamp", "alternative_selected"
        ])
        df.to_csv(HISTORY_FILE, index=False)

def save_journey_to_history(start_loc, end_loc, departure_time_ist, travel_time_min, traffic_delay_min, route_type, mode, alternative_selected=0):
    initialize_history_file()
    current_time_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    
    new_record = pd.DataFrame([{
        "start_location": start_loc,
        "end_location": end_loc,
        "departure_time_ist": departure_time_ist,
        "travel_time_min": travel_time_min,
        "traffic_delay_min": traffic_delay_min,
        "route_type": route_type,
        "mode": mode,
        "timestamp": current_time_str,
        "alternative_selected": alternative_selected # Store which alternative was chosen
    }])
    new_record.to_csv(HISTORY_FILE, mode='a', header=False, index=False)
    st.session_state['historical_data_needs_reload'] = True

@st.cache_data(ttl=600)
def load_history_for_route(start_loc, end_loc):
    initialize_history_file()
    try:
        df_history = pd.read_csv(HISTORY_FILE)
        df_filtered = df_history[
            (df_history['start_location'].str.lower() == start_loc.lower()) &
            (df_history['end_location'].str.lower() == end_loc.lower())
        ].copy()
        
        df_filtered['departure_time_dt'] = pd.to_datetime(df_filtered['departure_time_ist'], format="%I:%M %p").dt.time
        df_filtered['timestamp_dt'] = pd.to_datetime(df_filtered['timestamp'])
        return df_filtered
    except Exception as e:
        return pd.DataFrame()

# STREAMLIT APP LAYOUT 
st.markdown("<h1 class='header-style'>WHEN_TO_GO</h1>", unsafe_allow_html=True)
st.markdown("<h3><small>Best Departure Time</small></h3>", unsafe_allow_html=True)

col_inputs, col_map_results = st.columns([1, 3])

with col_inputs:
    st.subheader("Journey Details 🗺️")
    start = st.text_input("Enter starting location", "", key="start_loc_input") 
    end = st.text_input("Enter destination", "", key="end_loc_input")
    st.markdown("Mode of transpotation is car.")
    mode="car"
    
    st.markdown("---")
    st.subheader("Optimization Preferences ⏰")
    best_departure = st.checkbox("Find Best Departure Time?", value=True, key="best_dep_checkbox")
    
    # UPDATED: Added "Eco-Friendly" to radio options
    route_type = st.radio("Route Priority", ["Fastest", "Shortest", "Eco-Friendly"], index=0, key="route_priority_radio")

    window, interval = 60, 10
    if best_departure:
        st.markdown("<p style='font-size:14px;'>Search Window (from now):</p>", unsafe_allow_html=True)
        col_win, col_int = st.columns(2)
        with col_win:
            window = st.number_input("Window (mins)", 10, 120, 60, key="window_input")
        with col_int:
            interval = st.number_input("Interval (mins)", 5, 30, 10, key="interval_input")

    st.markdown("---")
    if st.button("🚀 Find Optimal Departure", type="primary", key="find_routes_button"):
        if start and end:
            st.session_state['run_optimization'] = True
            st.session_state['selected_departure_card_idx'] = 0 # Default to first departure option
            st.session_state['selected_alternative_idx'] = 0   # Default to first alternative
        else:
            st.error("Please enter both start and destination locations.")
    elif 'run_optimization' not in st.session_state:
        st.session_state['run_optimization'] = False


with col_map_results:
    st.subheader("🗺️ Route Map")
    
    if not st.session_state.get('run_optimization', False) and 'all_departure_options_df' not in st.session_state:
        st.info("Enter journey details on the left and click 'Find Optimal Departure' to see the map and recommendations.")
        # Initial map with OpenStreetMap tiles
        default_map = folium.Map(location=[17.3850, 78.4867], zoom_start=11, tiles='OpenStreetMap') 
        st_folium(default_map, width="100%", height=400)

    if st.session_state.get('run_optimization'):
        start_coords = geocode_location(start)
        end_coords = geocode_location(end)
        
        if not start_coords or not end_coords:
            st.error("❌ Could not geocode locations. Please ensure the locations are correct and your API key is valid.")
            st.session_state['run_optimization'] = False
        else:
            st.session_state.start_coords = start_coords
            st.session_state.end_coords = end_coords
            # UPDATED: Storing the route_type as lowercased string (e.g., "fastest", "shortest", "eco-friendly")
            st.session_state.route_type = route_type.lower() 
            st.session_state.mode = mode
            st.session_state.best_departure_enabled = best_departure 
            
            if best_departure:
                with st.spinner(f"Analyzing {window} mins of traffic data..."):
                    overall_best_depart_at_utc, all_departure_options_df = find_best_departure_with_alternatives(
                        start_coords, end_coords, mode, window, interval, st.session_state.route_type
                    )
                    
                if all_departure_options_df.empty:
                    st.error("❌ No routes found for the given time window. Try adjusting the time window or locations.")
                    st.session_state['run_optimization'] = False
                else:
                    st.session_state.all_departure_options_df = all_departure_options_df
                    # Set the initial selected departure card to the best one
                    st.session_state.selected_departure_card_idx = all_departure_options_df['primary_travel_time_min'].idxmin()

            else: # If not finding best departure (single route for "now")
                routes_response = get_routes(start_coords, end_coords, mode, depart_at=datetime.now(timezone.utc), route_type=st.session_state.route_type)
                if not routes_response:
                    st.error("❌ No routes found.")
                else:
                    alternatives_for_now = []
                    for i, route in enumerate(routes_response):
                        duration = route["summary"]["travelTimeInSeconds"]
                        traffic_delay = route["summary"].get("trafficDelayInSeconds", 0)
                        distance = route["summary"].get("lengthInMeters", 0)/1000
                        alternatives_for_now.append({
                            "alt_idx": i,
                            "travel_time_min": duration // 60,
                            "traffic_delay_min": traffic_delay // 60,
                            "distance_km": distance,
                            "route_points": extract_route_points(route)
                        })
                    
                    all_departure_options_df = pd.DataFrame([{
                        "depart_at_utc": datetime.now(timezone.utc),
                        "depart_at_ist": datetime.now(IST).strftime("%I:%M %p"),
                        "primary_travel_time_min": alternatives_for_now[0].get("travel_time_min",0),
                        "primary_traffic_delay_min": alternatives_for_now[0].get("traffic_delay_min",0),
                        "primary_arrival_ist": (datetime.now(timezone.utc) + timedelta(seconds=alternatives_for_now[0].get("travel_time_min",0)*60)).astimezone(IST).strftime("%I:%M %p"),
                        "alternatives": alternatives_for_now
                    }])
                    st.session_state.all_departure_options_df = all_departure_options_df
                    st.session_state.selected_departure_card_idx = 0
                    st.session_state.selected_alternative_idx = 0 # Default to first alternative
            
            st.session_state['run_optimization'] = False # Reset flag

    # Display Logic (Map and Results)
    if 'all_departure_options_df' in st.session_state and not st.session_state.all_departure_options_df.empty:
        df_options = st.session_state.all_departure_options_df
        selected_departure_option_idx = st.session_state.get('selected_departure_card_idx', 0)
        selected_departure_row = df_options.loc[selected_departure_option_idx]
        
        # Get the selected alternative route for display
        selected_alternative_idx = st.session_state.get('selected_alternative_idx', 0)
        
        # Ensure selected_alternative_idx is valid for the current departure row
        num_alternatives = len(selected_departure_row['alternatives'])
        if selected_alternative_idx >= num_alternatives:
            selected_alternative_idx = 0 # Default to the first if the previous selection is out of bounds
            st.session_state['selected_alternative_idx'] = 0
            
        selected_alt_route_data = selected_departure_row['alternatives'][selected_alternative_idx]
        
        current_route_points = selected_alt_route_data['route_points']
        all_alt_route_points = [alt['route_points'] for alt in selected_departure_row['alternatives']]

        st.markdown(f"""
        <div style='background-color: #1e2026; padding: 10px; border-radius: 5px; margin-bottom: 10px;'>
            <p style='color: #ddd; margin: 0;'>
                <strong>Departure:</strong> {selected_departure_row['depart_at_ist']} | 
                <strong>Duration:</strong> {selected_alt_route_data['travel_time_min']} mins | 
                <strong>Arrival (approx):</strong> { (selected_departure_row['depart_at_utc'] + timedelta(minutes=selected_alt_route_data['travel_time_min'])).astimezone(IST).strftime("%I:%M %p") } | 
                <strong>Traffic Delay:</strong> {selected_alt_route_data['traffic_delay_min']} mins |
                <strong>Selected Alternative:</strong> {selected_alternative_idx + 1}
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # Pass all alternative points to draw_map
        folium_map = draw_map(
            st.session_state.start_coords, 
            st.session_state.end_coords, 
            current_route_points,
            alternative_points=all_alt_route_points
        )
        st_folium(folium_map, width="100%", height=400)

        st.markdown("---")

        #   Departure Time Card
        st.subheader("⏰ Optimal Departure Times")
        
        if st.session_state.best_departure_enabled: 
            df_sorted_by_departure_time = df_options.sort_values(by='primary_travel_time_min', ascending=True).reset_index(drop=True)
            st.write(f"Showing **{len(df_sorted_by_departure_time)}** departure options based on '{st.session_state.route_type}' priority.")

            card_cols_departure = st.columns(min(len(df_sorted_by_departure_time), 3)) 

            for i, row in df_sorted_by_departure_time.iterrows():
                # Original index (from df_options) to reference `selected_departure_card_idx`
                original_idx = df_options[df_options['depart_at_utc'] == row['depart_at_utc']].index[0]
                is_selected_departure = (original_idx == selected_departure_option_idx)
                is_best_overall = (df_options['primary_travel_time_min'].idxmin() == original_idx)
                
                color = "#ff69b4" if is_best_overall else "#6a0dad"
                card_style = f"border-left: 5px solid {color};"
                
                # Traffic Icon/Color for the primary route of this departure time
                if row['primary_traffic_delay_min'] > 10:
                    traffic_indicator = "🔴 Heavy Traffic"
                elif row['primary_traffic_delay_min'] > 3:
                    traffic_indicator = "🟠 Moderate Traffic"
                else:
                    traffic_indicator = "🟢 Smooth Traffic"
                                        
                with card_cols_departure[i % len(card_cols_departure)]: 
                    st.markdown(f"""
                    <div class='route-card' style='{card_style}'>
                        <p class='card-title' style='color:{color}; margin-bottom: 5px;'>{"⭐ BEST OVERALL!" if is_best_overall else f"Option {i+1}"}</p>
                        <p style='color: #ddd; margin: 0;'>🚀 Depart At: {row['depart_at_ist']}</p>
                        <p style='color: #ddd; margin: 0;'>⏱️ Total Duration: {row['primary_travel_time_min']} mins</p>
                        <p style='color: #ddd; margin: 0;'>🚦 Traffic Level: {traffic_indicator}</p>
                        <p style='color: #ddd; margin: 0;'>➡️ Arrival Time: {row['primary_arrival_ist']}</p>
                        <button id='btn_dep_{original_idx}' style='
                            background-color: {color}; color: white; border: none; padding: 5px 10px; border-radius: 5px; cursor: pointer; margin-top: 10px; font-size: 12px;'
                            onclick="document.getElementById('stButton_select_departure_{original_idx}').click();">
                            {"Selected" if is_selected_departure else "Select Departure"}
                        </button>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button(f"Select Departure {row['depart_at_ist']}", key=f"stButton_select_departure_{original_idx}", help="Hidden button for custom HTML"):
                        st.session_state.selected_departure_card_idx = original_idx
                        st.session_state.selected_alternative_idx = 0 # Reset alternative selection when departure time changes
                        st.rerun() # Use st.rerun()

            st.markdown("---")
            # Alternative Routes for the Currently Selected Departure
            st.subheader(f"🔄 Alternative Paths for Departure at {selected_departure_row['depart_at_ist']}")
            
            alternatives_for_selected_departure = selected_departure_row['alternatives']
            
            if alternatives_for_selected_departure:
                card_cols_alternatives = st.columns(len(alternatives_for_selected_departure))
                for i, alt_data in enumerate(alternatives_for_selected_departure):
                    is_selected_alt = (i == selected_alternative_idx)
                    card_class = "alternative-card-selected" if is_selected_alt else "alternative-card"
                    alt_color = "#ff69b4" if is_selected_alt else "#6a0dad"
                    
                    with card_cols_alternatives[i]:
                        st.markdown(f"""
                        <div class='{card_class}'>
                            <p style='color: {alt_color}; font-weight: bold; margin-bottom: 5px;'>{"Selected Alternative" if is_selected_alt else f"Alternative {i+1}"}</p>
                            <p style='color: #ddd; margin: 0;'>⏱️ Duration: {alt_data['travel_time_min']} mins</p>
                            <p style='color: #ddd; margin: 0;'>🚦 Traffic Delay: {alt_data['traffic_delay_min']} mins</p>
                            <p style='color: #ddd; margin: 0;'>📏 Distance: {alt_data['distance_km']:.1f} km</p>
                            <button id='btn_alt_{i}' style='
                                background-color: {alt_color}; color: white; border: none; padding: 5px 10px; border-radius: 5px; cursor: pointer; margin-top: 10px; font-size: 12px;'
                                onclick="document.getElementById('stButton_select_alternative_{i}').click();">
                                {"Showing on Map" if is_selected_alt else "View on Map"}
                            </button>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        if st.button(f"Select Alternative {i+1}", key=f"stButton_select_alternative_{i}", help="Hidden button for custom HTML"):
                            st.session_state.selected_alternative_idx = i
                            st.rerun()
            else:
                st.info("No alternative paths found for this departure time.")

        else: # Single route for "now"
            row = df_options.iloc[0]
            # UPDATED: Changed display text for route priority
            st.info(f"Showing {st.session_state.route_type.replace('-', ' ').title()} route departing NOW ({row['depart_at_ist']}).") 
            
            # Display primary route card for 'now'
            st.markdown(f"""
            <div class='route-card' style='border-left: 5px solid #ff69b4;'>
                <p class='card-title' style='color:#ff69b4; margin-bottom: 5px;'>Current {st.session_state.route_type.replace('-', ' ').title()} Route</p>
                <p style='color: #ddd; margin: 0;'>🚀 **Depart At:** {row['depart_at_ist']}</p>
                <p style='color: #ddd; margin: 0;'>⏱️ **Total Duration:** {row['primary_travel_time_min']} mins</p>
                <p style='color: #ddd; margin: 0;'>🚦 **Traffic Delay:** {row['primary_traffic_delay_min']} mins</p>
                <p style='color: #ddd; margin: 0;'>➡️ **Arrival Time:** {row['primary_arrival_ist']}</p>
            </div>
            """, unsafe_allow_html=True)
            
            # Still show alternatives for the "now" departure
            alternatives_for_selected_departure = row['alternatives']
            if alternatives_for_selected_departure:
                st.markdown("---")
                st.subheader(f"🔄 Alternative Paths for Departure at {row['depart_at_ist']}")
                card_cols_alternatives = st.columns(len(alternatives_for_selected_departure))
                for i, alt_data in enumerate(alternatives_for_selected_departure):
                    is_selected_alt = (i == selected_alternative_idx)
                    card_class = "alternative-card-selected" if is_selected_alt else "alternative-card"
                    alt_color = "#ff69b4" if is_selected_alt else "#6a0dad"
                    
                    with card_cols_alternatives[i]:
                        st.markdown(f"""
                        <div class='{card_class}'>
                            <p style='color: {alt_color}; font-weight: bold; margin-bottom: 5px;'>{"Selected Alternative" if is_selected_alt else f"Alternative {i+1}"}</p>
                            <p style='color: #ddd; margin: 0;'>⏱️ **Duration:** {alt_data['travel_time_min']} mins</p>
                            <p style='color: #ddd; margin: 0;'>🚦 **Traffic Delay:** {alt_data['traffic_delay_min']} mins</p>
                            <p style='color: #ddd; margin: 0;'>📏 **Distance:** {alt_data['distance_km']:.1f} km</p>
                            <button id='btn_alt_single_{i}' style='
                                background-color: {alt_color}; color: white; border: none; padding: 5px 10px; border-radius: 5px; cursor: pointer; margin-top: 10px; font-size: 12px;'
                                onclick="document.getElementById('stButton_select_alternative_single_{i}').click();">
                                {"Showing on Map" if is_selected_alt else "View on Map"}
                            </button>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        if st.button(f"Select Alternative {i+1} (Single)", key=f"stButton_select_alternative_single_{i}", help="Hidden button for custom HTML"):
                            st.session_state.selected_alternative_idx = i
                            st.rerun()

        # Save the calculated route to history
        # The best primary route of the selected departure (and its chosen alternative) is saved
        best_route_to_save_for_history = selected_alt_route_data
        save_journey_to_history(
            start_loc=start, 
            end_loc=end, 
            departure_time_ist=selected_departure_row['depart_at_ist'], 
            travel_time_min=best_route_to_save_for_history['travel_time_min'], 
            traffic_delay_min=best_route_to_save_for_history['traffic_delay_min'],
            route_type=st.session_state.route_type, # This will now save "fastest", "shortest", or "eco-friendly"
            mode=mode,
            alternative_selected=selected_alternative_idx + 1 # Save the 1-based index of the alternative
        )

        # Bottom Graph (Current Traffic Impact Trend)
        if st.session_state.best_departure_enabled and not df_options.empty:
            st.markdown("---") 
            st.subheader("📊 Current Traffic Impact Trend (Primary Route)")
            fig = px.line(df_options, 
                          x="depart_at_ist", 
                          y="primary_travel_time_min",
                          labels={"depart_at_ist":"Departure Time (IST)", "primary_travel_time_min":"Travel Time (min)"},
                          title="Primary Route Travel Time vs Departure Time",
                          template="plotly_dark")
            
            overall_best_time_str = df_options.loc[df_options['primary_travel_time_min'].idxmin(), 'depart_at_ist']
            overall_best_time_idx = df_options["depart_at_ist"].tolist().index(overall_best_time_str)
            fig.add_vline(x=overall_best_time_idx, line_width=2, line_dash="dash", line_color="#ff69b4", 
                          annotation_text="Overall Best Departure", annotation_position="top left")
                            
            st.plotly_chart(fig, width='stretch')

    # Historical Data Visualization Section
    if start and end: 
        if st.session_state.get('historical_data_needs_reload', False):
            load_history_for_route.clear() 
            st.session_state['historical_data_needs_reload'] = False

        df_history_filtered = load_history_for_route(start, end)
        
        if not df_history_filtered.empty:
            st.markdown("---")
            st.subheader("📈 Historical Travel Trends for this Route")
            
            st.write("#### Average Travel Time by Time of Day")
            
            df_history_filtered['hour_of_day'] = df_history_filtered['departure_time_dt'].apply(lambda x: x.hour)
            df_hourly = df_history_filtered.groupby('hour_of_day')['travel_time_min'].mean().reset_index()
            
            fig_hourly = px.bar(df_hourly, 
                                 x="hour_of_day", 
                                 y="travel_time_min",
                                 labels={"hour_of_day":"Hour of Day (24h)", "travel_time_min":"Average Travel Time (min)"},
                                 title="Average Travel Time by Hour for this Route",
                                 template="plotly_dark",
                                 color_discrete_sequence=px.colors.sequential.Plasma) 
            fig_hourly.update_layout(xaxis = dict(tickmode = 'linear', tick0 = 0, dtick = 1)) 
            st.plotly_chart(fig_hourly, width='stretch')

            st.write("#### Traffic Delay Trends Over Time")
            fig_delay = px.line(df_history_filtered.sort_values(by='timestamp_dt'),
                                 x='timestamp_dt',
                                 y='traffic_delay_min',
                                 title='Historical Traffic Delay (mins) for this Route',
                                 labels={"timestamp_dt": "Date & Time", "traffic_delay_min": "Traffic Delay (min)"},
                                 template="plotly_dark",
                                 line_shape="spline",
                                 color_discrete_sequence=["#ff69b4"])
            st.plotly_chart(fig_delay, width='stretch')
            
        else:
            st.markdown("---")
            st.info("No historical data available yet for this route. Run a few optimizations to build up the history!")