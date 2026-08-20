import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from _lib.garmin_client import GarminClient
from _lib.cache import save, load

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            g = GarminClient()
            if not g.connect():
                self._r(503, {"error": "No se pudo conectar con Garmin"})
                return
            data = g.get_full_snapshot()
            data["synced_at"] = datetime.now().isoformat()
            save("garmin", data)
            meta = load("meta") or {}
            meta["garmin_synced"] = data["synced_at"]
            save("meta", meta)
            self._r(200, {
                "status": "ok", "source": "garmin", "synced_at": data["synced_at"],
                "steps": data.get("daily", {}).get("steps", 0),
                "sleep_score": data.get("sleep", {}).get("score", 0),
                "resting_hr": data.get("daily", {}).get("resting_hr", 0),
                "hrv": data.get("hrv", {}).get("last_night_avg", 0),
                "weekly_data": {
                    "steps_days": len(data.get("steps_week", [])),
                    "hrv_days": len(data.get("hrv_week", [])),
                    "sleep_days": len(data.get("sleep_week", [])),
                    "rhr_weeks": len(data.get("rhr_trend", [])),
                },
            })
        except Exception as e:
            self._r(500, {"error": str(e)})

    def _r(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
