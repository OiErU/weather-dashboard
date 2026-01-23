#!/usr/bin/env python3
"""
Surf EPG Generator (Stormglass + Gemini Flash Lite)
FIXED: Added back the missing <channel> definitions so TiviMate works.
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
HAS_AI = False
try:
    from google import genai
    if GEMINI_API_KEY:
        client = genai.Client(api_key=GEMINI_API_KEY)
        HAS_AI = True
        print("✅ AI Client connected.")
except ImportError:
    print("⚠️ google-genai library not found.")
except Exception as e:
    print(f"⚠️ AI Client failed: {e}")

SPOTS_CONFIG = {
    "ericeira":   {"lat": 38.97, "lon": -9.42, "name": "Ericeira", "facing": 290},
    "supertubos": {"lat": 39.34, "lon": -9.36, "name": "Supertubos", "facing": 240},
    "molheleste": {"lat": 39.34, "lon": -9.36, "name": "Molhe Leste", "facing": 270},
    "baleal_s":   {"lat": 39.37, "lon": -9.34, "name": "Baleal South", "facing": 180},
    "baleal_n":   {"lat": 39.37, "lon": -9.34, "name": "Baleal North", "facing": 10},
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
    if not STORMGLASS_API_KEY:
        print("⚠️ No Stormglass Key")
        return None
    url = "https://api.stormglass.io/v2/weather/point"
    params = {
        'lat': lat, 'lng': lon,
        'params': 'waveHeight,wavePeriod,windSpeed,windDirection',
        'source': 'sg'
    }
    headers = {'Authorization': STORMGLASS_API_KEY}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️ SG Error: {e}")
        return None

def get_ai_commentary(spot_name, height, period, wind_speed, wind_label):
    if not HAS_AI:
        return f"{height}m swell."

    prompt = (
        f"You are a local surfer at {spot_name}. "
        f"OFFICIAL DATA: Swell {height} meters @ {period} seconds. Wind {wind_speed}km/h ({wind_label}).\n"
        "TASK: Write a ONE-SENTENCE funny/cynical surf report.\n"
        "- If it's messy/huge: Call it a 'washing machine' or 'mess'.\n"
        "- If it's good: Say it's firing.\n"
        "- Include the wave height in meters naturally.\n"
        "- Keep it under 20 words."
    )

    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash-lite', 
            contents=prompt
        )
        if response.text:
            return response.text.strip().replace('"', '')
        return f"{height}m swell (AI Silent)"
    except Exception as e:
        print(f"⚠️ AI Error: {e}")
        return f"{height}m swell (AI Error)"

def get_wind_label(wind_deg, facing_deg):
    if wind_deg is None or facing_deg is None: return ""
    diff = abs(wind_deg - facing_deg)
    if diff > 180: diff = 360 - diff
    if diff < 45: return "ONSHORE" 
    elif diff > 135: return "OFFSHORE"
    else: return "CROSS"

def generate_xml(days=1):
    root = ET.Element("tv")
    root.set("generator-info-name", "Surf EPG Fixed")
    root.set("generator-info-url", BASE_URL)
    
    # 1. Fetch Data
    weather_cache = {}
    unique_coords = set()
    for key, spot in SPOTS_CONFIG.items():
        unique_coords.add((spot['lat'], spot['lon']))
    
    print(f"🌍 Fetching data for {len(unique_coords)} unique locations...")

    for lat, lon in unique_coords:
        coord_key = f"{lat},{lon}"
        data = get_stormglass_data(lat, lon)
        weather_cache[coord_key] = data
        time.sleep(1)

    # --- CRITICAL FIX: DEFINE CHANNELS FIRST ---
    # This was missing in the previous version!
    for ch in CHANNELS:
        channel = ET.SubElement(root, "channel", id=ch["id"])
        ET.SubElement(channel, "display-name").text = ch["name"]
        ET.SubElement(channel, "icon", src=f"{BASE_URL}/logos/{ch['logo']}")
    # -------------------------------------------

    # 3. Build Programs
    start_time = datetime.now()
    ai_memory = {}

    for day in range(days):
        for block in range(4): 
            block_hour = block * 6
            program_start = start_time.replace(hour=block_hour, minute=0, second=0, microsecond=0) + timedelta(days=day)
            program_stop = program_start + timedelta(hours=6)
            target_hour_idx = (day * 24) + block_hour

            for ch in CHANNELS:
                spot_id = ch['spot']
                spot_info = SPOTS_CONFIG[spot_id]
                coord_key = f"{spot_info['lat']},{spot_info['lon']}"
                spot_data = weather_cache.get(coord_key)
                
                title = f"{ch['name']}"
                desc = "No Data"

                if spot_data and 'hours' in spot_data:
                    try:
                        hours_list = spot_data['hours']
                        safe_idx = min(target_hour_idx, len(hours_list) - 1)
                        h = hours_list[safe_idx]

                        wh = round(float(h['waveHeight']['sg']), 1)
                        wp = round(float(h['wavePeriod']['sg']), 1)
                        ws = round(float(h['windSpeed']['sg']) * 3.6) 
                        wd = float(h['windDirection']['sg'])
                        
                        wind_qual = get_wind_label(wd, spot_info['facing'])
                        
                        ai_key = f"{spot_id}-{day}-{block}"
                        if ai_key in ai_memory:
                            ai_text = ai_memory[ai_key]
                        else:
                            print(f"   Asking AI about {spot_info['name']}...")
                            ai_text = get_ai_commentary(spot_info['name'], wh, wp, ws, wind_qual)
                            ai_memory[ai_key] = ai_text
                            time.sleep(1)

                        rating = "⭐⭐" if "OFFSHORE" in wind_qual and wh > 1.0 else "🌊"
                        if wh > 3.5: rating = "⚠️"
                        
                        title = f"{rating} {wh}m {wind_qual} @ {wp}s"
                        
                        desc = (f"{ai_text}\n\n"
                                f"🌊 Size: {wh}m @ {wp}s\n"
                                f"🌬️ Wind: {ws}km/h {wind_qual}")

                    except Exception as e:
                        print(f"Error {spot_id}: {e}")

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
