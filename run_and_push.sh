#!/bin/bash
# This script runs on Render's cron job
# It generates the EPG and pushes it back to your GitHub repo

set -e  # Exit on any error

echo "🏄 Starting Surf EPG update..."

# Clone your repo (shallow clone for speed)
git clone --depth 1 https://${GITHUB_TOKEN}@github.com/OiErU/weather-dashboard.git repo
cd repo

# Run the EPG generator
echo "🌊 Generating EPG..."
python generate_epg.py -d 2

# Check if file changed
if git diff --quiet surf_epg.xml; then
    echo "📋 No changes to EPG, skipping commit."
    exit 0
fi

# Commit and push
echo "📤 Pushing to GitHub..."
git config user.name "Render Cron"
git config user.email "cron@render.com"
git add surf_epg.xml
git commit -m "Auto-update EPG $(date +'%Y-%m-%d %H:%M UTC')"
git push

echo "✅ Done!"
