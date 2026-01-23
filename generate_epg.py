#!/usr/bin/env python3
"""
Surf EPG Generator (Stormglass.io Edition)
Strategy:
1. Groups spots by coordinates to minimize API calls (Smart Caching).
2. Uses Stormglass 'sg' source for premium maritime data.
3. Feeds precise data to Gemini for 'funny' human-like reports.
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
STORMGLASS_API_KEY = os.environ.get("STORMGLASS_API_KEY")

# --- LIBRARIES ---
try:
    import google.generativeai as genai
    HAS_AI = True
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
except ImportError:
    HAS_AI = False

# SPOT CONFIGURATION
# Notice: Some spots share coordinates. The script will detect this and only make 1 API call per unique pair.
SPOTS_CONFIG = {
    "ericeira":   {"lat": 38.97, "lon": -9.42, "name": "Ericeira", "facing": 290},
    "supertubos": {"lat": 39.34, "lon": -9.36, "name": "Supertubos", "facing": 240},
    "molheleste": {"lat": 39.34, "lon": -9.36, "name": "Molhe Leste", "facing": 270}, # Same as Supertubos
    "baleal_s":   {"lat": 39.37, "lon": -9.34, "name": "Baleal South", "facing": 180},
    "baleal_n":   {"lat": 39.37, "lon": -9.34, "name": "Baleal North", "facing": 10},  # Same as South
}

CHANNELS = [
    {"id": "ericeira-surfline", "spot": "ericeira", "name": "Surfline Ericeira", "logo": "ericeira.png", "poster": "ericeira_poster.jpg"},
    {"id": "ericeira-meo", "spot": "ericeira", "name": "MEO Ericeira", "logo": "ericeira.png", "poster": "ericeira_poster.jpg"},
    {"id": "supertubos-surfline", "spot": "supertubos", "name": "Surfline Supertubos", "logo": "supertubos.png", "poster": "supertubos_poster.jpg"},
    {"id": "supertubos-meo", "spot": "supertubos", "name": "MEO Supertubos", "logo": "supertubos.png", "poster": "supertubos_poster.jpg"},
    {"id": "molheleste-surfline", "spot": "molheleste", "name": "Surfline Molhe Leste", "logo": "molheleste.png", "poster": "molheleste_poster.jpg"},
    {"id": "molheleste-meo", "spot": "molheleste", "name": "MEO Molhe Leste", "logo": "molheleste.png", "poster": "molheleste_poster.jpg"},
    {"id": "baia-meo", "spot": "baleal_s", "name": "MEO Baia", "logo": "baleal.png", "poster": "baleal_poster.jpg"},
    {"id": "cantinho-surfline", "spot": "baleal_s", "name": "Surfline Cantinho", "logo": "cantinho.png", "poster": "cantinho_poster.jpg"},
    {"id": "cantinho-meo", "spot": "baleal_s", "name": "MEO Cantinho", "logo": "cantinho.png", "poster": "cantinho_poster.jpg"},
    {"id": "baleal-surfline", "spot": "baleal_n", "name": "Surfline Baleal", "logo": "baleal.png", "poster": "baleal_poster.jpg"},
    {"id": "lagide-surfline", "spot": "baleal_n", "name": "Surfline Lagide", "logo": "lagide.png", "poster": "lagide_poster.jpg"},
    {"id": "lagide-meo", "spot": "baleal_n", "name": "MEO Lagide", "logo": "lagide.png", "poster": "lagide_poster.jpg"},
]

def get_stormglass_data(lat, lon):
    """
    Fetches wave and wind data from Stormglass.io.
    Counts as 1 request per call.
    """
    if not STORMGLASS_API_KEY:
        print("⚠️ No Stormglass API Key found.")
        return None

    url = "https://api.stormglass.io/v2/weather/point"
    # We request all parameters in ONE call to save quota
    params = {
        'lat': lat,
        'lng': lon,
        'params': 'waveHeight,wavePeriod,windSpeed,windDirection',
        'source': 'sg' # 'sg' mixes multiple models for best accuracy
    }
    headers = {'Authorization': STORMGLASS_API_KEY}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️ Stormglass Error ({lat}, {lon}): {e}")
        return None

def get_ai_commentary(spot_name, height, period, wind_speed, wind_label):
    """
    Gemini generates the funny/gnarly report based on the precise data.
    """
    if not HAS_AI or not GEMINI_API_KEY:
        return f"{height}m swell, {wind_speed}km/h wind."

    # Contextualize wind
    wind_desc = f"{wind_speed}km/h ({wind_label})"

    prompt = (
        f"You are a local surfer at {spot_name}. "
        f"Here is the OFFICIAL DATA: Swell {height} meters @ {period} seconds. Wind {wind_desc}.\n"
        "TASK: Write a funny, cynical one-sentence surf report.\n"
        "- If it's big (3m+) and onshore: It's a 'washing machine' or 'death wish'.\n"
        "- If it's flat: Joke about sleeping or bringing a longboard.\n"
        "- If it's pumping (offshore + good size): Say it.\n"
        "- INCLUDE the wave height (in meters) and period in your sentence naturally.\n"
        "- Keep it under 20 words."
    )

    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text.strip().replace('"', '')
    except Exception as e:
        print(f"⚠️ AI Error: {e}")
        return f"{height}m @ {period}s {wind_label}"

def get_wind_label(wind_deg, facing_deg):
    if wind_deg is None or facing_deg is None: return ""
    diff = abs(wind_deg - facing_deg)
    if diff > 180: diff = 360 - diff
    if diff < 45: return "ONSHORE" 
    elif diff > 135: return "OFFSHORE"
    else: return "CROSS"

def generate_xml(days=1):
    root = ET.Element("tv")
    root.set("generator-info-name", "Surf EPG Stormglass")
    root.set("generator-info-url", BASE_URL)
    
    # --- STEP 1: SMART FETCHING ---
    # We identify unique coordinates to avoid duplicate API calls
    weather_cache = {} # Key: "lat,lon" -> Value: JSON Data
    
    unique_coords = set()
    for key, spot in SPOTS_CONFIG.items():
        unique_coords.add((spot['lat'], spot['lon']))
    
    print(f"🌍 Optimization: Found {len(SPOTS_CONFIG)} spots, but only need {len(unique_coords)} API calls.")

    # Fetch data for unique locations
    for lat, lon in unique_coords:
        coord_key = f"{lat},{lon}"
        print(f"📡 Calling Stormglass for {lat}, {lon}...")
        data = get_stormglass_data(lat, lon)
        weather_cache[coord_key] = data
        time.sleep(1) # Be nice to the API

    # --- STEP 2: BUILD EPG ---
    start_time = datetime.now()
    ai_memory = {} # Don't ask AI twice for the same spot description

    for day in range(days):
        for block in range(4): 
            block_hour = block * 6
            program_start = start_time.replace(hour=block_hour, minute=0, second=0, microsecond=0) + timedelta(days=day)
            program_stop = program_start + timedelta(hours=6)
            
            # Stormglass returns hourly data. We need to find the matching hour in the response.
            # Usually the response starts from 00:00 UTC today.
            target_hour_idx = (day * 24) + block_hour

            for ch in CHANNELS:
                spot_id = ch['spot']
                spot_info = SPOTS_CONFIG[spot_id]
                coord_key = f"{spot_info['lat']},{spot_info['lon']}"
                
                spot_data = weather_cache.get(coord_key)
                
                title = f"{ch['name']} - Live"
                desc = "No Data"

                if spot_data and 'hours' in spot_data:
                    try:
                        # Find the correct hour in the array
                        hours_list = spot_data['hours']
                        # Safety check: ensure index is within bounds
                        safe_idx = min(target_hour_idx, len(hours_list) - 1)
                        hour_data = hours_list[safe_idx]

                        # Extract Data (Stormglass 'sg' source)
                        wh = float(hour_data['waveHeight']['sg'])
                        wp = float(hour_data['wavePeriod']['sg'])
                        ws_mps = float(hour_data['windSpeed']['sg']) 
                        ws_kph = round(ws_mps * 3.6) # Convert m/s to km/h
                        wd = float(hour_data['windDirection']['sg'])
                        
                        wind_qual = get_wind_label(wd, spot_info['facing'])
                        
                        # AI Generation (Once per spot per day/block to save time)
                        ai_key = f"{spot_id}-{day}-{block}"
                        if ai_key in ai_memory:
                            ai_text = ai_memory[ai_key]
                        else:
                            print(f"   🤖 Asking AI about {spot_info['name']}...")
                            ai_text = get_ai_commentary(spot_info['name'], wh, wp, ws_kph, wind_qual)
                            ai_memory[ai_key] = ai_text
                            time.sleep(0.5)

                        # Icons
                        rating = "⭐⭐" if "OFFSHORE" in wind_qual and wh > 1.0 else "🌊"
                        if wh > 3.5: rating = "⚠️"
                        
                        title = f"{rating} {wh}m {wind_qual} | {ai_text[:25]}..."
                        desc = (f"{ai_text}\n\n"
                                f"📏 SWELL: {wh}m @ {wp}s\n"
                                f"🌬️ WIND: {ws_kph}km/h {wind_qual}\n"
                                f"🌊 SOURCE: Stormglass.io")

                    except Exception as e:
                        print(f"Error processing {spot_id}: {e}")

                start_fmt = program_start.strftime("%Y%m%d%H%M%S +0000")
                stop_fmt = program_stop.strftime("%Y%m%d%H%M%S +0000")
                
                prog = ET.SubElement(root, "programme", start=start_fmt, stop=stop_fmt, channel=ch["id"])
                ET.SubElement(prog, "title", lang="en").text = title
                ET.SubElement(prog, "desc", lang="en").text = desc
                ET.SubElement(prog, "icon", src=f"{BASE_URL}/posters/{ch['poster']}")

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    tree.write("surf_epg.xml", encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    generate_xml()
