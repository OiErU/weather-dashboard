#!/usr/bin/env python3
"""
Surf EPG Generator (Open-Meteo + Gemini Flash)
Generates XMLTV EPG with surf conditions for Portuguese surf spots.

Changes from Stormglass version:
- Uses Open-Meteo Marine API (unlimited free requests, no API key needed)
- Separate swell vs wind wave data for better accuracy
- Peak period instead of mean period (matches Surfline better)
- Improved wind direction labels for each spot's facing direction
- Better rideability logic in AI prompts
"""

import os
import sys
import requests
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# --- CONFIGURATION ---
BASE_URL = "https://raw.githubusercontent.com/OiErU/weather-dashboard/main"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- AI CLIENT SETUP ---
HAS_AI = False
client = None
try:
    from google import genai
    if GEMINI_API_KEY:
        client = genai.Client(api_key=GEMINI_API_KEY)
        HAS_AI = True
        print("✅ AI Client connected.")
    else:
        print("⚠️ No GEMINI_API_KEY set - using fallback descriptions.")
except ImportError:
    print("⚠️ google-genai library not found. Install with: pip install google-genai")
except Exception as e:
    print(f"⚠️ AI Client failed: {e}")

# --- SPOTS CONFIGURATION ---
# facing = direction the beach faces (where waves come FROM for ideal conditions)
# offshore_wind = wind directions that are offshore for this spot
# NOTE: Coordinates pushed slightly offshore to ensure they hit Open-Meteo sea grid cells
SPOTS_CONFIG = {
    # ERICEIRA
    "ribeira": {
        "lat": 38.988, 
        "lon": -9.419, 
        "name": "Ribeira d'Ilhas", 
        "facing": 290,
        "offshore_wind": (45, 135),  # NE to SE winds are offshore
        "description": "World-class right point break"
    },
    
    # PENICHE - SOUTH SIDE
    "supertubos": {
        "lat": 39.345, 
        "lon": -9.363, 
        "name": "Supertubos", 
        "facing": 240,
        "offshore_wind": (0, 90),  # N to E winds are offshore
        "description": "Heavy beach break, the Portuguese Pipeline"
    },
    "molheleste": {
        "lat": 39.349, 
        "lon": -9.370, 
        "name": "Molhe Leste", 
        "facing": 270,
        "offshore_wind": (45, 135),  # NE to SE winds are offshore
        "description": "Sheltered jetty spot, works on big swells"
    },
    "meio_baia": {
        "lat": 39.358, 
        "lon": -9.351, 
        "name": "Meio da Baia", 
        "facing": 300,
        "offshore_wind": (90, 180),  # E to S winds are offshore
        "description": "Middle of the bay, mellower waves"
    },
    "cantinho": {
        "lat": 39.368, 
        "lon": -9.355,  # FIXED: pushed west to hit sea grid cell
        "name": "Cantinho da Baia", 
        "facing": 320,
        "offshore_wind": (100, 200),  # E to S winds are offshore
        "description": "Protected corner, good for smaller days"
    },
    
    # PENICHE - NORTH SIDE (Baleal)
    "baleal_n": {
        "lat": 39.385, 
        "lon": -9.345,  # FIXED: pushed north/west to hit sea grid cell
        "name": "Baleal Norte", 
        "facing": 10,
        "offshore_wind": (135, 225),  # SE to SW winds are offshore
        "description": "North-facing, works when south side is maxed"
    },
    "lagide": {
        "lat": 39.390, 
        "lon": -9.350,  # FIXED: pushed north/west to hit sea grid cell
        "name": "Lagide", 
        "facing": 350,
        "offshore_wind": (135, 225),  # SE to SW winds are offshore
        "description": "Powerful reef break, needs solid swell"
    },
}

