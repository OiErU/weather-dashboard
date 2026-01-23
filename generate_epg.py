#!/usr/bin/env python3
"""
Surf Webcam EPG Generator (Google Grounding Edition)
True Chatbot Replication: Uses Gemini's native Google Search tool.
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
    HAS_AI = True
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
    else:
        print("⚠️ WARNING: GEMINI_API_KEY not found!")
except ImportError as e:
    HAS_AI = False
    print(f"⚠️ Missing libraries: {e}")

# Spot Definitions 
# (We keep coordinates for backup data, but the AI will now Google the spot name directly)
SPOTS_CONFIG = {
    "ericeira":   {"lat": 38.960, "lon": -9.500, "name": "Ericeira",   "facing": 290},
    "supertubos": {"lat": 39.320, "lon": -9.400, "name": "Supertubos", "facing": 240},
    "molheleste": {"lat": 39.320, "lon": -9.400, "name": "Molhe Leste","facing": 270},
    "baleal_s":   {"lat": 39.400, "lon": -9.380, "name": "Baleal South", "facing": 180},
    "baleal_n":   {"lat": 39.400, "lon": -9.380, "name": "Baleal North", "facing": 10},
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

def get_ai_report(spot_name, height, wind_speed, wind_label):
    """
    Uses Google Search Grounding to find the 'Vibe' and confirm data.
    """
    if not HAS_AI or not GEMINI_API_KEY:
        return f"Conditions: {height}m {wind_label}"

    # Backup data string in case search fails
    buoy_data = f"{height}m swell, {wind_speed}km/h {wind_label} wind"

    prompt = (
        f"Search for the current surf report and forecast for {spot_name} right now. "
        f"Compare it with this buoy data: {buoy_data}. "
        "Write a ONE-LINE, cynical, funny surf report for a local TV channel. "
        "If it's huge/blown out, warn them (e.g. 'washing machine'). "
        "If it's flat, mock it. "
        "Mention the size (in meters) and the vibe. "
        "Keep it under 25 words."
    )

    try:
        # Switch to Gemini 1.5 Flash which supports Search Grounding
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # This is the MAGIC LINE that enables Google Search
        response = model.generate_content(prompt, tools='google_search_retrieval')
        
        # Check if we got a valid text response
        if response.text:
            return response.text.strip().replace('"', '')
        return f"Conditions: {height}m {wind_label}"
        
    except Exception as e:
        print(f"⚠️ AI/Search Error: {e}")
        return f"Conditions: {height}m {wind_label}"

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
    root.set("generator-info-name", "Surf EPG Google")
    root.set("generator-info-url", BASE_URL)
    
    weather_cache = {}
    ai_cache = {}
    
    # 1. Fetch Data
    unique_spots = set(ch['spot'] for ch in CHANNELS)
    
    for spot_key in unique_spots:
        coords = SPOTS_CONFIG[spot_key]
        print(f"--- Processing {coords['name']} ---")
        weather_cache[spot_key] = get_surf_data(coords['lat'], coords['lon'])

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
                            print(f"   Googling {spot_info['name']}...")
                            ai_text = get_ai_report(spot_info['name'], wh, ws, wind_qual)
                            ai_cache[ai_key] = ai_text
                            time.sleep(1) # Be nice to API

                        rating = "⭐⭐" if "OFFSHORE" in wind_qual and wh > 1.0 else "🌊"
                        if wh > 4.0: rating = "⚠️"
                        
                        wind_display = "N/A" if ws < 1 else f"{ws}km/h {wind_qual}"

                        title = f"{rating} {wh}m | {ai_text[:30]}..."
                        desc = (f"{ai_text}\n\n"
                                f"📏 SWELL: {wh}m @ {wp}s\n"
                                f"🌬️ WIND: {wind_display}")
                                
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
