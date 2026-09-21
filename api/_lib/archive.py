"""Archivo diario.

Hasta ahora Redis solo guardaba la foto de *hoy* (`garmin`, `strava`,
`metrics`) y cada sync la machacaba: no quedaba rastro de cómo estabas hace un
mes. Todo lo histórico que enseña la app sale de las ventanas móviles que
Garmin devuelve en ese momento (7 días, 8 semanas), así que en cuanto un dato
se sale de la ventana desaparece para siempre.

Aquí se guarda una ficha compacta por día en `day:YYYY-MM-DD`, más un índice
(`day:index`) con las fechas que hay, para poder listarlas sin recorrer Redis
entero.

Compacta a propósito: la foto completa lleva la curva de FC del día (248+
mediciones) y no tiene sentido multiplicar eso por 365.

Dos cosas que hace y que no son obvias:

- **Rellena los últimos 7 días, no solo hoy.** El cron corre de madrugada,
  cuando «hoy» son 200 pasos y nada más; si solo archivara hoy, el archivo
  sería una colección de días vacíos. Los arrays semanales del snapshot
  (`steps_week`, `hrv_week`, …) traen los 7 últimos días con fecha, así que se
  aprovechan para completar hacia atrás. De paso tapa los huecos de los días
  que no sincronizaste.
- **Nunca degrada un día ya archivado.** Al fusionar, un valor nuevo a 0 o
  vacío no pisa uno anterior que sí tenía dato: en estas métricas el 0 casi
  siempre significa «no medido», y la ficha rica de ayer por la noche no debe
  perder la readiness solo porque el array semanal de hoy no la traiga.
"""

from datetime import datetime

from .cache import save, load, mload

INDEX_KEY = "day:index"
BACKFILL_DAYS = 7


def _key(date):
    return f"day:{date}"


def _clean(d):
    """Quita claves sin dato para no archivar ruido."""
    return {k: v for k, v in (d or {}).items() if v not in (None, 0, "", [], {})}


def _merge(old, new):
    """Fusiona `new` sobre `old` sin dejar que un vacío pise un dato bueno."""
    out = dict(old or {})
    for k, v in (new or {}).items():
        if isinstance(v, dict):
            merged = _merge(out.get(k) if isinstance(out.get(k), dict) else {}, v)
            if merged:
                out[k] = merged
        elif v not in (None, 0, "", [], {}):
            out[k] = v
        elif k not in out:
            out[k] = v
    return out


def _by_date(rows):
    """Array semanal del snapshot → {fecha: fila}."""
    return {r["date"]: r for r in (rows or []) if isinstance(r, dict) and r.get("date")}


def _today_record(garmin, metrics):
    """Ficha completa del día que trae el snapshot detallado."""
    daily = garmin.get("daily") or {}
    sleep = garmin.get("sleep") or {}
    hrv = garmin.get("hrv") or {}
    fitness = (metrics.get("fitness") or {}).get("current") or {}
    readiness = metrics.get("readiness") or {}
    acwr = metrics.get("acwr") or {}
    breakdown = readiness.get("breakdown") or {}

    return _clean({
        "daily": _clean({
            "steps": daily.get("steps"),
            "steps_goal": daily.get("steps_goal"),
            "calories": daily.get("calories_total"),
            "calories_active": daily.get("calories_active"),
            "distance_km": daily.get("distance_km"),
            "active_minutes": daily.get("active_minutes"),
            "floors": daily.get("floors_climbed"),
            "resting_hr": daily.get("resting_hr"),
            "min_hr": daily.get("min_hr"),
            "max_hr": daily.get("max_hr"),
            "avg_stress": daily.get("avg_stress"),
            "max_stress": daily.get("max_stress"),
            "bb_high": daily.get("body_battery_high"),
            "bb_low": daily.get("body_battery_low"),
            "avg_spo2": daily.get("avg_spo2"),
            "lowest_spo2": daily.get("lowest_spo2"),
            "avg_respiration": daily.get("avg_respiration"),
        }),
        "sleep": _clean({
            "score": sleep.get("score"),
            "total_min": sleep.get("total_min"),
            "deep_min": sleep.get("deep_min"),
            "light_min": sleep.get("light_min"),
            "rem_min": sleep.get("rem_min"),
            "awake_min": sleep.get("awake_min"),
            "start_time": sleep.get("start_time"),
            "end_time": sleep.get("end_time"),
        }),
        "hrv": _clean({
            "last_night_avg": hrv.get("last_night_avg"),
            "weekly_avg": hrv.get("weekly_avg"),
            "status": hrv.get("status"),
        }),
        "fitness": _clean({
            "ctl": fitness.get("ctl"),
            "atl": fitness.get("atl"),
            "tsb": fitness.get("tsb"),
            "status": fitness.get("status"),
        }),
        "readiness": _clean({
            "score": readiness.get("score"),
            "status": readiness.get("status"),
            "sleep": (breakdown.get("sleep") or {}).get("value"),
            "hrv": (breakdown.get("hrv") or {}).get("value"),
            "body_battery": (breakdown.get("body_battery") or {}).get("value"),
            "load": (breakdown.get("load") or {}).get("value"),
        }),
        "acwr": _clean({
            "ratio": acwr.get("ratio"),
            "acute": acwr.get("acute_load"),
            "chronic": acwr.get("chronic_load"),
            "risk": acwr.get("risk"),
        }),
        "vo2max": metrics.get("vo2max_estimated"),
    })


