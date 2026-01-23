#!/usr/bin/env python3
"""
Surf Webcam EPG Generator (Final Fixed Version)
Updates: Python 3.11 support, 'ddgs' library, and strict timeouts.
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
    # NEW: Import directly from the new 'ddgs' package
    from ddgs import DDGS
    HAS_AI = True
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
except ImportError as e:
    HAS_AI = False
    print(f"⚠️ Missing libraries: {e}")

# Spot Definitions
SPOTS_CONFIG = {
    "ericeira":   {"lat": 38.995, "lon": -9.425, "name": "Ericeira",   "facing": 290},
    "supertubos": {"lat": 39.345, "lon": -9.365, "name": "Supertubos", "facing": 240},
    "molheleste": {"lat": 39.355, "lon": -9.375, "name": "Molhe Leste","facing": 270},
    "baleal_s":   {"lat": 39.372, "lon": -9.338, "name": "Baleal South", "facing": 180},
    "baleal_n":   {"lat": 39.382, "lon": -9.338, "name": "Baleal North", "facing": 10},
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

def search_web_report(spot_name):
    """Searches using the new ddgs library with strict timeout."""
    try:
        query = f"surf report {spot_name} current conditions today"
        # We limit to 1 result to be super fast and avoid hangs
        results = DDGS().text(query, max_results=1)
        # Convert generator to list to force execution
        results_list = list(results)
        if results_list:
            return results_list[0]['body']
        return ""
    except Exception as e:
        print(f"⚠️ Search skipped for {spot_name}: {e}")
        return ""

def get_ai_analysis(spot_name, height, wind_speed, wind_label, search_text):
    if not HAS_AI or not GEMINI_API_KEY:
        return f"Surf: {height}m. Wind: {wind_speed}km/h."

    prompt = (
        f"Act as a cool surfer. Analyze: {spot_name}.\n"
        f"Buoy: {height}m, {wind_speed}km/h ({wind_label}).\n"
        f"Web: {search_text}\n"
        "Write a ONE SENTENCE funny summary. "
        "Prioritize Web info if Buoy looks wrong. "
        "Keep it under 25 words."
    )

    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text.strip().replace('"', '')
    except Exception as e:
        print(f"⚠️ AI skipped: {e}")
        return f"Conditions: {height}m {wind_label}"

def get_surf_data(lat, lon):
    url = "https://marine-api.open-meteo.com/v1/marine"
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "wave_height,wave_period,wind_speed_10m,wind_direction_10m",
        "timezone": "auto", "forecast_days": 1
    }
    try:
        # Timeout is crucial to prevent hanging
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
    root.set("generator-info-name", "Surf EPG Final")
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
        # Pause to be polite to the search engine
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
                        
                        title = f"{rating} {wh}m {wind_qual} | {ai_text[:25]}..."
                        desc = (f"{ai_text}\n\n"
                                f"📏 SWELL: {wh}m @ {wp}s\n"
                                f"🌬️ WIND: {ws}km/h {wind_qual}\n"
                                f"🔍 WEB INTEL: {search_text[:100]}...")
                                
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
