"""GET /api/history?days=90 — el archivo diario.

Lo que hay aquí no se puede reconstruir: son las fichas que se fueron guardando
cada día, y van más atrás de las ventanas móviles que devuelven Garmin y Strava
(7 días de sueño/HRV/estrés, 8 semanas de FC en reposo). Cuanto más tiempo lleve
el cron corriendo, más largo es.

`?field=` devuelve solo una serie, aplanada, para pintarla sin bajarse todo:

    /api/history?days=180&field=readiness.score
    /api/history?days=90&field=daily.resting_hr
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from _lib.cache import load
from _lib.archive import read_days, INDEX_KEY
from _lib.auth import authorized, deny


def _dig(record, path):
    cur = record
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not authorized(self.headers):
            return deny(self)
        q = parse_qs(urlparse(self.path).query)
        try:
            days = max(1, min(1000, int(q.get("days", ["90"])[0])))
        except ValueError:
            days = 90
        field = (q.get("field", [None])[0] or "").strip()
        end = (q.get("end", [None])[0] or "").strip() or None

        try:
            index = load(INDEX_KEY) or []
            records = read_days(days=days, end=end)
        except Exception as e:
            self._r(500, {"error": str(e)})
            return

        payload = {
            "days": len(records),
            "total_archived": len(index),
            "first": index[0] if index else None,
            "last": index[-1] if index else None,
        }
        if field:
            payload["field"] = field
            payload["series"] = [
                {"date": r.get("date"), "value": _dig(r, field)}
                for r in records if _dig(r, field) is not None
            ]
        else:
            payload["records"] = records

        self._r(200, payload)

    def _r(self, code, payload):
        body = json.dumps(payload, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
