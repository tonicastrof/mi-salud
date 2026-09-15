"""
Entrenador IA — conversa con Claude usando todos tus datos.

GET  /api/coach   → estado (¿está configurado?) + preguntas sugeridas
POST /api/coach   → {"messages": [{"role": "user", "content": "..."}],
                     "activity_id": 123 (opcional)}
                  ← {"reply": "...", "usage": {...}}

Variables de entorno:
  ANTHROPIC_API_KEY  (obligatoria)
  COACH_MODEL        (opcional, por defecto claude-sonnet-5;
                      pon claude-opus-5 si quieres análisis más finos)
  APP_SECRET         (opcional; si está, hay que mandar la cabecera
                      X-App-Secret con el mismo valor)
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import json
from http.server import BaseHTTPRequestHandler

from _lib.cache import load
from _lib.analytics import build_analytics
from _lib.coach_context import build_context

MODEL = os.getenv("COACH_MODEL", "claude-sonnet-5")
MAX_TOKENS = 3000
MAX_HISTORY = 20          # turnos de conversación que se reenvían
MAX_QUESTION = 2000       # caracteres por mensaje

SYSTEM = """Eres el entrenador personal de este atleta dentro de su app privada "Mi Salud".
Hablas español de España, tuteas y vas al grano como lo haría un buen entrenador por WhatsApp.

Tienes delante su dossier: datos de Garmin (sueño, HRV, FC en reposo, Body Battery, estrés),
sus actividades de Strava y métricas calculadas (CTL/ATL/TSB, ratio agudo:crónico, readiness,
predicciones de carrera). Úsalo siempre: cita cifras y fechas concretas de sus datos en vez de
dar consejos genéricos.

Cómo respondes:
- Directo y breve por defecto: 3-6 frases o una lista corta. Si te pide un plan o un análisis
  a fondo, entonces sí desarróllalo.
- Empieza por la respuesta, no por un resumen de lo que te ha preguntado.
- Apóyate en los números ("llevas 58 km esta semana frente a 41 de media") y explica qué implican.
- Cuando propongas entrenamientos, concreta: tipo de sesión, distancia o duración, ritmo o zona
  de FC, y qué día encaja mejor según su calendario y su carga.
- Si los datos no dan para responder (falta sincronizar, no hay FC en esa sesión, etc.), dilo
  claramente en una frase en vez de inventarte cifras. Nunca te inventes datos que no estén
  en el dossier.
- Markdown ligero: negritas y listas cortas. Sin encabezados grandes ni tablas enormes.