def _backfill_records(garmin, metrics):
    """Fichas parciales de los últimos días a partir de los arrays semanales."""
    steps = _by_date(garmin.get("steps_week"))
    hrv = _by_date(garmin.get("hrv_week"))
    sleep = _by_date(garmin.get("sleep_week"))
    stress = _by_date(garmin.get("stress_week"))
    battery = _by_date(garmin.get("body_battery_week"))
    timeline = _by_date((metrics.get("fitness") or {}).get("timeline"))

    out = {}
    for date in set(steps) | set(hrv) | set(sleep) | set(stress) | set(battery):
        s = sleep.get(date) or {}
        hours = s.get("hours")
        rec = _clean({
            "daily": _clean({
                "steps": (steps.get(date) or {}).get("steps"),
                "resting_hr": (hrv.get(date) or {}).get("rhr"),
                "avg_stress": (stress.get(date) or {}).get("stress"),
                "bb_high": (battery.get(date) or {}).get("high"),
                "bb_low": (battery.get(date) or {}).get("low"),
            }),
            "sleep": _clean({
                "score": s.get("score"),
                "total_min": round(hours * 60) if hours else None,
            }),
            "hrv": _clean({
                "last_night_avg": (hrv.get(date) or {}).get("hrv"),
            }),
            "fitness": _clean({
                "ctl": (timeline.get(date) or {}).get("ctl"),
                "atl": (timeline.get(date) or {}).get("atl"),
                "tsb": (timeline.get(date) or {}).get("tsb"),
                "load": (timeline.get(date) or {}).get("load"),
            }),
        })
        if rec:
            out[date] = rec
    return out


def archive_day(garmin, metrics):
    """Archiva hoy + los últimos días. Devuelve las fechas escritas."""
    garmin = garmin or {}
    metrics = metrics or {}

    records = _backfill_records(garmin, metrics)

    today = (garmin.get("daily") or {}).get("date") or (garmin.get("sleep") or {}).get("date")
    if today:
        records[today] = _merge(records.get(today, {}), _today_record(garmin, metrics))

    if not records:
        return []

    dates = sorted(records)[-BACKFILL_DAYS:]
    existing = dict(zip(dates, mload([_key(d) for d in dates])))

    now = datetime.now().isoformat()
    written = []
    for date in dates:
        merged = _merge(existing.get(date) or {}, records[date])
        if not merged:
            continue
        merged["date"] = date
        merged["archived_at"] = now
        save(_key(date), merged)
        written.append(date)

    if written:
        index = sorted(set(load(INDEX_KEY) or []) | set(written))
        save(INDEX_KEY, index)

    return written


def read_days(days=90, end=None):
    """Últimos N días archivados, del más antiguo al más reciente."""
    index = load(INDEX_KEY) or []
    if end:
        index = [d for d in index if d <= end]
    dates = index[-max(1, int(days)):]
    return [r for r in mload([_key(d) for d in dates]) if r]
