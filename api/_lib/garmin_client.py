"""
Garmin Connect Client — CORREGIDO con datos reales del test
Maneja timestamps en ms, valores None, Body Battery, métricas semanales.
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from garminconnect import Garmin
from .tz import ahora, MADRID
from .cache import load, save

logger = logging.getLogger(__name__)

DAY_NAMES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def _safe(val, default=0):
    """Convierte None a default."""
    return val if val is not None else default


def _ms_to_time(ms):
    """Convierte timestamp en milisegundos a HH:MM."""
    if not ms:
        return ""
    try:
        # Los *TimestampLocal ya vienen en hora local: se leen tal cual, sin zona
        return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%H:%M")
    except Exception:
        return str(ms)


TOKENS_KEY = "garmin_tokens"
TOKEN_DIR = Path("/tmp/.garmin_tokens")
TOKEN_FILE = TOKEN_DIR / "garmin_tokens.json"


class GarminClient:
    def __init__(self):
        self.email = os.getenv("GARMIN_EMAIL")
        self.password = os.getenv("GARMIN_PASSWORD")
        self.client = None
        self._stats = {}

    def connect(self):
        """
        Reutiliza la sesión guardada en Redis y solo hace login con usuario y
        contraseña si no hay sesión o ha caducado. Garmin bloquea durante un
        rato las cuentas que hacen muchos logins seguidos, y /tmp solo no
        sirve: se borra en cada arranque en frío de Vercel.

        La librería sabe cargar y guardar la sesión en un fichero; se le da
        uno en /tmp relleno desde Redis y lo que quede en él se devuelve a Redis.
        """
        saved = None
        try:
            saved = load(TOKENS_KEY)
        except Exception as e:
            logger.error(f"Garmin: no se pudo leer la sesión guardada: {e}")
        try:
            TOKEN_DIR.mkdir(parents=True, exist_ok=True)
            if isinstance(saved, str) and saved:
                TOKEN_FILE.write_text(saved)
            elif TOKEN_FILE.exists():
                TOKEN_FILE.unlink()
        except Exception as e:
            logger.error(f"Garmin: no se pudo preparar la sesión: {e}")

        try:
            self.client = Garmin(self.email, self.password)
            # Con sesión válida no hay login; si caducó, lo hace la librería
            # con usuario y contraseña y escribe la nueva en el fichero.
            self.client.login(str(TOKEN_DIR))
        except Exception as e:
            logger.error(f"Garmin login error: {e}")
            return False

        self._save_tokens(saved)
        return True

    def _save_tokens(self, previous=None):
        """Guarda la sesión si ha cambiado (login nuevo o tokens refrescados)."""
        try:
            tokens = self.client.client.dumps()
            if tokens and tokens != previous:
                save(TOKENS_KEY, tokens)
                logger.info("Garmin: sesión nueva guardada")
        except Exception as e:
            logger.error(f"Garmin: no se pudo guardar la sesión: {e}")

    def _get_stats(self, date):
        """get_stats con memoria: pasos, HRV, estrés y Body Battery semanales
        piden los mismos 7 días; así son 7 llamadas en vez de 28."""
        if date not in self._stats:
            self._stats[date] = self.client.get_stats(date) or {}
        return self._stats[date]

    def _today(self):
        return ahora().strftime("%Y-%m-%d")

    def _date(self, days_ago=0):
        return (ahora() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    # ─── HOY ───

    def get_daily(self, date=None):
        date = date or self._today()
        try:
            s = self._get_stats(date)
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
                "body_battery_current": _safe(s.get("bodyBatteryMostRecentValue")),
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
                    hour = datetime.fromtimestamp(entry[0] / 1000, MADRID).strftime("%H")
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
                    hour = datetime.fromtimestamp(entry[0] / 1000, MADRID).strftime("%H")
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
                stats = self._get_stats(date)
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

    def get_training_status(self, date=None):
        """
        Estado de entreno de Garmin: VO₂max real del reloj, carga de 7 días
        y aclimatación. Es lo que se ve en «Estado de entreno» en la app.

        Ojo con la carga: Garmin suma su propia Training Load (basada en EPOC)
        de los últimos 7 días. No tiene nada que ver con el Relative Effort de
        Strava que usamos para CTL/ATL/TSB — son escalas distintas y no deben
        compararse ni mezclarse. Por eso va en su propio bloque.
        """
        date = date or self._today()
        out = {"date": date}

        # VO₂max — el de correr es el que vale para predecir carreras.
        try:
            metrics = self.client.get_max_metrics(date)
            if isinstance(metrics, list) and metrics:
                metrics = metrics[0]
            if isinstance(metrics, dict):
                generic = metrics.get("generic") or {}
                cycling = metrics.get("cycling") or {}
                heat = metrics.get("heatAltitudeAcclimation") or {}
                run_vo2 = generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue")
                bike_vo2 = cycling.get("vo2MaxPreciseValue") or cycling.get("vo2MaxValue")
                if run_vo2:
                    out["vo2max_running"] = round(float(run_vo2), 1)
                if bike_vo2:
                    out["vo2max_cycling"] = round(float(bike_vo2), 1)
                if heat.get("heatAcclimationPercentage") is not None:
                    out["heat_acclimation"] = _safe(heat.get("heatAcclimationPercentage"))
        except Exception as e:
            logger.error(f"max_metrics: {e}")

        # Estado de entreno + carga aguda de 7 días
        try:
            ts = self.client.get_training_status(date)
            recent = (ts or {}).get("mostRecentTrainingStatus") or {}
            latest = recent.get("latestTrainingStatusData") or {}
            for dev in latest.values():
                if not isinstance(dev, dict):
                    continue
                if dev.get("trainingStatus"):
                    out["status_code"] = dev.get("trainingStatus")
                if dev.get("trainingStatusFeedbackPhrase"):
                    out["status_phrase"] = dev.get("trainingStatusFeedbackPhrase")
                acute = dev.get("acuteTrainingLoadDTO") or {}
                load = (acute.get("acwrStatus") and acute) or acute
                if load.get("dailyAcuteChronicWorkloadRatio") is not None:
                    out["acwr_garmin"] = round(
                        float(load["dailyAcuteChronicWorkloadRatio"]), 2)
                if load.get("acuteTrainingLoad") is not None:
                    out["load_7d"] = round(float(load["acuteTrainingLoad"]))
                break
        except Exception as e:
            logger.error(f"training_status: {e}")

        return out

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
                s = self._get_stats(date)
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
                stats = self._get_stats(date)
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
                s = self._get_stats(date)
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
                s = self._get_stats(date)
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
                s = self._get_stats(date)
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

    # ─── ENTRENOS PROGRAMADOS (Garmin Coach + calendario) ───

    def get_scheduled_workouts(self, days=14, max_details=12):
        """
        Próximos entrenos del calendario de Garmin: los de un plan de Garmin
        Coach (adaptativos, van por UUID) y los que programes tú a mano.

        El calendario solo trae título, fecha y deporte; los pasos (series,
        ritmos, zonas) salen de pedir cada entreno por separado. Si ese detalle
        falla, el entreno se lista igual con lo que traiga el calendario.
        """
        today = ahora().date()
        until = today + timedelta(days=days)

        # El calendario va por meses (0-indexados en la API de Garmin)
        months = {(today.year, today.month), (until.year, until.month)}
        items = []
        for year, month in sorted(months):
            try:
                cal = self.client.connectapi(
                    f"/calendar-service/year/{year}/month/{month - 1}") or {}
                items.extend(cal.get("calendarItems") or [])
            except Exception as e:
                logger.error(f"calendar {year}-{month}: {e}")

        upcoming, seen = [], set()
        for it in items:
            if not isinstance(it, dict):
                continue
            kind = str(it.get("itemType") or "")
            is_workout = (it.get("workoutUuid") or it.get("workoutId")
                          or "workout" in kind.lower())
            if not is_workout or kind == "activity":
                continue
            date = str(it.get("date") or "")[:10]
            if not date or not (today.isoformat() <= date <= until.isoformat()):
                continue
            key = (date, it.get("workoutUuid") or it.get("workoutId") or it.get("id"))
            if key in seen:
                continue
            seen.add(key)
            upcoming.append(it)

        upcoming.sort(key=lambda it: str(it.get("date")))
        out = []
        for i, it in enumerate(upcoming):
            detail = self._workout_detail(it) if i < max_details else None
            out.append(_parse_workout(it, detail))
        return out

    def _workout_detail(self, item):
        # Garmin Coach va por UUID; los programados a mano, por id de entreno o
        # de programación. Se prueba en ese orden hasta que uno conteste.
        urls = []
        if item.get("workoutUuid"):
            urls.append(f"/workout-service/fbt-adaptive/{item['workoutUuid']}")
        if item.get("workoutId"):
            urls.append(f"/workout-service/workout/{item['workoutId']}")
        if item.get("id"):
            urls.append(f"/workout-service/schedule/{item['id']}")
        for url in urls:
            try:
                d = self.client.connectapi(url)
            except Exception as e:
                logger.error(f"workout detail {url}: {e}")
                continue
            if isinstance(d, dict) and isinstance(d.get("workout"), dict):
                d = d["workout"]
            if isinstance(d, dict) and d:
                return d
        return None

    # ─── SNAPSHOT ───

    def get_full_snapshot(self):
        today = self._today()
        logger.info(f"Garmin snapshot: {today}")
        return {
            "timestamp": ahora().isoformat(),
            # Hoy
            "daily": self.get_daily(today),
            "sleep": self.get_sleep(today),
            "heart_rate": self.get_heart_rate(today),
            "stress": self.get_stress(today),
            "body_battery": self.get_body_battery(today),
            "hrv": self.get_hrv(today),
            "training_status": self.get_training_status(today),
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


# ─── Entrenos programados: de la estructura de Garmin a algo legible ───

STEP_NAMES = {
    "warmup": "Calentamiento", "cooldown": "Vuelta a la calma",
    "interval": "Serie", "recovery": "Recuperación", "rest": "Descanso",
    "run": "Carrera", "other": "Otro", "main": "Principal",
}

SPORT_KEYS = {
    "running": "Run", "trail_running": "Run", "treadmill_running": "Run",
    "cycling": "Ride", "indoor_cycling": "Ride", "virtual_ride": "Ride",
    "hiking": "Hike", "walking": "Walk", "strength_training": "Strength",
    "swimming": "Swim", "lap_swimming": "Swim",
}


def _fmt_secs(sec):
    sec = int(round(sec or 0))
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    if h:
        return f"{h}h{m:02d}"
    return f"{m}:{s:02d}" if s else f"{m} min"


def _fmt_dist(m):
    m = float(m or 0)
    if m >= 1000:
        km = m / 1000
        return f"{km:.2f}".rstrip("0").rstrip(".") + " km"
    return f"{int(round(m))} m"


def _fmt_pace(speed):
    """m/s → min:ss /km"""
    if not speed or speed <= 0:
        return None
    sec = 1000 / speed
    return f"{int(sec // 60)}:{int(round(sec % 60)):02d}"


_KEYS = {"stepType": "stepTypeKey", "endCondition": "conditionTypeKey",
         "targetType": "workoutTargetTypeKey", "sportType": "sportTypeKey"}


def _key(obj, field):
    """Garmin anida los tipos: {"stepType": {"stepTypeKey": "warmup", ...}}."""
    v = (obj or {}).get(field)
    if isinstance(v, dict):
        return str(v.get(_KEYS[field]) or "")
    return str(v or "")


def _step_duration(step):
    cond = _key(step, "endCondition")
    val = step.get("endConditionValue")
    if cond == "time" and val:
        return _fmt_secs(val)
    if cond == "distance" and val:
        return _fmt_dist(val)
    if cond == "lap.button":
        return "hasta pulsar vuelta"
    if cond == "heart.rate" and val:
        return f"hasta {int(val)} ppm"
    if cond == "calories" and val:
        return f"{int(val)} kcal"
    if cond == "reps" and val:
        return f"{int(val)} reps"
    return None


def _step_target(step):
    kind = _key(step, "targetType")
    lo, hi = step.get("targetValueOne"), step.get("targetValueTwo")
    zone = step.get("zoneNumber")
    if not kind or kind == "no.target":
        return None
    if kind == "pace.zone":
        if lo and hi:
            # Velocidad más alta = ritmo más rápido: el rango va de rápido a lento
            fast, slow = _fmt_pace(max(lo, hi)), _fmt_pace(min(lo, hi))
            return f"{fast}–{slow} /km"
        return f"ritmo Z{zone}" if zone else None
    if kind == "speed.zone":
        if lo and hi:
            return f"{min(lo, hi) * 3.6:.1f}–{max(lo, hi) * 3.6:.1f} km/h"
        return f"velocidad Z{zone}" if zone else None
    if kind == "heart.rate.zone":
        if zone:
            return f"FC zona {zone}"
        if lo and hi:
            return f"{int(min(lo, hi))}–{int(max(lo, hi))} ppm"
    if kind in ("power.zone", "power"):
        if zone:
            return f"potencia Z{zone}"
        if lo and hi:
            return f"{int(min(lo, hi))}–{int(max(lo, hi))} W"
    if kind == "cadence" and lo and hi:
        return f"cadencia {int(min(lo, hi))}–{int(max(lo, hi))}"
    return None


def _parse_steps(steps):
    out = []
    for st in sorted(steps or [], key=lambda x: x.get("stepOrder") or 0):
        if not isinstance(st, dict):
            continue
        if st.get("type") == "RepeatGroupDTO" or st.get("workoutSteps"):
            out.append({
                "repeat": int(st.get("numberOfIterations") or st.get("endConditionValue") or 1),
                "steps": _parse_steps(st.get("workoutSteps")),
            })
            continue
        kind = _key(st, "stepType")
        out.append({
            "type": kind,
            "label": STEP_NAMES.get(kind, kind.capitalize() or "Paso"),
            "duration": _step_duration(st),
            "target": _step_target(st),
            "note": st.get("description") or None,
        })
    return out


def _parse_workout(item, detail):
    """Une la entrada del calendario con el detalle del entreno (si lo hay)."""
    d = detail if isinstance(detail, dict) else {}
    sport = (_key(d, "sportType") or item.get("sportTypeKey") or "").lower()
    steps = []
    for seg in d.get("workoutSegments") or []:
        steps.extend(_parse_steps(seg.get("workoutSteps")))

    duration = (d.get("estimatedDurationInSecs") or item.get("duration")
                or d.get("workoutDuration"))
    distance = (d.get("estimatedDistanceInMeters") or item.get("distance")
                or d.get("workoutDistance"))
    return {
        "date": str(item.get("date"))[:10],
        "title": d.get("workoutName") or item.get("title") or "Entreno",
        "sport": SPORT_KEYS.get(sport, sport.capitalize() or "Other"),
        "sport_key": sport,
        "coach": bool(item.get("workoutUuid")) or "fbt" in str(item.get("itemType", "")).lower(),
        "description": d.get("description") or item.get("description") or None,
        "phrase": d.get("workoutPhrase") or d.get("trainingEffectLabel") or None,
        "duration_sec": int(duration) if duration else None,
        "distance_m": int(distance) if distance else None,
        "steps": steps,
    }