# --- CHANNELS MAP ---
CHANNELS = [
    {"id": "ericeira-surfline", "spot": "ribeira", "name": "Surfline Ericeira", "logo": "ericeira.png?v=2", "poster": "ericeira_poster.jpg"},
    {"id": "ericeira-meo", "spot": "ribeira", "name": "MEO Ericeira", "logo": "ericeira.png?v=2", "poster": "ericeira_poster.jpg"},
    {"id": "supertubos-surfline", "spot": "supertubos", "name": "Surfline Supertubos", "logo": "supertubos.png?v=2", "poster": "supertubos_poster.jpg"},
    {"id": "supertubos-meo", "spot": "supertubos", "name": "MEO Supertubos", "logo": "supertubos.png?v=2", "poster": "supertubos_poster.jpg"},
    {"id": "molheleste-surfline", "spot": "molheleste", "name": "Surfline Molhe Leste", "logo": "molheleste.png?v=2", "poster": "molheleste_poster.jpg"},
    {"id": "molheleste-meo", "spot": "molheleste", "name": "MEO Molhe Leste", "logo": "molheleste.png?v=2", "poster": "molheleste_poster.jpg"},
    {"id": "baia-meo", "spot": "meio_baia", "name": "MEO Baia", "logo": "baleal.png?v=2", "poster": "baleal_poster.jpg"},
    {"id": "cantinho-surfline", "spot": "cantinho", "name": "Surfline Cantinho", "logo": "cantinho.png?v=2", "poster": "cantinho_poster.jpg"},
    {"id": "cantinho-meo", "spot": "cantinho", "name": "MEO Cantinho", "logo": "cantinho.png?v=2", "poster": "cantinho_poster.jpg"},
    {"id": "baleal-surfline", "spot": "baleal_n", "name": "Surfline Baleal", "logo": "baleal.png?v=2", "poster": "baleal_poster.jpg"},
    {"id": "lagide-surfline", "spot": "lagide", "name": "Surfline Lagide", "logo": "lagide.png?v=2", "poster": "lagide_poster.jpg"},
    {"id": "lagide-meo", "spot": "lagide", "name": "MEO Lagide", "logo": "lagide.png?v=2", "poster": "lagide_poster.jpg"},
]


def get_openmeteo_marine_data(lat: float, lon: float, forecast_days: int = 3) -> dict | None:
    """Fetch marine data from Open-Meteo API."""
    url = "https://marine-api.open-meteo.com/v1/marine"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": [
            "wave_height",
            "wave_period",
            "wave_direction",
            "swell_wave_height",
            "swell_wave_period",
            "swell_wave_peak_period",
            "swell_wave_direction",
            "wind_wave_height",
        ],
        "forecast_days": forecast_days,
        "timezone": "Europe/Lisbon",
    }
    
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️ Marine API Error for {lat},{lon}: {e}")
        return None