Límites: eres un entrenador, no un médico. Ante dolor persistente, mareos, dolor en el pecho,
arritmias o cualquier señal preocupante, recomiéndale ver a un profesional sanitario y no le
des diagnósticos."""

SUGGESTIONS = [
    "¿Cómo he entrenado esta semana?",
    "¿Qué toca mañana según mi fatiga?",
    "¿Voy bien para bajar de 45' en 10K?",
    "¿Estoy subiendo el volumen demasiado rápido?",
    "Analiza mi última carrera",
    "Móntame la semana que viene",
]


class handler(BaseHTTPRequestHandler):

    # ─── Estado ───

    def do_GET(self):
        self._r(200, {
            "enabled": bool(os.getenv("ANTHROPIC_API_KEY")),
            "model": MODEL,
            "protected": bool(os.getenv("APP_SECRET")),
            "suggestions": SUGGESTIONS,
        })

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    # ─── Conversación ───

    def do_POST(self):
        secret = os.getenv("APP_SECRET")
        if secret and self.headers.get("X-App-Secret") != secret:
            self._r(401, {"error": "No autorizado"})
            return

        if not os.getenv("ANTHROPIC_API_KEY"):
            self._r(503, {"error": "Falta ANTHROPIC_API_KEY. Añádela en las "
                                   "variables de entorno de Vercel."})
            return

        try:
            body = json.loads(self.rfile.read(
                int(self.headers.get("Content-Length") or 0)) or b"{}")
        except json.JSONDecodeError:
            self._r(400, {"error": "JSON inválido"})
            return

        messages = self._clean_messages(body.get("messages") or [])
        if not messages:
            self._r(400, {"error": "Falta el mensaje"})
            return

        try:
            context = self._build_dossier(body.get("activity_id"))
        except Exception as e:
            self._r(500, {"error": f"No se pudo leer tus datos: {e}"})
            return

        try:
            import anthropic
        except ImportError:
            self._r(503, {"error": "Falta el paquete 'anthropic' en requirements.txt"})
            return

        client = anthropic.Anthropic()
        system = [
            {"type": "text", "text": SYSTEM},
            # El dossier va al final del prefijo estable y se cachea: las
            # siguientes preguntas de la conversación lo reutilizan.
            {"type": "text", "text": context,
             "cache_control": {"type": "ephemeral"}},
        ]
        try:
            try:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    thinking={"type": "adaptive"},
                    output_config={"effort": "medium"},
                    system=system,
                    messages=messages,
                )
            except anthropic.BadRequestError:
                # Modelos antiguos (p. ej. si cambias COACH_MODEL a Haiku) no
                # aceptan thinking adaptativo ni effort: repetimos sin ellos.
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=system,
                    messages=messages,
                )
        except anthropic.AuthenticationError:
            self._r(401, {"error": "La ANTHROPIC_API_KEY no es válida"})
            return
        except anthropic.RateLimitError:
            self._r(429, {"error": "Límite de peticiones de la API alcanzado, "
                                   "prueba en un minuto"})
            return
        except anthropic.APIConnectionError:
            self._r(504, {"error": "No se pudo conectar con la API de Claude"})
            return
        except anthropic.APIStatusError as e:
            self._r(502, {"error": f"Error de la API de Claude: {e.message}"})
            return
        except Exception as e:
            self._r(500, {"error": str(e)})
            return

        if response.stop_reason == "refusal":
            self._r(200, {"reply": "No puedo responder a eso. Prueba a "
                                   "preguntarme sobre tu entrenamiento."})
            return

        reply = "\n\n".join(b.text for b in response.content
                            if b.type == "text" and b.text).strip()

        self._r(200, {
            "reply": reply or "No he podido generar respuesta, inténtalo otra vez.",
            "model": response.model,
            "usage": {
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
                "cache_read": getattr(response.usage, "cache_read_input_tokens", 0),
            },
        })

    # ─── Helpers ───

    def _clean_messages(self, raw):
        """Normaliza el historial que manda el navegador."""
        messages = []
        for m in raw[-MAX_HISTORY:]:
            role = m.get("role")
            content = (m.get("content") or "").strip()[:MAX_QUESTION]
            if role in ("user", "assistant") and content:
                # La API exige alternancia empezando por el usuario
                if not messages and role != "user":
                    continue
                messages.append({"role": role, "content": content})
        while messages and messages[-1]["role"] != "user":
            messages.pop()
        return messages

    def _build_dossier(self, activity_id):
        garmin = load("garmin") or {}
        strava = load("strava") or {}
        metrics = load("metrics") or {}
        activities = strava.get("activities", []) or []
        context = build_context(garmin, strava, metrics, build_analytics(activities))

        if activity_id:
            detail = self._activity_detail(activity_id, activities)
            if detail:
                context += "\n" + detail
        return context

    def _activity_detail(self, activity_id, activities):
        """Splits y zonas de una actividad concreta, si se está consultando una."""
        try:
            from _lib.strava_client import StravaClient
            base = next((a for a in activities
                         if str(a.get("id")) == str(activity_id)), None)
            s = StravaClient()
            if not s.connect():
                return ""
            d = s.get_activity_detail(int(activity_id))
            lines = [f"\n## Actividad que está mirando ahora mismo (id {activity_id})"]
            if base:
                lines.append(f'- {base.get("date")} · "{base.get("name")}" · '
                             f'{base.get("distance")} km · {base.get("time")} · '
                             f'{base.get("elevation")} m D+ · RE {base.get("effort")}')
            if d.get("laps"):
                lines.append("- Parciales por km: " + ", ".join(
                    f"km{l['km']} {l['pace']}" + (f" FC{l['hr']}" if l.get("hr") else "")
                    for l in d["laps"][:30]))
            if d.get("best_efforts"):
                lines.append("- Mejores esfuerzos: " + ", ".join(
                    f"{b['name']} {b['time']}" for b in d["best_efforts"]))
            for z in s.get_activity_zones(int(activity_id)):
                lines.append(f"- Tiempo en zonas ({z['type']}): " + ", ".join(
                    f"{b['zone']} {b['minutes']}min ({b['percent']}%)"
                    for b in z["buckets"]))
            return "\n".join(lines)
        except Exception:
            return ""

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-App-Secret")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _r(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False, default=str).encode())
