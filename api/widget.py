"""Endpoint mínimo para el widget de Android.

/api/dashboard devuelve el volcado completo (200 actividades con polylines):
demasiado para bajarlo cada media hora desde la pantalla de inicio. Esto son
solo los números que caben en el widget.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import json
from http.server import BaseHTTPRequestHandler
from _lib.cache import load
from _lib.metrics import current_body_battery


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        g = load("garmin") or {}
        s = load("strava") or {}
        m = load("metrics") or {}
        meta = load("meta") or {}

        daily = g.get("daily") or {}
        sleep = g.get("sleep") or {}
        heart = g.get("heart_rate") or {}
        fitness = (m.get("fitness") or {}).get("current") or {}
        readiness = m.get("readiness") or {}

        battery = current_body_battery(g)

        activities = sorted(
            s.get("activities") or [],
            key=lambda a: (a.get("date") or "", a.get("start_time") or ""),
            reverse=True,
        )
        last = activities[0] if activities else None

        payload = {
            "has_data": bool(meta),
            "synced_at": meta.get("garmin_synced") or meta.get("strava_synced") or "",
            "date": daily.get("date") or "",
            "steps": daily.get("steps") or 0,
            "steps_goal": daily.get("steps_goal") or 10000,
            "calories": daily.get("calories_total") or 0,
            "distance_km": daily.get("distance_km") or 0,
            "active_minutes": daily.get("active_minutes") or 0,
            "resting_hr": daily.get("resting_hr") or heart.get("resting") or 0,
            "body_battery": battery,
            "stress": daily.get("avg_stress") or 0,
            "sleep_text": sleep.get("total_formatted") or "",
            "sleep_score": sleep.get("score") or 0,
            "ctl": fitness.get("ctl") or 0,
            "atl": fitness.get("atl") or 0,
            "tsb": fitness.get("tsb") or 0,
            "form_status": fitness.get("status") or "",
            "form_emoji": fitness.get("emoji") or "",
            "readiness": readiness.get("score") or 0,
            "readiness_status": readiness.get("status") or "",
            "last_activity": {
                "name": last.get("name") or "",
                "sport": last.get("sport") or "",
                "date": last.get("date") or "",
                "date_formatted": last.get("date_formatted") or "",
                "distance": last.get("distance") or 0,
                "time": last.get("time") or "",
            } if last else None,
        }

        body = json.dumps(payload, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
