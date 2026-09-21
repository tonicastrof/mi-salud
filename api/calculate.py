import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from _lib.cache import save, load
from _lib.metrics import calculate_all
from _lib.archive import archive_day

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            garmin = load("garmin") or {}
            strava = load("strava") or {}
            if not garmin and not strava:
                self._r(404, {"error": "No hay datos. Pulsa Sync primero."})
                return
            metrics = calculate_all(garmin, strava)
            metrics["calculated_at"] = datetime.now().isoformat()
            save("metrics", metrics)
            meta = load("meta") or {}
            meta["metrics_calculated"] = metrics["calculated_at"]

            # Archivar el día. Aquí y no en sync-garmin porque es el único punto
            # donde garmin y metrics están frescos a la vez, así que la ficha del
            # día se guarda con su readiness y su CTL/ATL/TSB. Si falla, el
            # cálculo no se cae: el archivo es un extra, no la respuesta.
            archived = []
            try:
                archived = archive_day(garmin, metrics)
                if archived:
                    meta["last_archived"] = archived[-1]
                meta.pop("archive_error", None)
            except Exception as e:
                meta["archive_error"] = str(e)

            save("meta", meta)
            self._r(200, {"status": "ok", "calculated_at": metrics["calculated_at"],
                          "readiness": metrics.get("readiness", {}).get("score"),
                          "tsb": metrics.get("fitness", {}).get("current", {}).get("tsb"),
                          "archived_days": archived})
        except Exception as e:
            self._r(500, {"error": str(e)})

    def _r(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
