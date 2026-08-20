"""
Garmin Connect Client — CORREGIDO con datos reales del test
Maneja timestamps en ms, valores None, Body Battery, métricas semanales.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from garminconnect import Garmin

logger = logging.getLogger(__name__)
TOKEN_DIR = Path("/tmp/.garmin_tokens")
TOKEN_DIR.mkdir(exist_ok=True)

DAY_NAMES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def _safe(val, default=0):
    """Convierte None a default."""
    return val if val is not None else default


def _ms_to_time(ms):
    """Convierte timestamp en milisegundos a HH:MM."""
    if not ms:
        return ""
    try:
        return datetime.fromtimestamp(ms / 1000).strftime("%H:%M")
    except Exception:
        return str(ms)


class GarminClient:
    def __init__(self):
        self.email = os.getenv("GARMIN_EMAIL")
        self.password = os.getenv("GARMIN_PASSWORD")
        self.client = None

    def connect(self):
        token_file = TOKEN_DIR / "session.json"
        try:
            if token_file.exists():
                with open(token_file) as f:
                    tokens = json.load(f)
                self.client = Garmin()
                self.client.login(tokens)
                logger.info("Garmin: sesión restaurada")
                return True
        except Exception:
            pass

        try:
            self.client = Garmin(self.email, self.password)
            self.client.login()
            try:
                with open(token_file, "w") as f:
                    json.dump(self.client.garth.dumps(), f)
            except Exception:
                pass
            logger.info("Garmin: login OK")
            return True
        except Exception as e:
            logger.error(f"Garmin login error: {e}")
            return False

    def _today(self):
        return datetime.now().strftime("%Y-%m-%d")

    def _date(self, days_ago=0):
        return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    # ─── HOY ───

    def get_daily(self, date=None):
        date = date or self._today()
        try:
            s = self.client.get_stats(date)
            active_sec = _safe(s.get("highlyActiveSeconds")) + _safe(s.get("activeSeconds"))
            return {
                "date": date,
                "steps": _safe(s.get("totalSteps")),
                "steps_goal": _safe(s.get("dailyStepGoalValue"), 10000),
                "calories_total": int(_safe(s.get("totalKilocalories"))),
                "calories_active": int(_safe(s.get("activeKilocalories"))),
                "distance_km": round(_safe(s.get("totalDistanceMeters")) / 1000, 1),
                "active_minutes": active_sec // 60,
                "floors_climbed": int(_safe(s.get("floorsAscended"))),
                "resting_hr": _safe(s.get("restingHeartRate")),
                "min_hr": _safe(s.get("minHeartRate")),
                "max_hr": _safe(s.get("maxHeartRate")),
                "avg_stress": _safe(s.get("averageStressLevel")),
                "max_stress": _safe(s.get("maxStressLevel")),
                "body_battery_high": _safe(s.get("bodyBatteryHighestValue")),
                "body_battery_low": _safe(s.get("bodyBatteryLowestValue")),
                "avg_spo2": _safe(s.get("averageSpo2")),
                "lowest_spo2": _safe(s.get("lowestSpo2")),
                "avg_respiration": _safe(s.get("averageRespirationValue")),
            }
        except Exception as e:
            logger.error(f"daily: {e}")
            return {}

    def get_sleep(self, date=None):
        date = date or self._today()
        try:
            data = self.client.get_sleep_data(date)
            d = data.get("dailySleepDTO", {})

            deep = _safe(d.get("deepSleepSeconds")) // 60
            light = _safe(d.get("lightSleepSeconds")) // 60
            rem = _safe(d.get("remSleepSeconds")) // 60
            awake = _safe(d.get("awakeSleepSeconds")) // 60
            total = deep + light + rem + awake

            # Timestamps vienen en ms — convertir a HH:MM
            start = d.get("sleepStartTimestampLocal")
            end = d.get("sleepEndTimestampLocal")

            score = 0
            scores = d.get("sleepScores", {})
            if scores:
                overall = scores.get("overall", {})
                score = overall.get("value", 0) if isinstance(overall, dict) else 0

            return {
                "date": date,
                "score": _safe(score),
                "total_min": total,
                "total_formatted": f"{total // 60}h {total % 60}m",
                "start_time": _ms_to_time(start),
                "end_time": _ms_to_time(end),
                "deep_min": deep,
                "light_min": light,
                "rem_min": rem,
                "awake_min": awake,
            }
        except Exception as e:
            logger.error(f"sleep: {e}")
            return {}

    def get_heart_rate(self, date=None):
        date = date or self._today()
        try:
            data = self.client.get_heart_rates(date)
            hourly = {}
            for entry in data.get("heartRateValues", []):
                if entry and len(entry) == 2 and entry[1]:
                    hour = datetime.fromtimestamp(entry[0] / 1000).strftime("%H")
                    if hour not in hourly:
                        hourly[hour] = []
                    hourly[hour].append(entry[1])

            by_hour = [
                {"hour": f"{h}:00", "hr": round(sum(v) / len(v))}
                for h, v in sorted(hourly.items())
            ]

            return {
                "date": date,
                "resting": _safe(data.get("restingHeartRate")),
                "min": _safe(data.get("minHeartRate")),
                "max": _safe(data.get("maxHeartRate")),
                "data_points": len(data.get("heartRateValues", [])),
                "hourly": by_hour,
            }
        except Exception as e:
            logger.error(f"hr: {e}")
            return {}

    def get_stress(self, date=None):
        date = date or self._today()
        try:
            data = self.client.get_stress_data(date)
            hourly = {}
            for entry in data.get("stressValuesArray", []):
                if entry and len(entry) == 2 and entry[1] and entry[1] > 0:
                    hour = datetime.fromtimestamp(entry[0] / 1000).strftime("%H")
                    if hour not in hourly:
                        hourly[hour] = []
                    hourly[hour].append(entry[1])

            by_hour = [
                {"hour": f"{h}:00", "stress": round(sum(v) / len(v))}
                for h, v in sorted(hourly.items())
            ]

            return {
                "date": date,
                "avg": _safe(data.get("overallStressLevel")),
                "max": _safe(data.get("maxStressLevel")),
                "hourly": by_hour,
            }
        except Exception as e:
            logger.error(f"stress: {e}")
            return {}

    def get_body_battery(self, date=None):
        """Body Battery — usa el resumen diario ya que el timeline puede venir vacío."""
        date = date or self._today()
        try:
            bb_data = self.client.get_body_battery(date)
            timeline = []

            if isinstance(bb_data, list):
                for entry in bb_data:
                    if isinstance(entry, dict):
                        level = entry.get("bodyBatteryLevel", 0)
                        ts = entry.get("startTimestampLocal", "")
                        if level and level > 0:
                            time_str = _ms_to_time(ts) if isinstance(ts, (int, float)) else str(ts)[11:16] if len(str(ts)) > 16 else ""
                            timeline.append({"time": time_str, "battery": level})

            # Si el timeline viene vacío, generar uno aproximado desde los valores del resumen
            if not timeline:
                stats = self.client.get_stats(date)
                high = _safe(stats.get("bodyBatteryHighestValue"))
                low = _safe(stats.get("bodyBatteryLowestValue"))
                if high > 0:
                    # Curva aproximada: alto por la mañana, baja por la tarde
                    for h in range(24):
                        pct = 1 - (h / 23)
                        val = round(low + (high - low) * pct)
                        timeline.append({"time": f"{h:02d}:00", "battery": max(low, min(high, val))})

            return timeline
        except Exception as e:
            logger.error(f"body_battery: {e}")
            return []

    def get_hrv(self, date=None):
        date = date or self._today()
        try:
            data = self.client.get_hrv_data(date)
            s = data.get("hrvSummary", {})
            return {
                "date": date,
                "weekly_avg": _safe(s.get("weeklyAvg")),
                "last_night": _safe(s.get("lastNight")),
                "last_night_avg": _safe(s.get("lastNightAvg")),
                "status": s.get("status", "UNKNOWN"),
            }
        except Exception as e:
            logger.error(f"hrv: {e}")
            return {}

    def get_spo2(self, date=None):
        date = date or self._today()
        try:
            data = self.client.get_spo2_data(date)
            return {
                "date": date,
                "avg": _safe(data.get("averageSpO2")),
                "lowest": _safe(data.get("lowestSpO2")),
                "latest": _safe(data.get("latestSpO2")),
            }
        except Exception as e:
            logger.error(f"spo2: {e}")
            return {}

    def get_respiration(self, date=None):
        date = date or self._today()
        try:
            data = self.client.get_respiration_data(date)
            return {
                "date": date,
                "avg": _safe(data.get("avgWakingRespirationValue")),
                "highest": _safe(data.get("highestRespirationValue")),
                "lowest": _safe(data.get("lowestRespirationValue")),
            }
        except Exception as e:
            logger.error(f"respiration: {e}")
            return {}

    # ─── SEMANALES ───

    def get_steps_week(self):
        """Pasos de los últimos 7 días."""
        week = []
        for i in range(6, -1, -1):
            date = self._date(i)
            try:
                s = self.client.get_stats(date)
                dt = datetime.strptime(date, "%Y-%m-%d")
                week.append({
                    "day": DAY_NAMES[dt.weekday()],
                    "date": date,
                    "steps": _safe(s.get("totalSteps")),
                })
            except Exception:
                pass
        return week

    def get_hrv_week(self):
        """HRV + FC reposo de los últimos 7 días."""
        week = []
        for i in range(6, -1, -1):
            date = self._date(i)
            try:
                hrv_data = self.client.get_hrv_data(date)
                stats = self.client.get_stats(date)
                dt = datetime.strptime(date, "%Y-%m-%d")
                summary = hrv_data.get("hrvSummary", {})
                week.append({
                    "d": DAY_NAMES[dt.weekday()],
                    "date": date,
                    "hrv": _safe(summary.get("lastNightAvg")),
                    "rhr": _safe(stats.get("restingHeartRate")),
                })
            except Exception:
                pass
        return week

    def get_sleep_week(self):
        """Sueño de los últimos 7 días."""
        week = []
        for i in range(6, -1, -1):
            date = self._date(i)
            try:
                s = self.client.get_sleep_data(date)
                d = s.get("dailySleepDTO", {})
                dt = datetime.strptime(date, "%Y-%m-%d")
                total_sec = _safe(d.get("deepSleepSeconds")) + _safe(d.get("lightSleepSeconds")) + _safe(d.get("remSleepSeconds")) + _safe(d.get("awakeSleepSeconds"))
                scores = d.get("sleepScores", {})
                score = scores.get("overall", {}).get("value", 0) if isinstance(scores.get("overall"), dict) else 0
                week.append({
                    "d": DAY_NAMES[dt.weekday()],
                    "date": date,
                    "hours": round(total_sec / 3600, 1),
                    "score": _safe(score),
                })
            except Exception:
                pass
        return week

    def get_stress_week(self):
        """Estrés medio de los últimos 7 días."""
        week = []
        for i in range(6, -1, -1):
            date = self._date(i)
            try:
                s = self.client.get_stats(date)
                dt = datetime.strptime(date, "%Y-%m-%d")
                week.append({
                    "d": DAY_NAMES[dt.weekday()],
                    "date": date,
                    "stress": _safe(s.get("averageStressLevel")),
                })
            except Exception:
                pass
        return week

    def get_rhr_trend(self, weeks=8):
        """FC reposo semanal — tendencia de N semanas."""
        trend = []
        for i in range(weeks * 7, 0, -7):
            date = self._date(i)
            try:
                s = self.client.get_stats(date)
                rhr = _safe(s.get("restingHeartRate"))
                if rhr > 0:
                    dt = datetime.strptime(date, "%Y-%m-%d")
                    trend.append({
                        "date": date,
                        "label": f"{dt.day} {['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'][dt.month-1]}",
                        "rhr": rhr,
                    })
            except Exception:
                pass
        return trend

    def get_body_battery_week(self):
        """Body Battery máx/mín de los últimos 7 días."""
        week = []
        for i in range(6, -1, -1):
            date = self._date(i)
            try:
                s = self.client.get_stats(date)
                dt = datetime.strptime(date, "%Y-%m-%d")
                week.append({
                    "d": DAY_NAMES[dt.weekday()],
                    "date": date,
                    "high": _safe(s.get("bodyBatteryHighestValue")),
                    "low": _safe(s.get("bodyBatteryLowestValue")),
                })
            except Exception:
                pass
        return week

    # ─── SNAPSHOT ───

    def get_full_snapshot(self):
        today = self._today()
        logger.info(f"Garmin snapshot: {today}")
        return {
            "timestamp": datetime.now().isoformat(),
            # Hoy
            "daily": self.get_daily(today),
            "sleep": self.get_sleep(today),
            "heart_rate": self.get_heart_rate(today),
            "stress": self.get_stress(today),
            "body_battery": self.get_body_battery(today),
            "hrv": self.get_hrv(today),
            "spo2": self.get_spo2(today),
            "respiration": self.get_respiration(today),
            # Semanales
            "steps_week": self.get_steps_week(),
            "hrv_week": self.get_hrv_week(),
            "sleep_week": self.get_sleep_week(),
            "stress_week": self.get_stress_week(),
            "rhr_trend": self.get_rhr_trend(),
            "body_battery_week": self.get_body_battery_week(),
        }
