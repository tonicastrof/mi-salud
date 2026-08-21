"""
GET /api/day?date=2026-08-15
Consulta datos de Garmin de cualquier día.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from _lib.garmin_client import GarminClient

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        date = parse_qs(urlparse(self.path).query).get("date", [None])[0]
        if not date:
            self._r(400, {"error": "Falta parámetro date (YYYY-MM-DD)"})
            return
        try:
            g = GarminClient()
            if not g.connect():
                self._r(503, {"error": "No se pudo conectar con Garmin"})
                return
            result = {
                "date": date,
                "daily": g.get_daily(date),
                "sleep": g.get_sleep(date),
                "heart_rate": g.get_heart_rate(date),
                "stress": g.get_stress(date),
                "body_battery": g.get_body_battery(date),
                "hrv": g.get_hrv(date),
                "spo2": g.get_spo2(date),
                "respiration": g.get_respiration(date),
            }
            self._r(200, result)
        except Exception as e:
            self._r(500, {"error": str(e)})

    def _r(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(payload, default=str).encode())
