#!/usr/bin/env python3
"""
Surf Webcam EPG Generator (Pro Version)
Fixes: Handles "Storm" conditions and missing wind data.
"""

import sys
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# --- CONFIGURATION ---
BASE_URL = "https://raw.githubusercontent.com/OiErU/weather-dashboard/main"

# Spot Definitions
SPOTS_CONFIG = {
    "ericeira":   {"lat": 38.99, "lon": -9.42, "name": "Ericeira",   "facing": 290},
    "supertubos": {"lat": 39.34, "lon": -9.36, "name": "Supertubos", "facing": 240},
    "molheleste": {"lat": 39.35, "lon": -9.37, "name": "Molhe Leste","facing": 270},
    "baleal_s":   {"lat": 39.37, "lon": -9.34, "name": "Baleal South", "facing": 180},
    "baleal_n":   {"lat": 39.38, "lon": -9.34, "name": "Baleal North", "facing": 10},
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

def get_surf_data(lat, lon):
    url = "https://marine-api.open-meteo.com/v1/marine"
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "wave_height,wave_period,wind_speed_10m,wind_direction_10m",
        "timezone": "auto", "forecast_days": 3
    }
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"API Error: {e}")
        return None

def get_wind_label(wind_deg, facing_deg):
    if wind_deg is None or facing_deg is None: return ""
    diff = abs(wind_deg - facing_deg)
    if diff > 180: diff = 360 - diff
    
    if diff < 45: return "ONSHORE 💨" 
    elif diff > 135: return "OFFSHORE 🟢"
    else: return "CROSS ↔️"

def judge_surf(height, period, wind_speed, wind_label):
    # Safety checks for Missing Data
    if height is None: height = 0
    if wind_speed is None: wind_speed = 0
    
    rating = ""
    status = "Choppy"
    
    # --- 1. DANGER CHECK (The Fix) ---
    if height > 4.0:
        return "⚠️ STORM / DANGEROUS", "Too Big"
    if height > 3.0:
        return "⚠️ XL / EXPERTS ONLY", "Huge"
    if wind_speed > 35:
        return "💨 BLOWN OUT", "Windy"

    # --- 2. QUALITY CHECK ---
    if height < 0.5: 
        status = "Flat"; rating = "😴"
    elif height > 2.0 and period > 11: 
        status = "PUMPING"; rating = "⭐⭐⭐"
    elif height > 1.2 and period > 9: 
        status = "Fun"; rating = "⭐"
    
    # --- 3. WIND PENALTY ---
    if "ONSHORE" in wind_label: 
        rating = ""; status = "Messy"
    if "OFFSHORE" in wind_label and height > 1.0: 
        rating += "⭐" # Bonus star for offshore
        
    return f"{rating} {status}", status

def generate_xml(days=3):
    root = ET.Element("tv")
    root.set("generator-info-name", "Surf EPG Pro")
    root.set("generator-info-url", BASE_URL)
    weather_cache = {}
    
    # Create Channels
    for ch in CHANNELS:
        channel = ET.SubElement(root, "channel", id=ch["id"])
        ET.SubElement(channel, "display-name").text = ch["name"]
        ET.SubElement(channel, "icon", src=f"{BASE_URL}/logos/{ch['logo']}")

    # Fetch Data
    unique_spots = set(ch['spot'] for ch in CHANNELS)
    for spot_key in unique_spots:
        coords = SPOTS_CONFIG[spot_key]
        print(f"Fetching forecast for {coords['name']}...")
        weather_cache[spot_key] = get_surf_data(coords['lat'], coords['lon'])

    # Generate Programs
    start_time = datetime.now()
    for day in range(days):
        for block in range(4): 
            block_hour = block * 6
            program_start = start_time.replace(hour=block_hour, minute=0, second=0, microsecond=0) + timedelta(days=day)
            program_stop = program_start + timedelta(hours=6)
            start_fmt = program_start.strftime("%Y%m%d%H%M%S +0000")
            stop_fmt = program_stop.strftime("%Y%m%d%H%M%S +0000")
            hour_index = (day * 24) + block_hour
            
            for ch in CHANNELS:
                spot_id = ch['spot']
                spot_info = SPOTS_CONFIG[spot_id]
                spot_data = weather_cache.get(spot_id)
                
                # Default values if fetch fails
                title = f"{ch['name']} - Live"
                desc = "Forecast Unavailable"
                
                if spot_data and 'hourly' in spot_data:
                    try:
                        h = spot_data['hourly']
                        idx = min(hour_index, len(h['wave_height']) - 1)
                        
                        # Safe Extraction (Fixes the "None" error)
                        wh = h['wave_height'][idx] if h['wave_height'][idx] is not None else 0
                        wp = h['wave_period'][idx] if h['wave_period'][idx] is not None else 0
                        # Try to get wind, default to 0 if None
                        ws = h['wind_speed_10m'][idx] if h['wind_speed_10m'][idx] is not None else 0
                        wd = h['wind_direction_10m'][idx]
                        
                        wind_qual = get_wind_label(wd, spot_info['facing'])
                        condition_str, simple_status = judge_surf(wh, wp, ws, wind_qual)
                        
                        title = f"{condition_str} | {wh}m {wind_qual}"
                        desc = (f"🌊 SWELL: {wh}m @ {wp}s ({simple_status})\n"
                                f"🌬️ WIND: {ws}km/h {wind_qual}\n"
                                f"📍 SPOT: {spot_info['name']}")
                    except Exception as e: 
                        print(f"Calc Error {ch['id']}: {e}")

                prog = ET.SubElement(root, "programme", start=start_fmt, stop=stop_fmt, channel=ch["id"])
                ET.SubElement(prog, "title", lang="en").text = title
                ET.SubElement(prog, "desc", lang="en").text = desc
                ET.SubElement(prog, "icon", src=f"{BASE_URL}/posters/{ch['poster']}")

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    tree.write("surf_epg.xml", encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    generate_xml()
