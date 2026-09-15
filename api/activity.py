"""
GET /api/activity?id=123            → detalle (splits, mejores esfuerzos)
GET /api/activity?id=123&full=1     → detalle + series temporales + zonas
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from _lib.strava_client import StravaClient

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        qid = q.get("id", [None])[0]
        full = q.get("full", ["0"])[0] not in ("0", "", "false")
        if not qid:
            self._r(400, {"error": "Falta parámetro id"})
            return
        try:
            s = StravaClient()
            if not s.connect():
                self._r(503, {"error": "Strava no disponible"})
                return
            aid = int(qid)
            result = s.get_activity_detail(aid)
            if full:
                result["streams"] = s.get_activity_streams(aid)
                result["zones"] = s.get_activity_zones(aid)
            self._r(200, result)
        except Exception as e:
            self._r(500, {"error": str(e)})

    def _r(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())
