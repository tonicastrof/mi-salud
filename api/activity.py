import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from _lib.strava_client import StravaClient

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qid = parse_qs(urlparse(self.path).query).get("id", [None])[0]
        if not qid:
            self._r(400, {"error": "Falta parámetro id"})
            return
        try:
            s = StravaClient()
            if s.connect():
                self._r(200, s.get_activity_detail(int(qid)))
            else:
                self._r(503, {"error": "Strava no disponible"})
        except Exception as e:
            self._r(500, {"error": str(e)})

    def _r(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())
