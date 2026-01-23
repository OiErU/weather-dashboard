#!/usr/bin/env python3
"""
Surf Webcam EPG Generator (Deep Water Edition)
Fixed: Coordinates moved offshore to get real wind.
Fixed: '0km/h' hidden if invalid.
Fixed: Search query tweaked for better intel.
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

# --- LIBRARIES ---
try:
    import google.generativeai as genai
    from ddgs import DDGS
    HAS_AI = True
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
    else:
        print("⚠️ WARNING: GEMINI_API_KEY not found in environment variables!")
except ImportError as e:
    HAS_AI = False
    print(f"⚠️ Missing libraries: {e}")

# Spot Definitions (Coordinates shifted 2km Offshore to avoid '0 wind' landmask issues)
SPOTS_CONFIG = {
    # Ericeira moved West
    "ericeira":   {"lat": 38.995, "lon": -9.450, "name": "Ericeira",   "facing": 290},
    # Supertubos moved South-West
    "supertubos": {"lat": 39.330, "lon": -9.380, "name": "Supertubos", "facing": 240},
    # Molhe Leste (Tricky, it's inside harbor, but we use Supertubos wind data nearby)
    "molheleste": {"lat": 39.330, "lon": -9.380, "name": "Molhe Leste","facing": 270},
    # Baleal moved North-West (Deep water)
    "baleal_s":   {"lat": 39.380, "lon": -9.360, "name": "Baleal South", "facing": 180},
    "baleal_n":   {"lat": 39.390, "lon": -9.360, "name": "Baleal North", "facing": 10},
}

CHANNELS = [
    {"id": "ericeira-surfline", "spot": "ericeira", "name": "Surfline Ericeira", "logo": "ericeira.png", "poster": "ericeira_poster.jpg"},
    {"id": "ericeira-meo", "spot": "ericeira", "name": "MEO Ericeira", "logo": "ericeira.png", "poster": "ericeira_poster.jpg"},
    {"id": "supertubos-surfline", "spot": "supertubos", "name": "Surfline Supertubos", "logo": "supertubos.png", "poster": "supertubos_poster.jpg"},
    {"id": "supertubos-meo", "spot": "supertubos", "name": "MEO Beachcam Supertubos", "logo": "supertubos.png", "poster": "supertubos_poster.jpg"},
    {"id": "molheleste-surfline", "spot": "molheleste", "name": "Surfline Molhe Leste", "logo": "molheleste.png", "poster": "molheleste_poster.jpg"},
    {"id": "molheleste-meo", "spot": "molheleste", "name": "MEO Beachcam Molhe Leste", "logo": "molheleste.png", "poster": "molheleste_poster.jpg"},
    {"id": "baia-meo", "spot": "baleal_s", "name": "MEO Baia", "logo": "baleal.png", "poster": "baleal_poster.jpg"},
    {"id": "cantinho-surfline", "spot": "baleal_s", "name": "Surfline Cantinho", "logo": "cantinho.png", "poster": "cantinho_poster.jpg"},
    {"id": "cantinho-meo", "spot": "baleal_s", "name": "MEO Cantinho", "logo": "cantinho.png", "poster": "cantinho_poster.jpg"},
    {"id": "baleal-surfline", "spot": "baleal_n", "name": "Surfline Baleal", "logo": "baleal.png", "poster": "baleal_poster.jpg"},
    {"id": "lagide-surfline", "spot": "baleal_n", "name": "Surfline Lagide", "logo": "lagide.png", "poster": "lagide_poster.jpg"},
    {"id": "lagide-meo", "spot": "baleal_n", "name": "MEO Lagide", "logo": "lagide.png", "poster": "lagide_poster.jpg"},
]

def search_web_report(spot_name):
    """Searches for 'Forecast Discussion' to avoid generic headers."""
    try:
        # Changed query to find more text-heavy results
        query = f"{spot_name} surf forecast text discussion"
        results = DDGS().text(query, max_results=1)
        results_list = list(results)
        if results_list:
            return results_list[0]['body']
        return "No web report found."
    except Exception as e:
        print(f"⚠️ Search skipped for {spot_name}: {e}")
        return ""

def get_ai_analysis(spot_name, height, wind_speed, wind_label, search_text):
    if not HAS_AI or not GEMINI_API_KEY:
        return f"Surf: {height}m. Wind: {wind_speed}km/h."

    # Tell AI to hunt for wind if missing
    wind_context = f"{wind_speed}km/h ({wind_label})" if wind_speed > 0 else "UNKNOWN/BROKEN SENSOR"

    prompt = (
        f"You are a local surf reporter for {spot_name}.\n"
        f"OFFICIAL BUOY DATA: Swell {height}m, Wind {wind_context}.\n"
        f"WEB SEARCH SNIPPET: \"{search_text}\"\n\n"
        "TASK: Write a ONE SENTENCE funny status update.\n"
        "- If Buoy Wind is UNKNOWN, try to find wind direction in the Web Snippet.\n"
        "- If the Web Snippet is generic, make a joke about the data being lost at sea.\n"
        "- Keep it under 20 words."
    )

    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text.strip().replace('"', '')
    except Exception as e:
        print(f"⚠️ FATAL AI ERROR: {e}") # This will show in GitHub Logs
        return f"Conditions: {height}m (AI Offline)"

def get_surf_data(lat, lon):
    url = "https://marine-api.open-meteo.com/v1/marine"
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "wave_height,wave_period,wind_speed_10m,wind_direction_10m",
        "timezone": "auto", "forecast_days": 1
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️ Open-Meteo skipped: {e}")
        return None

def get_wind_label(wind_deg, facing_deg):
    if wind_deg is None or facing_deg is None: return ""
    diff = abs(wind_deg - facing_deg)
    if diff > 180: diff = 360 - diff
    if diff < 45: return "ONSHORE" 
    elif diff > 135: return "OFFSHORE"
    else: return "CROSS"

def generate_xml(days=2):
    root = ET.Element("tv")
    root.set("generator-info-name", "Surf EPG DeepWater")
    root.set("generator-info-url", BASE_URL)
    
    weather_cache = {}
    search_cache = {}
    ai_cache = {}
    
    # 1. Fetch Data
    unique_spots = set(ch['spot'] for ch in CHANNELS)
    
    for spot_key in unique_spots:
        coords = SPOTS_CONFIG[spot_key]
        print(f"--- Processing {coords['name']} ---")
        
        weather_cache[spot_key] = get_surf_data(coords['lat'], coords['lon'])
        
        print(f"   Searching web...")
        search_cache[spot_key] = search_web_report(coords['name'])
        time.sleep(1)

    # 2. Build XML
    for ch in CHANNELS:
        channel = ET.SubElement(root, "channel", id=ch["id"])
        ET.SubElement(channel, "display-name").text = ch["name"]
        ET.SubElement(channel, "icon", src=f"{BASE_URL}/logos/{ch['logo']}")

    start_time = datetime.now()
    
    for day in range(days):
        for block in range(4): 
            block_hour = block * 6
            program_start = start_time.replace(hour=block_hour, minute=0, second=0, microsecond=0) + timedelta(days=day)
            program_stop = program_start + timedelta(hours=6)
            hour_index = (day * 24) + block_hour
            
            for ch in CHANNELS:
                spot_id = ch['spot']
                spot_info = SPOTS_CONFIG[spot_id]
                spot_data = weather_cache.get(spot_id)
                search_text = search_cache.get(spot_id, "")
                
                ai_key = f"{day}-{spot_id}"
                
                title = f"{ch['name']} - Live"
                desc = "No Data"

                if spot_data and 'hourly' in spot_data:
                    try:
                        h = spot_data['hourly']
                        idx = min(hour_index, len(h['wave_height']) - 1)
                        
                        wh = h['wave_height'][idx] or 0
                        wp = h['wave_period'][idx] or 0
                        ws = h['wind_speed_10m'][idx] or 0
                        wd = h['wind_direction_10m'][idx]
                        
                        wind_qual = get_wind_label(wd, spot_info['facing'])
                        
                        if ai_key in ai_cache:
                            ai_text = ai_cache[ai_key]
                        else:
                            print(f"   Asking Gemini about {spot_info['name']}...")
                            ai_text = get_ai_analysis(spot_info['name'], wh, ws, wind_qual, search_text)
                            ai_cache[ai_key] = ai_text
                            time.sleep(0.5)

                        rating = "⭐⭐" if "OFFSHORE" in wind_qual and wh > 1.0 else "🌊"
                        if wh > 4.0: rating = "⚠️"
                        
                        # LOGIC: Hide "0 km/h" if bad data
                        if ws < 1:
                            wind_display = "N/A"
                        else:
                            wind_display = f"{ws}km/h {wind_qual}"

                        title = f"{rating} {wh}m {wind_qual} | {ai_text[:25]}..."
                        desc = (f"{ai_text}\n\n"
                                f"📏 SWELL: {wh}m @ {wp}s\n"
                                f"🌬️ WIND: {wind_display}\n"
                                f"🔍 WEB INTEL: {search_text[:120]}...")
                                
                    except Exception as e:
                        print(f"Error building desc: {e}")

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
