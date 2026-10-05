"""Endpoint mínimo para el widget de Android.

/api/dashboard devuelve el volcado completo (200 actividades con polylines):
demasiado para bajarlo cada media hora desde la pantalla de inicio. Esto son
solo los números que caben en el widget.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import json
import re
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from _lib.cache import load
from _lib.metrics import current_body_battery
from _lib.tz import hoy
from _lib.auth import authorized, deny


# Mismos tipos y colores que la tarjeta de la pestaña Coach (WTIPOS en index.html)
TIPOS = [
    (r"recover|recupera|regenera", "Recuperación", "#60A5FA"),
    (r"sprint|speed|velocidad", "Sprint", "#EC4899"),
    (r"anaer", "Anaeróbico", "#A855F7"),
    (r"vo2", "VO₂ máx", "#EF4444"),
    (r"threshold|umbral|lactate|lactato", "Umbral", "#F97316"),
    (r"tempo", "Tempo", "#F59E0B"),
    # Series sin más pistas («6x800»): después de umbral/tempo, que también usan NxM
    (r"interval|series|\d+\s*[x×]\s*\d+", "VO₂ máx", "#EF4444"),
    (r"long|larg|tirada", "Larga", "#14B8A6"),
    (r"base|aerob|easy|suave|rodaje", "Base", "#22C55E"),
]


def _next_workout(workouts):
    """El entreno de hoy o, si no hay, el siguiente programado."""
    today = hoy()
    pending = sorted((w for w in workouts or [] if (w.get("date") or "") >= today.isoformat()),
                     key=lambda w: w["date"])
    if not pending:
        return None
    w = pending[0]
    day = datetime.strptime(w["date"], "%Y-%m-%d").date()
    if day == today:
        when = "Hoy"
    elif day == today + timedelta(days=1):
        when = "Mañana"
    else:
        when = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"][day.weekday()] + f" {day.day}"
    txt = f"{w.get('phrase') or ''} {w.get('title') or ''}".lower().replace("_", " ")
    kind, color = next(((l, c) for r, l, c in TIPOS if re.search(r, txt)), ("", "#94A3B8"))
    return {
        "when": when,
        "is_today": day == today,
        "title": w.get("title") or "Entreno",
        "kind": kind,
        "color": color,
        "minutes": round(w["duration_sec"] / 60) if w.get("duration_sec") else 0,
        "distance_km": round(w["distance_m"] / 1000, 1) if w.get("distance_m") else 0,
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not authorized(self.headers):
            return deny(self)
        g = load("garmin") or {}
        s = load("strava") or {}
        m = load("metrics") or {}
        meta = load("meta") or {}
        plan = load("garmin_plan") or {}

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
            "workout": _next_workout(plan.get("workouts")),
        }

        body = json.dumps(payload, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
