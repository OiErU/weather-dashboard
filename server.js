// server.js
const express = require('express');
const cors = require('cors');
const path = require('path');
const fetch = require('node-fetch'); // OK on Render; you can switch to global fetch later

const app = express();

// Use platform port in production; fallback to 3000 locally
const PORT = process.env.PORT || 3000;

// Secret API key is provided by Render Env Vars (never hard-code)
const API_KEY = process.env.WEATHER_API_KEY;
if (!API_KEY) {
  console.error('Missing WEATHER_API_KEY environment variable.');
  process.exit(1);
}

// Basic hardening + JSON
app.use(cors());
app.use(express.json());

// Serve static files (the PWA UI lives in /public)
app.use(express.static(path.join(__dirname, 'public'), {
  maxAge: '1h',
  setHeaders(res, filePath) {
    if (filePath.endsWith('sw.js')) {
      // Ensure the service worker is always fresh
      res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    }
  }
}));

// --- Helpers ---
const wApi = (stationId) =>
  `https://api.weather.com/v2/pws/observations/current?stationId=${stationId}&format=json&units=m&apiKey=${API_KEY}`;

const maskKey = (url) => url.replace(/(apiKey=)[^&]+/i, '$1***');

// --- Endpoints ---

// Health check (Render uses this if you set it)
app.get('/api/health', (_req, res) => {
  console.log('💚 Health check');
  res.json({ status: 'healthy', timestamp: new Date().toISOString(), server: 'Weather Dashboard API' });
});

// Single-station fetch
app.get('/api/weather/:stationId', async (req, res) => {
  const { stationId } = req.params;
  console.log(`🌤️ Fetching station ${stationId}`);

  try {
    const url = wApi(stationId);
    console.log('📡 GET', maskKey(url));

    const response = await fetch(url);
    if (!response.ok) throw new Error(`Upstream error: ${response.status} ${response.statusText}`);

    const data = await response.json();
    if (!data.observations?.length) throw new Error('No observations found');

    const obs = data.observations[0];

    console.log(`✅ ${stationId}`, {
      temp: obs.metric?.temp,
      humidity: obs.humidity,
      windSpeed: obs.metric?.windSpeed
    });

    res.json({ success: true, data: obs, stationId, timestamp: new Date().toISOString() });
  } catch (err) {
    console.error(`❌ ${stationId}`, err.message);
    res.status(500).json({ success: false, error: err.message, stationId, timestamp: new Date().toISOString() });
  }
});

// All-stations fetch (with special wind source for IVAU4)
app.get('/api/weather-all', async (_req, res) => {
  const stations = ['IVAU4', 'IATOUG14', 'IABBEY4'];
  const windStation = 'INADAD1'; // wind data source for IVAU4

  console.log('🌍 Fetching all stations:', stations.join(', '));

  try {
    const results = await Promise.all(
      stations.map(async (stationId) => {
        try {
          const url = wApi(stationId);
          console.log('📡 GET', maskKey(url));
          const r = await fetch(url);
          if (!r.ok) throw new Error(`Upstream error: ${r.status} ${r.statusText}`);

          const json = await r.json();
          if (!json.observations?.length) throw new Error('No observations found');

          let obs = json.observations[0];

          // If IVAU4, enrich with wind from INADAD1
          if (stationId === 'IVAU4') {
            try {
              const windUrl = wApi(windStation);
              console.log(`💨 Wind fallback GET`, maskKey(windUrl));
              const wr = await fetch(windUrl);
              if (wr.ok) {
                const wj = await wr.json();
                if (wj.observations?.length) {
                  const wObs = wj.observations[0];
                  obs.winddir = wObs.winddir;
                  obs.metric = obs.metric || {};
                  obs.metric.windSpeed = wObs.metric?.windSpeed ?? obs.metric.windSpeed ?? 0;
                  obs.metric.windGust = wObs.metric?.windGust ?? obs.metric.windGust ?? 0;
                }
              }
            } catch (wErr) {
              console.warn(`⚠️ Wind fallback failed for ${stationId}`, wErr.message);
            }
          }

          console.log(`✅ OK ${stationId}`, {
            temp: obs.metric?.temp,
            humidity: obs.humidity,
            windSpeed: obs.metric?.windSpeed,
            winddir: obs.winddir,
            rainTotal: obs.metric?.precipTotal
          });

          return { stationId, success: true, data: obs };
        } catch (err) {
          console.error(`❌ Fail ${stationId}`, err.message);
          return { stationId, success: false, error: err.message };
        }
      })
    );

    console.log('🎉 All-stations complete');
    res.json({ success: true, results, timestamp: new Date().toISOString() });
  } catch (err) {
    console.error('❌ All-stations error', err.message);
    res.status(500).json({ success: false, error: err.message, timestamp: new Date().toISOString() });
  }
});

// Root -> serve the dashboard
app.get('/', (_req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Start
app.listen(PORT, () => {
  console.log('🌤️ Weather Dashboard Server Started');
  console.log(`🚀 http://localhost:${PORT}`);
});
