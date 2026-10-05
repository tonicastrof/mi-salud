"""Acceso a la API: solo tú.

Antes cualquiera con la URL veía tu sueño, tu HRV y tus rutas GPS, y podía
lanzar logins de Garmin en bucle. Ahora cada endpoint con datos exige una de
estas credenciales:

- La cookie `ms_auth`, que pone /api/login cuando escribes la contraseña en la
  app. La contraseña es APP_SECRET si existe en Vercel o, si no, la misma de
  Garmin (GARMIN_PASSWORD), así no hace falta tocar Vercel para activarlo.
- La cabecera `X-App-Token` con ese mismo valor (la usa el widget de Android).
- La cabecera `X-App-Secret` con APP_SECRET (compatibilidad con lo de antes).
- `Authorization: Bearer <CRON_SECRET>` (el cron de Vercel).

La cookie no contiene la contraseña: es un HMAC derivado de ella. Si cambias
la contraseña, las sesiones viejas dejan de valer.
"""
import hashlib
import hmac
import json
import os
from http.cookies import SimpleCookie

COOKIE = "ms_auth"
MAX_AGE = 10 * 365 * 24 * 3600   # la app es solo tuya: no hace falta caducar


def _password():
    return os.getenv("APP_SECRET") or os.getenv("GARMIN_PASSWORD") or ""


def token():
    pw = _password()
    if not pw:
        return ""
    return hmac.new(pw.encode(), b"mi-salud:sesion:v1", hashlib.sha256).hexdigest()


def check_password(candidate):
    pw = _password()
    return bool(pw) and hmac.compare_digest((candidate or "").encode(), pw.encode())


def _eq(a, b):
    return bool(a) and bool(b) and hmac.compare_digest(a.encode(), b.encode())


def authorized(headers):
    expected = token()
    if not expected:
        # Sin ninguna contraseña configurada no hay con qué comparar
        return True
    cookie = SimpleCookie()
    try:
        cookie.load(headers.get("Cookie") or "")
    except Exception:
        pass
    if COOKIE in cookie and _eq(cookie[COOKIE].value, expected):
        return True
    if _eq(headers.get("X-App-Token"), expected):
        return True
    if _eq(headers.get("X-App-Secret"), os.getenv("APP_SECRET")):
        return True
    auth = headers.get("Authorization") or ""
    if auth.startswith("Bearer ") and _eq(auth[7:], os.getenv("CRON_SECRET")):
        return True
    return False


def cookie_header(value, max_age=MAX_AGE):
    return (f"{COOKIE}={value}; Path=/; Max-Age={max_age}; HttpOnly; Secure; "
            "SameSite=Lax")


def deny(handler):
    body = json.dumps({"error": "No autorizado", "login": True}).encode()
    handler.send_response(401)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
