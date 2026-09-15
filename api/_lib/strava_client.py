"""
Strava API Client
Extrae actividades, rutas, zonas y material deportivo.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

TOKEN_FILE = Path("/tmp/.strava_tokens.json")
API_BASE = "https://www.strava.com/api/v3"


class StravaClient:
    def __init__(self):
        self.client_id = os.getenv("STRAVA_CLIENT_ID")
        self.client_secret = os.getenv("STRAVA_CLIENT_SECRET")
        self.refresh_token = os.getenv("STRAVA_REFRESH_TOKEN")
        self.access_token = None
        self.token_expires = 0

    # ─── AUTH ───

    def _refresh_access_token(self):
        """Renueva el access token usando el refresh token."""
        # Intentar cargar token guardado
        if TOKEN_FILE.exists():
            with open(TOKEN_FILE) as f:
                saved = json.load(f)
            if saved.get("expires_at", 0) > datetime.now().timestamp() + 60:
                self.access_token = saved["access_token"]
                self.token_expires = saved["expires_at"]
                self.refresh_token = saved.get("refresh_token", self.refresh_token)
                logger.info("Strava: token restaurado desde archivo")
                return True

        try:
            resp = requests.post("https://www.strava.com/oauth/token", data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            data = resp.json()

            self.access_token = data["access_token"]
            self.refresh_token = data["refresh_token"]
            self.token_expires = data["expires_at"]

            # Guardar para la próxima vez
            with open(TOKEN_FILE, "w") as f:
                json.dump(data, f)

            logger.info("Strava: token renovado")
            return True

        except Exception as e:
            logger.error(f"Strava: error renovando token — {e}")
            return False

    def connect(self) -> bool:
        """Conecta con Strava API."""
        return self._refresh_access_token()

    def _headers(self):
        if self.token_expires < datetime.now().timestamp() + 60:
            self._refresh_access_token()
        return {"Authorization": f"Bearer {self.access_token}"}

    def _get(self, endpoint: str, params: dict = None) -> dict | list:
        try:
            resp = requests.get(
                f"{API_BASE}/{endpoint}",
                headers=self._headers(),
                params=params or {},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Strava GET {endpoint}: {e}")
            return {}

    # ─── PERFIL ───

    def get_profile(self) -> dict:
        data = self._get("athlete")
        return {
            "id": data.get("id"),
            "name": f"{data.get('firstname', '')} {data.get('lastname', '')}".strip(),
            "weight": data.get("weight"),
            "ftp": data.get("ftp"),
            "city": data.get("city"),
            "country": data.get("country"),
            "measurement": data.get("measurement_preference", "metric"),
        }

    # ─── ACTIVIDADES ───

    def get_activities(self, count: int = 200, after: datetime = None) -> list:
        """
        Lista de actividades recientes. Pagina automáticamente hasta `count`
        (Strava devuelve como máximo 200 por página).
        """
        raw = []
        page = 1
        while len(raw) < count:
            params = {"per_page": min(200, count - len(raw)), "page": page}
            if after:
                params["after"] = int(after.timestamp())
            chunk = self._get("athlete/activities", params)
            if not isinstance(chunk, list) or not chunk:
                break
            raw.extend(chunk)
            if len(chunk) < params["per_page"]:
                break
            page += 1

        if not raw:
            return []

        activities = []
        for a in raw:
            sport = a.get("type", "")
            distance_km = round(a.get("distance", 0) / 1000, 1)
            moving_sec = a.get("moving_time", 0)
            elapsed_sec = a.get("elapsed_time", 0)

            # Formatear tiempo
            hours = moving_sec // 3600
            mins = (moving_sec % 3600) // 60
            secs = moving_sec % 60
            time_fmt = (
                f"{hours}:{mins:02d}:{secs:02d}" if hours
                else f"{mins}:{secs:02d}"
            )

            # Ritmo (correr/senderismo) o velocidad (bici)
            pace = None
            avg_speed = None
            if sport in ("Run", "Trail Run", "Hike", "Walk") and distance_km > 0:
                pace_sec = moving_sec / distance_km
                pace = f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}"
            elif distance_km > 0:
                avg_speed = f"{round(distance_km / (moving_sec / 3600), 1)} km/h"

            # Mapear tipo a categoría simple
            sport_cat = "Run"
            if sport in ("Ride", "VirtualRide", "EBikeRide", "MountainBikeRide"):
                sport_cat = "Ride"
            elif sport in ("Hike", "Walk", "RockClimbing"):
                sport_cat = "Hike"
            elif sport in ("Run", "Trail Run", "VirtualRun"):
                sport_cat = "Run"

            start_local = a.get("start_date_local", "") or ""
            try:
                hour = int(start_local[11:13]) if len(start_local) >= 13 else None
            except ValueError:
                hour = None

            activities.append({
                "id": a.get("id"),
                "name": a.get("name", ""),
                "sport": sport_cat,
                "sport_type": sport,
                "date": start_local[:10],
                "date_formatted": self._format_date(start_local),
                "start_time": start_local[11:16],
                "hour": hour,
                "weekday": self._weekday(start_local),
                "distance": distance_km,
                "time": time_fmt,
                "moving_time_sec": moving_sec,
                "elapsed_time_sec": elapsed_sec,
                "elevation": round(a.get("total_elevation_gain", 0)),
                "calories": round(a.get("calories", 0) or a.get("kilojoules", 0) * 0.239 or 0),
                "effort": a.get("suffer_score", 0) or 0,
                "pace": pace,
                "avg_speed": avg_speed,
                "avg_hr": a.get("average_heartrate"),
                "max_hr": a.get("max_heartrate"),
                "avg_watts": a.get("average_watts"),
                "max_watts": a.get("max_watts"),
                "weighted_watts": a.get("weighted_average_watts"),
                "avg_cadence": a.get("average_cadence"),
                "kudos": a.get("kudos_count", 0),
                "pr_count": a.get("pr_count", 0),
                "achievements": a.get("achievement_count", 0),
                "is_race": bool(a.get("workout_type") in (1, 11)),
                "trainer": bool(a.get("trainer")),
                "commute": bool(a.get("commute")),
                "gear_id": a.get("gear_id"),
                "pace_sec": round(moving_sec / distance_km) if distance_km > 0 else None,
                "speed_kmh": round(distance_km / (moving_sec / 3600), 1) if moving_sec > 0 and distance_km > 0 else None,
                "polyline": (a.get("map") or {}).get("summary_polyline", ""),
                "icon": "🏃" if sport_cat == "Run" else "🚴" if sport_cat == "Ride" else "⛰️",
            })

        return activities

    def _weekday(self, iso_date: str):
        """Día de la semana (0 = lunes) o None."""
        try:
            return datetime.fromisoformat(iso_date.replace("Z", "+00:00")).weekday()
        except (ValueError, AttributeError):
            return None

    def _format_date(self, iso_date: str) -> str:
        if not iso_date:
            return ""
        try:
            dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
            meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                     "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
            return f"{dt.day} {meses[dt.month - 1]}"
        except Exception:
            return iso_date[:10]

    # ─── DETALLE DE ACTIVIDAD ───

    def get_activity_detail(self, activity_id: int) -> dict:
        """Detalle con splits, mejores esfuerzos, etc."""
        data = self._get(f"activities/{activity_id}")
        if not data:
            return {}

        # Splits por km
        laps = []
        for lap in data.get("splits_metric", []):
            pace_sec = lap.get("moving_time", 0) / max(lap.get("distance", 1) / 1000, 0.01)
            laps.append({
                "km": lap.get("split", 0),
                "pace": f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}",
                "hr": round(lap.get("average_heartrate", 0) or 0),
                "elev": round(lap.get("elevation_difference", 0) or 0),
            })

        # Mejores esfuerzos
        best_efforts = []
        for be in data.get("best_efforts", []):
            time_sec = be.get("moving_time", 0)
            hrs = time_sec // 3600
            mins = (time_sec % 3600) // 60
            secs = time_sec % 60
            time_fmt = (
                f"{hrs}:{mins:02d}:{secs:02d}" if hrs
                else f"{mins}:{secs:02d}"
            )
            best_efforts.append({
                "name": be.get("name", ""),
                "distance": be.get("distance", 0),
                "time": time_fmt,
            })

        return {
            "id": activity_id,
            "laps": laps,
            "best_efforts": best_efforts,
            "description": data.get("description", ""),
            "device": data.get("device_name", ""),
            "gear": data.get("gear", {}).get("name", "") if data.get("gear") else "",
            "avg_cadence": data.get("average_cadence"),
            "max_speed_kmh": round((data.get("max_speed") or 0) * 3.6, 1),
            "calories": round(data.get("calories") or 0),
            "avg_temp": data.get("average_temp"),
            "has_heartrate": bool(data.get("has_heartrate")),
        }

    # ─── STREAMS (series temporales de una actividad) ───

    STREAM_KEYS = ["time", "heartrate", "altitude", "velocity_smooth",
                   "cadence", "watts", "distance"]

    def get_activity_streams(self, activity_id: int, points: int = 120) -> dict:
        """
        Series temporales de una actividad, remuestreadas a ~`points` puntos
        para que pesen poco y se puedan pintar directamente.
        """
        raw = self._get(
            f"activities/{activity_id}/streams",
            {"keys": ",".join(self.STREAM_KEYS), "key_by_type": "true"},
        )
        if not isinstance(raw, dict) or not raw:
            return {"points": [], "available": []}

        series = {k: (v or {}).get("data") or [] for k, v in raw.items()
                  if isinstance(v, dict)}
        length = max((len(v) for v in series.values()), default=0)
        if length == 0:
            return {"points": [], "available": []}

        step = max(1, length // points)
        idxs = list(range(0, length, step))

        def at(key, i, default=None):
            data = series.get(key) or []
            return data[i] if i < len(data) else default

        out = []
        for i in idxs:
            secs = at("time", i, i) or 0
            dist_m = at("distance", i, 0) or 0
            speed = at("velocity_smooth", i)  # m/s
            point = {
                "t": round(secs),
                "t_label": f"{int(secs) // 60}:{int(secs) % 60:02d}",
                "km": round(dist_m / 1000, 2),
                "hr": round(at("heartrate", i) or 0) or None,
                "alt": round(at("altitude", i) or 0) or None,
                "cad": round(at("cadence", i) or 0) or None,
                "watts": round(at("watts", i) or 0) or None,
            }
            if speed:
                point["speed"] = round(speed * 3.6, 1)
                pace_sec = 1000 / speed
                # Ignorar paradas y ritmos absurdos (> 15 min/km)
                point["pace_sec"] = round(pace_sec) if pace_sec < 900 else None
            out.append(point)

        available = [k for k in ("heartrate", "altitude", "velocity_smooth",
                                 "cadence", "watts") if series.get(k)]
        return {"points": out, "available": available}

    def get_activity_zones(self, activity_id: int) -> list:
        """Tiempo en cada zona de FC/potencia de una actividad."""
        raw = self._get(f"activities/{activity_id}/zones")
        if not isinstance(raw, list):
            return []

        zones = []
        for z in raw:
            buckets = z.get("distribution_buckets") or []
            total = sum(b.get("time", 0) for b in buckets) or 1
            zones.append({
                "type": z.get("type"),
                "buckets": [{
                    "zone": f"Z{i + 1}",
                    "min": b.get("min"),
                    "max": b.get("max"),
                    "seconds": b.get("time", 0),
                    "minutes": round(b.get("time", 0) / 60),
                    "percent": round(b.get("time", 0) * 100 / total),
                } for i, b in enumerate(buckets)],
            })
        return zones

    # ─── ZONAS ───

    def get_zones(self) -> dict:
        """Zonas de FC y potencia."""
        data = self._get("athlete/zones")
        if not isinstance(data, list):
            return {}

        zones = {}
        for zone_set in data:
            dist_type = zone_set.get("distribution_type")
            buckets = zone_set.get("zones", [])
            zones[dist_type] = [
                {"min": z.get("min", 0), "max": z.get("max", 0)}
                for z in buckets
            ]
        return zones

    # ─── MATERIAL ───

    def get_gear(self) -> list:
        """Bicicletas y zapatillas."""
        profile = self._get("athlete")
        gear = []

        for bike in profile.get("bikes", []):
            gear.append({
                "id": bike.get("id"),
                "name": bike.get("name"),
                "type": "Bike",
                "distance_km": round(bike.get("distance", 0) / 1000),
            })

        for shoe in profile.get("shoes", []):
            gear.append({
                "id": shoe.get("id"),
                "name": shoe.get("name"),
                "type": "Shoe",
                "distance_km": round(shoe.get("distance", 0) / 1000),
            })

        return gear

    # ─── SNAPSHOT COMPLETO ───

    def get_full_snapshot(self) -> dict:
        """Recoge todo de Strava."""
        logger.info("Strava: recogiendo snapshot")

        activities = self.get_activities(count=200)
        profile = self.get_profile()

        return {
            "timestamp": datetime.now().isoformat(),
            "profile": profile,
            "activities": activities,
            "gear": self.get_gear(),
            "zones": self.get_zones(),
        }
