"""
GET /api/plan            → próximos entrenos programados (lo guardado en Redis)
GET /api/plan?refresh=1  → los vuelve a descargar del calendario de Garmin

Son los entrenos de Garmin Coach y los que programes a mano en Garmin
Connect, con sus pasos (calentamiento, series, ritmos, zonas).

Va aparte de sync-garmin para que un fallo del calendario no tumbe la
sincronización de sueño/HRV, y porque pedir el detalle de cada entreno son
una docena de llamadas más.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from _lib.garmin_client import GarminClient
from _lib.cache import save, load


def refresh_plan(meta=None):
    g = GarminClient()
    if not g.connect():
        raise RuntimeError("No se pudo conectar con Garmin")
    data = {"workouts": g.get_scheduled_workouts(),
            "synced_at": datetime.now().isoformat()}
    save("garmin_plan", data)
    if meta is not None:
        meta["plan_synced"] = data["synced_at"]
    return data


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        try:
            if q.get("refresh"):
                meta = load("meta") or {}
                data = refresh_plan(meta)
                save("meta", meta)
            else:
                data = load("garmin_plan") or {"workouts": [], "synced_at": None}
            self._r(200, data)
        except Exception as e:
            self._r(503 if "conectar" in str(e) else 500, {"error": str(e)})

    def _r(self, code, payload):
        body = json.dumps(payload, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
