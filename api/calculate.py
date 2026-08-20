import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from _lib.cache import save, load
from _lib.metrics import calculate_all

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            garmin = load("garmin") or {}
            strava = load("strava") or {}
            if not garmin and not strava:
                self._r(404, {"error": "No hay datos. Pulsa Sync primero."})
                return
            metrics = calculate_all(garmin, strava)
            metrics["calculated_at"] = datetime.now().isoformat()
            save("metrics", metrics)
            meta = load("meta") or {}
            meta["metrics_calculated"] = metrics["calculated_at"]
            save("meta", meta)
            self._r(200, {"status": "ok", "calculated_at": metrics["calculated_at"],
                          "readiness": metrics.get("readiness", {}).get("score"),
                          "tsb": metrics.get("fitness", {}).get("current", {}).get("tsb")})
        except Exception as e:
            self._r(500, {"error": str(e)})

    def _r(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
