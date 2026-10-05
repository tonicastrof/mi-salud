"""
GET /api/compliance?date=2026-10-05&title=Base
  → cómo hiciste ese entreno frente a lo que pedía el plan (ver _lib/compliance.py)

Pide las vueltas de la actividad a Strava la primera vez y guarda el resultado:
las vueltas de una actividad ya hecha no cambian.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from _lib.cache import load, save
from _lib.auth import authorized, deny
from _lib.workouts import mark_done
from _lib.compliance import compare, cache_key
from _lib.strava_client import StravaClient


def find_done(date, title):
    """El entreno programado de ese día, ya cruzado con Strava, y su actividad."""
    plan = load("garmin_plan") or {}
    strava = load("strava") or {}
    acts = strava.get("activities") or []
    for w in mark_done(plan.get("workouts"), acts):
        if w.get("date") == date and (not title or w.get("title") == title):
            act_id = (w.get("done_activity") or {}).get("id")
            act = next((a for a in acts if a.get("id") == act_id), None)
            return w, act, strava
    return None, None, strava


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not authorized(self.headers):
            return deny(self)
        q = parse_qs(urlparse(self.path).query)
        date = q.get("date", [""])[0]
        title = q.get("title", [""])[0]
        if not date:
            self._r(400, {"error": "Falta date"})
            return
        try:
            w, act, strava = find_done(date, title)
            if not w:
                self._r(404, {"error": "No hay entreno programado ese día"})
                return
            if not w.get("done"):
                self._r(200, {"pending": True})
                return
            if not act:
                # Garmin dice que está hecho, pero la actividad aún no ha llegado a Strava
                self._r(200, {"pending": True, "error": "Sincroniza para traer la actividad de Strava"})
                return

            key = cache_key(act["id"], w)
            result = load(key)
            if not result:
                s = StravaClient()
                if not s.connect():
                    self._r(503, {"error": "Strava no disponible"})
                    return
                laps = s.get_laps(act["id"])
                hr_zones = (strava.get("zones") or {}).get("heartrate") or []
                result = compare(w, act, laps, hr_zones)
                if laps:
                    save(key, result)
            self._r(200, result)
        except Exception as e:
            self._r(500, {"error": str(e)})

    def _r(self, code, payload):
        body = json.dumps(payload, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