def get_openmeteo_weather_data(lat: float, lon: float, forecast_days: int = 3) -> dict | None:
    """Fetch wind data from Open-Meteo Weather API."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": [
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
        ],
        "forecast_days": forecast_days,
        "timezone": "Europe/Lisbon",
    }
    
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️ Weather API Error for {lat},{lon}: {e}")
        return None


def get_wind_label(wind_deg: float, spot_config: dict) -> str:
    """
    Determine if wind is offshore, onshore, or cross-shore for a specific spot.
    Uses the spot's offshore_wind range for accurate assessment.
    """
    if wind_deg is None:
        return "UNKNOWN"
    
    offshore_range = spot_config.get("offshore_wind", (0, 90))
    start, end = offshore_range
    
    # Handle ranges that cross 0 degrees (e.g., 315 to 45)
    if start > end:
        is_offshore = wind_deg >= start or wind_deg <= end
    else:
        is_offshore = start <= wind_deg <= end
    
    if is_offshore:
        return "OFFSHORE"
    
    # Check if it's directly onshore (opposite of offshore)
    onshore_start = (start + 180) % 360
    onshore_end = (end + 180) % 360
    
    if onshore_start > onshore_end:
        is_onshore = wind_deg >= onshore_start or wind_deg <= onshore_end
    else:
        is_onshore = onshore_start <= wind_deg <= onshore_end
    
    if is_onshore:
        return "ONSHORE"
    
    return "CROSS"


def get_wind_compass(degrees: float) -> str:
    """Convert wind degrees to compass direction."""
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = round(degrees / 22.5) % 16
    return directions[idx]


def assess_conditions(swell_height: float, swell_period: float, wind_speed: float, 
                      wind_label: str, wind_wave_height: float) -> dict:
    """
    Assess surf conditions and return a rating and notes.
    """
    rating = "🌊"  # Default: surfable
    notes = []
    is_rideable = True
    
    # Too big?
    if swell_height > 4.0:
        rating = "⚠️"
        notes.append("Very large swell - experienced surfers only")
        if swell_height > 6.0:
            notes.append("Potentially dangerous - consider watching from shore")
            is_rideable = False
    
    # Wind check
    if wind_label == "ONSHORE" and wind_speed > 20:
        rating = "💨"
        notes.append("Onshore wind making it messy")
        if wind_speed > 35:
            is_rideable = False
    elif wind_label == "OFFSHORE" and swell_height >= 1.0:
        rating = "⭐⭐"
        notes.append("Clean conditions with offshore wind")
    
    # Period check
    if swell_period < 8:
        notes.append("Short period - weaker waves")
    elif swell_period > 14:
        notes.append("Long period - powerful waves")
    
    # Wind waves adding chop
    if wind_wave_height > 1.0 and wind_label != "OFFSHORE":
        notes.append("Significant wind chop")
    
    # Flat?
    if swell_height < 0.5:
        rating = "😴"
        notes.append("Essentially flat")
        is_rideable = False
    
    return {
        "rating": rating,
        "notes": notes,
        "is_rideable": is_rideable
    }


def get_ai_commentary(spot_name: str, swell_height: float, swell_period: float, 
                      wind_speed: float, wind_label: str, assessment: dict) -> str:
    """Generate AI commentary for surf conditions."""
    if not HAS_AI or not client:
        # Fallback description
        if not assessment["is_rideable"]:
            return f"{swell_height}m - not ideal for surfing right now."
        return f"{swell_height}m @ {swell_period}s with {wind_label.lower()} winds."

    prompt = (
        f"You're an experienced local bodyboarder at {spot_name}, Portugal. "
        f"Current conditions: {swell_height}m swell @ {swell_period}s period, "
        f"{wind_speed}km/h {wind_label.lower()} wind.\n\n"
        
        "RIDEABILITY ASSESSMENT (apply first):\n"
        "- Onshore wind over 25km/h with swell over 2m = messy, probably not worth it\n"
        "- Swell over 5m at a beachbreak = dangerous closeouts, watching only\n"
        "- Short periods (<8s) = weak, crumbly waves\n"
        "- Offshore/light wind + 1-3m + 10s+ period = ideal\n"
        "- Under 0.5m = flat, go get coffee\n\n"
        
        "TASK: Write ONE sentence (max 20 words) describing today's session prospects.\n\n"
        
        "TONE: Dry wit, understated. Like a local who's seen it all. "
        "No forced slang, no 'brah', no exclamation marks. "
        "If it's dangerous or blown out, say so plainly with a bit of dark humor. "
        "If it's good, quiet confidence - you don't need to oversell it.\n\n"
        
        "Include the wave height naturally in your sentence."
    )

    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        if response.text:
            return response.text.strip().replace('"', '').replace('\n', ' ')
        return f"{swell_height}m swell (AI silent)"
    except Exception as e:
        print(f"⚠️ AI Error: {e}")
        return f"{swell_height}m swell (AI error)"


def fetch_all_spot_data(forecast_days: int = 3) -> dict:
    """
    Fetch marine and weather data for all unique coordinates.
    Returns a dict keyed by "lat,lon" with combined data.
    """
    data_cache = {}
    
    # Get unique coordinates
    unique_coords = {}
    for spot_id, spot in SPOTS_CONFIG.items():
        coord_key = f"{spot['lat']},{spot['lon']}"
        if coord_key not in unique_coords:
            unique_coords[coord_key] = (spot['lat'], spot['lon'], spot['name'])
    
    print(f"🌊 Fetching data for {len(unique_coords)} unique locations...")
    
    for coord_key, (lat, lon, name) in unique_coords.items():
        print(f"   📍 Fetching {name} ({coord_key})...")
        
        marine_data = get_openmeteo_marine_data(lat, lon, forecast_days)
        weather_data = get_openmeteo_weather_data(lat, lon, forecast_days)
        
        if marine_data and weather_data:
            # Combine hourly data
            hours = []
            marine_hourly = marine_data.get("hourly", {})
            weather_hourly = weather_data.get("hourly", {})
            
            times = marine_hourly.get("time", [])
            for i, t in enumerate(times):
                hours.append({
                    "time": t,
                    "wave_height": marine_hourly.get("wave_height", [None])[i] if i < len(marine_hourly.get("wave_height", [])) else None,
                    "wave_period": marine_hourly.get("wave_period", [None])[i] if i < len(marine_hourly.get("wave_period", [])) else None,
                    "wave_direction": marine_hourly.get("wave_direction", [None])[i] if i < len(marine_hourly.get("wave_direction", [])) else None,
                    "swell_height": marine_hourly.get("swell_wave_height", [None])[i] if i < len(marine_hourly.get("swell_wave_height", [])) else None,
                    "swell_period": marine_hourly.get("swell_wave_period", [None])[i] if i < len(marine_hourly.get("swell_wave_period", [])) else None,
                    "swell_peak_period": marine_hourly.get("swell_wave_peak_period", [None])[i] if i < len(marine_hourly.get("swell_wave_peak_period", [])) else None,
                    "swell_direction": marine_hourly.get("swell_wave_direction", [None])[i] if i < len(marine_hourly.get("swell_wave_direction", [])) else None,
                    "wind_wave_height": marine_hourly.get("wind_wave_height", [None])[i] if i < len(marine_hourly.get("wind_wave_height", [])) else None,
                    "wind_speed": weather_hourly.get("wind_speed_10m", [None])[i] if i < len(weather_hourly.get("wind_speed_10m", [])) else None,
                    "wind_direction": weather_hourly.get("wind_direction_10m", [None])[i] if i < len(weather_hourly.get("wind_direction_10m", [])) else None,
                    "wind_gusts": weather_hourly.get("wind_gusts_10m", [None])[i] if i < len(weather_hourly.get("wind_gusts_10m", [])) else None,
                })
            
            data_cache[coord_key] = {"hours": hours}
            print(f"   ✅ Got {len(hours)} hours of data")
        else:
            print(f"   ❌ Failed to fetch data for {name}")
        
        time.sleep(0.5)  # Be polite to the API
    
    return data_cache


def generate_xml(days: int = 1, output_file: str = "surf_epg.xml"):
    """Generate XMLTV EPG file."""
    root = ET.Element("tv")
    root.set("generator-info-name", "Surf EPG (Open-Meteo)")
    root.set("generator-info-url", BASE_URL)
    
    # Fetch all data
    weather_cache = fetch_all_spot_data(forecast_days=days + 1)
    
    if not weather_cache:
        print("❌ No data fetched. Exiting.")
        return
    
    # Add channel headers
    for ch in CHANNELS:
        channel = ET.SubElement(root, "channel", id=ch["id"])
        ET.SubElement(channel, "display-name").text = ch["name"]
        ET.SubElement(channel, "icon", src=f"{BASE_URL}/logos/{ch['logo']}")

    # Build programs
    now = datetime.now()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ai_cache = {}  # Cache AI responses to avoid duplicate calls

    print(f"\n📺 Generating {days} day(s) of EPG data...")
    
    for day in range(days):
        for block in range(4):  # 4 x 6-hour blocks per day
            block_hour = block * 6
            program_start = start_of_today + timedelta(days=day, hours=block_hour)
            program_stop = program_start + timedelta(hours=6)
            
            # Calculate which hour index to use in the data
            hours_from_start = (day * 24) + block_hour
            
            for ch in CHANNELS:
                spot_id = ch['spot']
                spot_config = SPOTS_CONFIG[spot_id]
                coord_key = f"{spot_config['lat']},{spot_config['lon']}"
                spot_data = weather_cache.get(coord_key)
                
                title = ch['name']
                desc = "No data available"
                icon_src = f"{BASE_URL}/posters/{ch['poster']}"

                if spot_data and 'hours' in spot_data:
                    hours_list = spot_data['hours']
                    
                    # Get the hour data, clamping to available range
                    hour_idx = min(hours_from_start, len(hours_list) - 1)
                    h = hours_list[hour_idx]
                    
                    try:
                        # Extract values with fallbacks
                        swell_height = h.get('swell_height') or h.get('wave_height') or 0
                        swell_period = h.get('swell_peak_period') or h.get('swell_period') or 0
                        wind_wave_height = h.get('wind_wave_height') or 0
                        wind_speed = h.get('wind_speed') or 0
                        wind_direction = h.get('wind_direction') or 0
                        wind_gusts = h.get('wind_gusts') or 0
                        
                        # Round values
                        swell_height = round(float(swell_height), 1)
                        swell_period = round(float(swell_period), 0)
                        wind_wave_height = round(float(wind_wave_height), 1)
                        wind_speed = round(float(wind_speed), 0)
                        wind_gusts = round(float(wind_gusts), 0)
                        
                        # Get wind label
                        wind_label = get_wind_label(wind_direction, spot_config)
                        wind_compass = get_wind_compass(wind_direction)
                        
                        # Assess conditions
                        assessment = assess_conditions(
                            swell_height, swell_period, wind_speed, 
                            wind_label, wind_wave_height
                        )
                        
                        # Get AI commentary (with caching)
                        ai_key = f"{spot_id}-{day}-{block}"
                        if ai_key not in ai_cache:
                            print(f"   🤖 AI for {spot_config['name']} (day {day+1}, block {block+1})...")
                            ai_text = get_ai_commentary(
                                spot_config['name'], swell_height, swell_period,
                                wind_speed, wind_label, assessment
                            )
                            ai_cache[ai_key] = ai_text
                            time.sleep(0.5)  # Rate limit AI calls
                        else:
                            ai_text = ai_cache[ai_key]
                        
                        # Build title and description
                        title = f"{assessment['rating']} {swell_height}m @ {int(swell_period)}s {wind_label}"
                        
                        desc_lines = [
                            ai_text,
                            "",
                            f"🌊 Swell: {swell_height}m @ {int(swell_period)}s",
                            f"💨 Wind: {wind_speed}km/h {wind_compass} ({wind_label})",
                            f"💨 Gusts: {wind_gusts}km/h",
                            f"🌊 Wind waves: {wind_wave_height}m",
                        ]
                        
                        if assessment['notes']:
                            desc_lines.append("")
                            desc_lines.append("📋 " + " • ".join(assessment['notes']))
                        
                        desc = "\n".join(desc_lines)
                        
                    except Exception as e:
                        print(f"⚠️ Error processing {spot_id}: {e}")
                        desc = f"Error: {e}"

                # Format times for XMLTV
                start_fmt = program_start.strftime("%Y%m%d%H%M%S +0000")
                stop_fmt = program_stop.strftime("%Y%m%d%H%M%S +0000")
                
                prog = ET.SubElement(root, "programme", start=start_fmt, stop=stop_fmt, channel=ch["id"])
                ET.SubElement(prog, "title", lang="en").text = title
                ET.SubElement(prog, "desc", lang="en").text = desc
                ET.SubElement(prog, "icon", src=icon_src)

    # Write XML
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ EPG generated: {output_file}")
    print(f"   📊 {len(CHANNELS)} channels × {days * 4} time blocks = {len(CHANNELS) * days * 4} programs")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate Surf EPG from Open-Meteo data")
    parser.add_argument("-d", "--days", type=int, default=1, help="Number of days to generate (default: 1)")
    parser.add_argument("-o", "--output", type=str, default="surf_epg.xml", help="Output filename (default: surf_epg.xml)")
    
    args = parser.parse_args()
    
    generate_xml(days=args.days, output_file=args.output)
