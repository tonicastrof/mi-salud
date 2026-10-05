import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from _lib.strava_client import StravaClient
from _lib.cache import save, load
from _lib.tz import ahora
from _lib.auth import authorized, deny

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not authorized(self.headers):
            return deny(self)
        try:
            s = StravaClient()
            if not s.connect():
                self._r(503, {"error": "No se pudo conectar con Strava"})
                return
            data = s.get_full_snapshot()
            data["synced_at"] = ahora().isoformat()
            save("strava", data)
            meta = load("meta") or {}
            meta["strava_synced"] = data["synced_at"]
            save("meta", meta)
            self._r(200, {"status": "ok", "source": "strava", "synced_at": data["synced_at"],
                          "activities": len(data.get("activities", []))})
        except Exception as e:
            self._r(500, {"error": str(e)})

    def _r(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
