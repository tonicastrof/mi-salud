import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import json
from http.server import BaseHTTPRequestHandler
from _lib.cache import load

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        g = load("garmin") or {}
        s = load("strava") or {}
        m = load("metrics") or {}
        meta = load("meta") or {}

        payload = {
            "meta": meta,
            "has_data": bool(meta),
            "profile": s.get("profile", {}),
            # Garmin hoy
            "daily": g.get("daily", {}),
            "sleep": g.get("sleep", {}),
            "heart_rate": g.get("heart_rate", {}),
            "stress": g.get("stress", {}),
            "body_battery": g.get("body_battery", []),
            "hrv": g.get("hrv", {}),
            "spo2": g.get("spo2", {}),
            "respiration": g.get("respiration", {}),
            # Garmin semanal
            "steps_week": g.get("steps_week", []),
            "hrv_week": g.get("hrv_week", []),
            "sleep_week": g.get("sleep_week", []),
            "stress_week": g.get("stress_week", []),
            "rhr_trend": g.get("rhr_trend", []),
            "body_battery_week": g.get("body_battery_week", []),
            # Strava
            "activities": s.get("activities", []),
            "gear": s.get("gear", []),
            "zones": s.get("zones", {}),
            # Calculadas
            "fitness": m.get("fitness", {}),
            "acwr": m.get("acwr", {}),
            "race_predictions": m.get("race_predictions", []),
            "readiness": m.get("readiness", {}),
            "training_summary": m.get("training_summary", {}),
            "vo2max_estimated": m.get("vo2max_estimated"),
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(payload, default=str).encode())
