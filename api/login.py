"""
POST /api/login   {"password": "..."}  → pone la cookie de sesión
GET  /api/login                        → {"authed": true/false}
DELETE /api/login                      → cierra la sesión

La contraseña es APP_SECRET o, si no está definida, la de Garmin. Tras 10
fallos se bloquea 15 minutos, para que no se pueda probar a lo bruto.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import json
from http.server import BaseHTTPRequestHandler
from _lib.auth import authorized, check_password, token, cookie_header
from _lib.cache import incr, delete

FAILS_KEY = "auth_fails"
MAX_FAILS = 10
WINDOW = 15 * 60


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._r(200, {"authed": authorized(self.headers)})

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(
                int(self.headers.get("Content-Length") or 0)) or b"{}")
        except json.JSONDecodeError:
            self._r(400, {"error": "JSON inválido"})
            return

        try:
            fails = incr(FAILS_KEY, WINDOW)
        except Exception:
            fails = 0
        if fails > MAX_FAILS:
            self._r(429, {"error": "Demasiados intentos. Espera 15 minutos."})
            return

        if not check_password(body.get("password")):
            self._r(401, {"error": "Contraseña incorrecta"})
            return

        try:
            delete(FAILS_KEY)
        except Exception:
            pass
        t = token()
        self._r(200, {"ok": True, "token": t}, cookie=cookie_header(t))

    def do_DELETE(self):
        self._r(200, {"ok": True}, cookie=cookie_header("", max_age=0))

    def _r(self, code, payload, cookie=None):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
