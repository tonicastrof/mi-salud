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

    def get_activities(self, count: int = 30, after: datetime = None) -> list:
        """Lista de actividades recientes."""
        params = {"per_page": count}
        if after:
            params["after"] = int(after.timestamp())

        raw = self._get("athlete/activities", params)
        if not isinstance(raw, list):
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

            activities.append({
                "id": a.get("id"),
                "name": a.get("name", ""),
                "sport": sport_cat,
                "sport_type": sport,
                "date": a.get("start_date_local", "")[:10],
                "date_formatted": self._format_date(a.get("start_date_local", "")),
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
                "polyline": (a.get("map") or {}).get("summary_polyline", ""),
                "icon": "🏃" if sport_cat == "Run" else "🚴" if sport_cat == "Ride" else "⛰️",
            })

        return activities

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
        }

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

        activities = self.get_activities(count=30)
        profile = self.get_profile()

        return {
            "timestamp": datetime.now().isoformat(),
            "profile": profile,
            "activities": activities,
            "gear": self.get_gear(),
            "zones": self.get_zones(),
        }
