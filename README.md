# ChicagoLMap

A real-time map of every CTA 'L' train in Chicago, with an ML delay predictor being trained in the background using live data collected 24/7.

---

## What it does

The map shows all 8 CTA rail lines — Red, Blue, Green, Brown, Orange, Purple, Pink, and Yellow — with live train positions updated every 15 seconds. Each train marker is a directional teardrop that points the way the train is heading. You can switch between individual lines or show everything at once.

When you click any station, you get a live arrival board for both directions: next trains, ETAs pulled directly from CTA's own prediction system, and (once the predictor is trained) an ML-based delay estimate — "arriving in 4 min, likely running 2 min late."

The map has two data modes. When CTA's GPS system is live, trains show their exact position with a green indicator. When GPS is down or in schedule mode (which happens more than you'd think), the app falls back to querying every station in parallel and places each train at the station it's closest to by time — so the map never goes blank. A yellow badge tells you when you're in schedule mode.

---

## The delay predictor

The second half of this project is a machine learning pipeline that learns the CTA's delay patterns from real data.

Every 5 minutes, a GitHub Actions job polls the CTA Train Tracker API for every Red and Blue Line station, stores the arrival predictions to a Supabase database, then immediately runs the ETL pipeline: infer which trains actually arrived and when, compute the delay vs schedule, and build a feature row for that observation. Once a week, it retrains four models on everything collected so far.

The features the model learns from:

| Feature | What it captures |
|---|---|
| `hour_of_day`, `day_of_week`, `is_weekend` | Time patterns — rush hour vs midnight |
| `is_peak_am`, `is_peak_pm` | 7–9am and 4–7pm weekday crunch |
| `stop_sequence` | Where on the line — downtown stations behave differently than end-of-line |
| `minutes_until_arrival` | How close the train is right now |
| `eta_delta_1_min`, `eta_delta_2_min` | Is the ETA drifting? Trains that keep slipping are usually going to slip more |
| `headway_before_min`, `headway_after_min` | Spacing between trains — bunching is a strong delay signal |
| `is_scheduled`, `is_delayed_flag` | CTA's own flags |

The output is a point estimate (delay in minutes), a status label (ahead / on time / behind), and a p10–p90 confidence interval so you can see how uncertain the prediction is.

---

## Architecture

```
GitHub Actions (every 5 min)
  └── poll CTA API → arrival_snapshots (Supabase)
  └── arrival_inference → actual_arrivals
  └── feature_builder → model_features

GitHub Actions (every Sunday)
  └── train XGBoost + quantile models → GitHub Artifact

Flask map server (local / Render)
  └── serves index.html + Leaflet map
  └── proxies /api/trains/<route> → CTA Train Tracker
  └── proxies /api/station/<id>/arrivals → FastAPI predictor

FastAPI predictor (Render)
  └── loads trained models at startup
  └── returns delay estimates per station
```

The Flask app and FastAPI predictor are decoupled — if the predictor is unavailable, the map still works and station popups show raw CTA data. When the predictor is running, it quietly enriches every arrival with an ML estimate.

---

## Tech

- **Map**: Leaflet.js on CartoDB Dark Matter tiles, Apple Liquid Glass UI (backdrop-filter, specular pseudo-elements)
- **Backend**: Flask (Python), CTA Train Tracker JSON API, KMZ station geometry
- **Predictor**: FastAPI, SQLAlchemy, XGBoost (regressor + classifier + p10/p90 quantile), scikit-learn
- **Database**: Supabase (PostgreSQL)
- **Pipeline**: GitHub Actions cron (collect → infer → features → retrain)
- **Route lines**: Built from CTA GTFS shapes.txt

---

## Running locally

```bash
# Clone and install
git clone https://github.com/charannanduri/ChicagoLMap.git
cd ChicagoLMap
pip install -r requirements.txt

# Add your CTA API key (get one at transitchicago.com/developers/traintracker)
echo "your_api_key" > api_key.txt

# Start the map
python app.py
# → http://localhost:5001
```

To run the delay predictor locally alongside the map:

```bash
cd cta-delay-predictor
cp .env.example .env
# Edit .env: add CTA_TRAIN_TRACKER_KEY and a DATABASE_URL (local Postgres or Supabase)
docker compose up -d db          # local Postgres
python -m backend.gtfs.loader    # load CTA schedule data once
python -m backend.collector.service   # start collecting (runs every 25s)
uvicorn backend.api.main:app --port 8000  # start predictor API
```

Then set `DELAY_PREDICTOR_URL=http://localhost:8000` when running Flask and station popups will show ML predictions.

---

*Built by [Charan Nanduri](https://github.com/charannanduri)*
