**When2Go – Smart Departure Time Finder**
When2Go is a Streamlit web app that helps you decide when to leave, not just which route to take. It analyzes near‑future traffic conditions and recommends the optimal departure time to avoid congestion and reduce travel time.

Primary test location: Hyderabad, India 🇮🇳
Easily extendable to other cities supported by TomTom
**Why When2Go?
Most navigation apps only show traffic right now. When2Go predicts traffic in the near future, helping you choose the best time to start your journey — saving time, fuel, and stress.

**Features**
Intelligent departure time analysis: Scans up to 60 minutes ahead and recommends the best time to leave.
Interactive maps: Folium visualization with traffic severity color‑coding.
Alternative routes: Up to 3 route options per departure time.
Traffic visualization: Plotly charts of travel‑time trends across the selected window.
Historical tracking: Journeys stored in CSV with hourly trend analysis.
Multiple route types: Fastest, Shortest, and Eco‑optimized (fuel‑efficient where supported).
Mode support: Optimized for car; bike gracefully falls back to car due to API limits.
Timezone‑aware: All times shown in IST (Indian Standard Time).

**Tech Stack**
| Component | Technology |
|---------|-----------|
| Backend | Python 3.8+ |
| Web Framework | Streamlit |
| Maps & Visualization | Folium, Plotly, Streamlit-Folium |
| APIs | TomTom Routing & Geocoding APIs |
| Data Handling | Pandas, CSV |
| HTTP Client | Requests |
| Timezone Management | Pytz |
| Configuration | Python-dotenv |

**Project Structure**
when-2-go/
├── when2go_streamlit.py      # Main Streamlit app
├── tomtom_optimizer.py       # Core routing & optimization logic
├── historical_journeys.csv   # Stored journey history
├── routes_map.html           # Exported interactive map
├── .env                      # Environment variables (gitignored)
├── .gitignore
└── README.md

**Getting Started**
**Prerequisites
Python 3.8+
TomTom API key (free tier available)
pip
Installation (Windows PowerShell)
# Clone
git clone https://github.com/Gagan-2005/when-2-go.git
cd when-2-go

# Create and activate venv
python -m venv venv
venv\Scripts\Activate.ps1

# Install dependencies
pip install streamlit requests folium streamlit-folium pandas plotly pytz python-dotenv

# Create .env with your API key
New-Item -Path . -Name ".env" -ItemType "file" -Force | Out-Null
Add-Content .env "TOMTOM_API_KEY=your_api_key_here"

# Run the app
streamlit run when2go_streamlit.py
# Local URL: http://localhost:8501

**How to Use**
Enter journey details:
Start (e.g., “Irrum Manzil, Hyderabad”)
Destination (e.g., “Punjagutta, Hyderabad”)
Mode: Car (bike falls back to car)
**Set optimization preferences:**
Enable “Best Departure Time”
Time window (default: 60 min) and interval (default: 10 min)
Route priority: Fastest / Shortest / Eco‑optimized
**View results:**
Interactive map with selected route and alternatives
Departure‑time cards: duration, traffic level (Smooth / Moderate / Heavy), estimated arrival, ⭐ best option
Traffic trend charts
**Decide & go:**
Select a departure time and alternative route
Map updates live
Journey saved automatically
Core Algorithm (BDT)
Start at current time + 1 minute
For each interval in the window:
Fetch routes with predicted traffic
Extract travel duration and delays
Track the minimum duration
Select the departure time with minimum duration
Time complexity: O(n × m), where n = number of intervals, m = number of alternatives.

**Data Model (CSV)**
historical_journeys.csv columns:

start_location, end_location, departure_time_ist, travel_time_min,
traffic_delay_min, route_type, mode, timestamp, alternative_selected
API Integration
**Geocoding:
GET https://api.tomtom.com/search/2/geocode/{location}.json
**Routing:
GET https://api.tomtom.com/routing/1/calculateRoute/{lat1},{lon1}:{lat2},{lon2}/json
Supports real‑time traffic, future departure prediction, and multiple alternatives.
**Limitations**
Primarily tested for Hyderabad (extendable to other cities)
TomTom API rate limits (free tier ~2,500/day)
Bike routing not officially supported
Requires internet
Historical data reflects your usage
Traffic predictions depend on TomTom availability and peak‑hour dynamics
**Future Enhancements**
Multi‑mode routing (bike, transit, walking)
ML‑based traffic prediction from history
Accounts & cloud sync
Mobile app (React Native)
Calendar integration & reminders
Multi‑city support
Weather‑aware routing
**Security Notes**
API key stored in .env (do not commit)
No cloud storage — local CSV only
All API calls over HTTPS
