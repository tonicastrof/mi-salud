"""GET /api/sync-all — Garmin + Strava + cálculo en una sola llamada.

Existe para el cron: Vercel llama a una URL, no puede encadenar tres. El botón
Sync de la app sigue llamando a los tres endpoints por separado porque así
enseña el progreso paso a paso y cada petición tiene su propio presupuesto de
tiempo.

Cada paso guarda en Redis en cuanto termina, así que un timeout a mitad deja
los pasos anteriores hechos en vez de perderlo todo. Por eso también devuelve
el detalle por paso: un 200 aquí no significa que los tres fueran bien.

Si `CRON_SECRET` está definida, exige `Authorization: Bearer <secreto>` — que
es justo la cabecera que manda Vercel Cron. Sin ella el endpoint es público y
cualquiera puede disparar un login de Garmin y la descarga de 200 actividades.

`?steps=garmin,strava` limita qué pasos corren (garmin, plan, strava,
calculate). Todos juntos caben de sobra en los 60s del plan Hobby, pero si
algún día no cupieran se puede partir en varios crons (`?steps=garmin,plan` y
luego `?steps=strava,calculate`) sin tocar código.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from _lib.cache import save, load
from _lib.garmin_client import GarminClient
from _lib.strava_client import StravaClient
from _lib.metrics import calculate_all
from _lib.archive import archive_day


def _authorized(headers):
    secret = os.environ.get("CRON_SECRET")
    if not secret:
        return True
    auth = headers.get("Authorization") or ""
    if auth.startswith("Bearer ") and auth[7:] == secret:
        return True
    return headers.get("X-App-Secret") == secret


_garmin = None


def _garmin_client():
    # Una sola sesión para los pasos de Garmin: Garmin castiga los logins seguidos.
    global _garmin
    if _garmin is None:
        g = GarminClient()
        if not g.connect():
            raise RuntimeError("No se pudo conectar con Garmin")
        _garmin = g
    return _garmin


def _sync_garmin(meta):
    g = _garmin_client()
    data = g.get_full_snapshot()
    data["synced_at"] = datetime.now().isoformat()
    save("garmin", data)
    meta["garmin_synced"] = data["synced_at"]
    return {"steps": (data.get("daily") or {}).get("steps", 0),
            "sleep_score": (data.get("sleep") or {}).get("score", 0)}


def _sync_strava(meta):
    s = StravaClient()
    if not s.connect():
        raise RuntimeError("No se pudo conectar con Strava")
    data = s.get_full_snapshot()
    data["synced_at"] = datetime.now().isoformat()
    save("strava", data)
    meta["strava_synced"] = data["synced_at"]
    return {"activities": len(data.get("activities", []))}


def _sync_plan(meta):
    # Paso propio: si el calendario falla, sueño/HRV ya están guardados.
    g = _garmin_client()
    data = {"workouts": g.get_scheduled_workouts(),
            "synced_at": datetime.now().isoformat()}
    save("garmin_plan", data)
    meta["plan_synced"] = data["synced_at"]
    return {"workouts": len(data["workouts"])}


def _calculate(meta):
    garmin = load("garmin") or {}
    strava = load("strava") or {}
    if not garmin and not strava:
        raise RuntimeError("No hay datos que calcular")
    metrics = calculate_all(garmin, strava)
    metrics["calculated_at"] = datetime.now().isoformat()
    save("metrics", metrics)
    meta["metrics_calculated"] = metrics["calculated_at"]

    archived = []
    try:
        archived = archive_day(garmin, metrics)
        if archived:
            meta["last_archived"] = archived[-1]
        meta.pop("archive_error", None)
    except Exception as e:
        meta["archive_error"] = str(e)

    return {"readiness": (metrics.get("readiness") or {}).get("score"),
            "tsb": ((metrics.get("fitness") or {}).get("current") or {}).get("tsb"),
            "archived_days": archived}


STEPS = (("garmin", _sync_garmin), ("plan", _sync_plan), ("strava", _sync_strava),
         ("calculate", _calculate))


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _garmin
        _garmin = None  # nada de arrastrar la sesión de una ejecución anterior
        if not _authorized(self.headers):
            self._r(401, {"error": "No autorizado"})
            return

        wanted = (parse_qs(urlparse(self.path).query).get("steps", [""])[0] or "").strip()
        only = {p.strip() for p in wanted.split(",") if p.strip()} if wanted else None
        if only and not only <= {name for name, _ in STEPS}:
            self._r(400, {"error": "steps admite: garmin, plan, strava, calculate"})
            return
        steps = [(n, f) for n, f in STEPS if not only or n in only]

        started = datetime.now()
        meta = load("meta") or {}
        results, failed = {}, []

        for name, fn in steps:
            try:
                results[name] = {"ok": True, **(fn(meta) or {})}
            except Exception as e:
                results[name] = {"ok": False, "error": str(e)}
                failed.append(name)

        meta["last_sync_all"] = started.isoformat()
        meta["last_sync_all_failed"] = failed
        save("meta", meta)

        payload = {
            "status": "ok" if not failed else ("partial" if len(failed) < len(steps) else "error"),
            "started_at": started.isoformat(),
            "seconds": round((datetime.now() - started).total_seconds(), 1),
            "failed": failed,
            "steps": results,
        }
        # Un fallo parcial sigue siendo 200: hay datos nuevos en Redis y no
        # quiero que el cron lo cuente como caída. Solo si no se salvó nada.
        self._r(200 if len(failed) < len(steps) else 503, payload)

    def _r(self, code, payload):
        body = json.dumps(payload, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
