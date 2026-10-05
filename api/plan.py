"""
GET /api/plan            → próximos entrenos programados (lo guardado en Redis)
GET /api/plan?refresh=1  → los vuelve a descargar del calendario de Garmin
GET /api/compliance?date=2026-10-05&title=Base
                         → ese entreno, pedido frente a hecho (_lib/compliance.py)

/api/compliance se sirve desde aquí (ver vercel.json) porque el plan Hobby de
Vercel admite como mucho 12 funciones por despliegue.

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
from _lib.tz import ahora
from _lib.auth import authorized, deny
from _lib.workouts import mark_done
from _lib.compliance import compare, cache_key
from _lib.strava_client import StravaClient


def refresh_plan(meta=None):
    g = GarminClient()
    if not g.connect():
        raise RuntimeError("No se pudo conectar con Garmin")
    data = {"workouts": g.get_scheduled_workouts(),
            "synced_at": ahora().isoformat()}
    save("garmin_plan", data)
    if meta is not None:
        meta["plan_synced"] = data["synced_at"]
    return data


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
        # Según cómo reescriba Vercel la ruta, self.path puede ser la original
        # o la de plan.py: «date» solo lo usa la valoración
        if self.path.startswith("/api/compliance") or q.get("date"):
            return self._compliance(q)
        try:
            if q.get("refresh"):
                meta = load("meta") or {}
                data = refresh_plan(meta)
                save("meta", meta)
            else:
                data = load("garmin_plan") or {"workouts": [], "synced_at": None}
            strava = load("strava") or {}
            self._r(200, dict(data, workouts=mark_done(data.get("workouts"),
                                                       strava.get("activities"))))
        except Exception as e:
            self._r(503 if "conectar" in str(e) else 500, {"error": str(e)})

    def _compliance(self, q):
        """Cómo hiciste el entreno de ese día; las vueltas se piden a Strava
        una vez y el resultado se guarda (no cambian)."""
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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
