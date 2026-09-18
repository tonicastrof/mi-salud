"""
Analítica de entrenamiento a partir de las actividades de Strava.

Agrega volumen semanal y mensual, calendario de días entrenados,
reparto por deporte, tendencias de ritmo/FC y récords personales.
Todo se calcula en memoria — no hace llamadas a la API.
"""

from datetime import datetime, timedelta

WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
WEEKDAYS_SHORT = ["L", "M", "X", "J", "V", "S", "D"]
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
         "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

SPORT_LABELS = {"Run": "Correr", "Ride": "Bici", "Hike": "Senderismo"}


def _date(a):
    """Fecha (date) de una actividad, o None si no se puede parsear."""
    try:
        return datetime.fromisoformat(a["date"]).date()
    except (ValueError, KeyError, TypeError):
        return None


def _monday(d):
    return d - timedelta(days=d.weekday())


def _fmt_hm(seconds):
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    return f"{h}h{m:02d}" if h else f"{m}m"


def _fmt_pace(sec_per_km):
    if not sec_per_km or sec_per_km <= 0:
        return None
    return f"{int(sec_per_km // 60)}:{int(sec_per_km % 60):02d}"


def _empty_bucket():
    return {"km": 0.0, "hours": 0.0, "elev": 0, "effort": 0, "count": 0,
            "calories": 0, "by_sport": {}}


def _add(bucket, a):
    bucket["km"] += a.get("distance", 0) or 0
    bucket["hours"] += (a.get("moving_time_sec", 0) or 0) / 3600
    bucket["elev"] += a.get("elevation", 0) or 0
    bucket["effort"] += a.get("effort", 0) or 0
    bucket["calories"] += a.get("calories", 0) or 0
    bucket["count"] += 1
    sport = a.get("sport", "Other")
    bucket["by_sport"][sport] = round(
        bucket["by_sport"].get(sport, 0) + (a.get("distance", 0) or 0), 1)


def _round(bucket):
    bucket["km"] = round(bucket["km"], 1)
    bucket["hours"] = round(bucket["hours"], 1)
    bucket["elev"] = round(bucket["elev"])
    bucket["effort"] = round(bucket["effort"])
    return bucket


# ─── VOLUMEN SEMANAL ───

def weekly_volume(activities: list, weeks: int = 16) -> list:
    """
    Volumen por SEMANA NATURAL (lunes a domingo), de la más antigua a la actual.

    Ojo: la última semana es la semana en curso y casi siempre está a medias.
    Por eso cada bucket lleva `days_elapsed` (días ya transcurridos, 1-7) y
    `partial`. Comparar esa semana con las anteriores —o con la ventana móvil
    de 7 días de `metrics.calculate_acwr`— sin tener eso en cuenta es lo que
    hacía que la misma carga se viera como 202 en la gráfica y como 400 en el
    informe. No son la misma métrica: una es lunes→hoy, la otra hoy-6→hoy.
    """
    today = datetime.now().date()
    first_monday = _monday(today) - timedelta(weeks=weeks - 1)

    buckets = {}
    for i in range(weeks):
        wk = first_monday + timedelta(weeks=i)
        buckets[wk] = _empty_bucket()

    for a in activities:
        d = _date(a)
        if not d or d > today:
            continue
        wk = _monday(d)
        if wk in buckets:
            _add(buckets[wk], a)

    out = []
    for i in range(weeks):
        wk = first_monday + timedelta(weeks=i)
        b = _round(buckets[wk])
        b["week_start"] = wk.isoformat()
        b["label"] = f"{wk.day} {MESES[wk.month - 1]}"
        b["is_current"] = wk == _monday(today)
        b["days_elapsed"] = min(7, (today - wk).days + 1) if wk <= today else 0
        b["partial"] = b["days_elapsed"] < 7
        out.append(b)
    return out


def rolling_load(activities: list, days: int = 7, offset: int = 0) -> float:
    """
    Carga (Relative Effort) en una ventana MÓVIL de `days` días que termina
    hace `offset` días. offset=0 → los últimos `days` días contando hoy.

    Es la ventana que usa el ACWR. No coincide con la semana natural y no
    tiene por qué: aquí siempre hay `days` días completos.
    """
    today = datetime.now().date()
    total = 0.0
    for a in activities:
        d = _date(a)
        if not d:
            continue
        days_ago = (today - d).days
        if offset <= days_ago < offset + days:
            total += a.get("effort", 0) or 0
    return total


# ─── CALENDARIO ───

def calendar_grid(activities: list, weeks: int = 12) -> dict:
    """
    Rejilla de días entrenados: `weeks` semanas × 7 días (lunes→domingo).
    Cada día trae km, minutos, esfuerzo y los deportes de ese día.
    """
    today = datetime.now().date()
    first_monday = _monday(today) - timedelta(weeks=weeks - 1)

    days = {}
    for a in activities:
        d = _date(a)
        if not d or d < first_monday or d > today:
            continue
        cell = days.setdefault(d, {
            "km": 0.0, "minutes": 0, "effort": 0, "count": 0,
            "sports": [], "names": [],
        })
        cell["km"] += a.get("distance", 0) or 0
        cell["minutes"] += round((a.get("moving_time_sec", 0) or 0) / 60)
        cell["effort"] += a.get("effort", 0) or 0
        cell["count"] += 1
        sport = a.get("sport", "Other")
        if sport not in cell["sports"]:
            cell["sports"].append(sport)
        cell["names"].append(a.get("name", ""))

    grid = []
    for w in range(weeks):
        monday = first_monday + timedelta(weeks=w)
        row = {"week_start": monday.isoformat(),
               "label": f"{monday.day} {MESES[monday.month - 1]}",
               "days": []}
        for i in range(7):
            d = monday + timedelta(days=i)
            cell = days.get(d)
            row["days"].append({
                "date": d.isoformat(),
                "day": d.day,
                "future": d > today,
                "today": d == today,
                "km": round(cell["km"], 1) if cell else 0,
                "minutes": cell["minutes"] if cell else 0,
                "effort": round(cell["effort"]) if cell else 0,
                "count": cell["count"] if cell else 0,
                "sports": cell["sports"] if cell else [],
                "names": cell["names"] if cell else [],
            })
        grid.append(row)

    trained = [d for d in days if days[d]["count"] > 0]
    return {
        "weeks": grid,
        "weekday_labels": WEEKDAYS_SHORT,
        "active_days": len(trained),
        "total_days": (today - first_monday).days + 1,
        "streak": current_streak(activities),
        "rest_days_last_7": 7 - len([d for d in trained if (today - d).days < 7]),
    }


def current_streak(activities: list) -> int:
    """Días consecutivos entrenando hasta hoy (o hasta ayer si hoy es descanso)."""
    dates = {_date(a) for a in activities}
    dates.discard(None)
    if not dates:
        return 0
    today = datetime.now().date()
    start = today if today in dates else today - timedelta(days=1)
    streak = 0
    d = start
    while d in dates:
        streak += 1
        d -= timedelta(days=1)
    return streak


# ─── REPARTO POR DEPORTE ───

def sport_totals(activities: list, days: int = 90) -> list:
    """Totales por deporte en los últimos N días."""
    cutoff = datetime.now().date() - timedelta(days=days - 1)
    totals = {}
    for a in activities:
        d = _date(a)
        if not d or d < cutoff:
            continue
        sport = a.get("sport", "Other")
        t = totals.setdefault(sport, {
            "sport": sport, "label": SPORT_LABELS.get(sport, sport),
            "icon": a.get("icon", "🏋️"), "km": 0.0, "hours": 0.0,
            "elev": 0, "count": 0, "effort": 0,
        })
        t["km"] += a.get("distance", 0) or 0
        t["hours"] += (a.get("moving_time_sec", 0) or 0) / 3600
        t["elev"] += a.get("elevation", 0) or 0
        t["effort"] += a.get("effort", 0) or 0
        t["count"] += 1

    out = []
    for t in totals.values():
        t["km"] = round(t["km"], 1)
        t["hours"] = round(t["hours"], 1)
        t["elev"] = round(t["elev"])
        t["effort"] = round(t["effort"])
        out.append(t)
    return sorted(out, key=lambda x: -x["hours"])


# ─── DISTRIBUCIÓN SEMANAL / HORARIA ───

def weekday_distribution(activities: list, days: int = 90) -> list:
    """Cuántas sesiones y km por día de la semana."""
    cutoff = datetime.now().date() - timedelta(days=days - 1)
    rows = [{"day": WEEKDAYS_SHORT[i], "name": WEEKDAYS[i],
             "count": 0, "km": 0.0, "minutes": 0} for i in range(7)]
    for a in activities:
        d = _date(a)
        if not d or d < cutoff:
            continue
        r = rows[d.weekday()]
        r["count"] += 1
        r["km"] += a.get("distance", 0) or 0
        r["minutes"] += round((a.get("moving_time_sec", 0) or 0) / 60)
    for r in rows:
        r["km"] = round(r["km"], 1)
    return rows


def time_of_day_distribution(activities: list, days: int = 90) -> list:
    """Reparto por franja horaria (usa la hora de inicio si está disponible)."""
    cutoff = datetime.now().date() - timedelta(days=days - 1)
    slots = [
        {"slot": "Madrugada", "range": "00-06", "icon": "🌙", "count": 0},
        {"slot": "Mañana", "range": "06-12", "icon": "🌅", "count": 0},
        {"slot": "Tarde", "range": "12-18", "icon": "☀️", "count": 0},
        {"slot": "Noche", "range": "18-24", "icon": "🌆", "count": 0},
    ]
    for a in activities:
        d = _date(a)
        hour = a.get("hour")
        if not d or d < cutoff or hour is None:
            continue
        slots[min(3, int(hour) // 6)]["count"] += 1
    return slots


# ─── TENDENCIAS ───

def pace_trend(activities: list, sport: str = "Run", limit: int = 24) -> list:
    """Ritmo medio y FC de las últimas sesiones de un deporte (antiguo→reciente)."""
    rows = []
    for a in activities:
        d = _date(a)
        if not d or a.get("sport") != sport:
            continue
        dist = a.get("distance", 0) or 0
        secs = a.get("moving_time_sec", 0) or 0
        if dist < 1 or secs <= 0:
            continue
        pace_sec = secs / dist
        rows.append({
            "date": d.isoformat(),
            "label": f"{d.day} {MESES[d.month - 1]}",
            "km": round(dist, 1),
            "pace_sec": round(pace_sec),
            "pace": _fmt_pace(pace_sec),
            "speed": round(dist / (secs / 3600), 1),
            "hr": round(a.get("avg_hr") or 0) or None,
            "effort": a.get("effort", 0) or 0,
            "elev": a.get("elevation", 0) or 0,
            "name": a.get("name", ""),
        })
    rows.sort(key=lambda r: r["date"])
    return rows[-limit:]


def monthly_volume(activities: list, months: int = 12) -> list:
    """Volumen por mes natural, del más antiguo al actual."""
    today = datetime.now().date()
    keys = []
    y, m = today.year, today.month
    for _ in range(months):
        keys.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    keys.reverse()

    buckets = {k: _empty_bucket() for k in keys}
    for a in activities:
        d = _date(a)
        if not d:
            continue
        k = (d.year, d.month)
        if k in buckets:
            _add(buckets[k], a)

    out = []
    for (y, m) in keys:
        b = _round(buckets[(y, m)])
        b["month"] = f"{y}-{m:02d}"
        b["label"] = MESES[m - 1]
        out.append(b)
    return out


# ─── RÉCORDS ───

def records(activities: list) -> list:
    """Mejores marcas de la ventana descargada."""
    out = []

    def best(label, icon, candidates, key, fmt):
        pool = [a for a in candidates if (key(a) or 0) > 0]
        if not pool:
            return
        a = max(pool, key=key)
        out.append({
            "label": label, "icon": icon, "value": fmt(a),
            "name": a.get("name", ""), "date": a.get("date_formatted") or a.get("date"),
            "id": a.get("id"),
        })

    runs = [a for a in activities if a.get("sport") == "Run"]
    rides = [a for a in activities if a.get("sport") == "Ride"]

    best("Carrera más larga", "🏃", runs, lambda a: a.get("distance", 0) or 0,
         lambda a: f"{a['distance']} km")
    best("Ruta más larga", "🚴", rides, lambda a: a.get("distance", 0) or 0,
         lambda a: f"{a['distance']} km")
    best("Más desnivel", "⛰️", activities, lambda a: a.get("elevation", 0) or 0,
         lambda a: f"{a['elevation']} m")
    best("Sesión más dura", "🔥", activities, lambda a: a.get("effort", 0) or 0,
         lambda a: f"RE {a['effort']}")

    # Carrera más rápida con al menos 5 km
    fast = [a for a in runs
            if (a.get("distance", 0) or 0) >= 5 and (a.get("moving_time_sec", 0) or 0) > 0]
    if fast:
        a = min(fast, key=lambda x: x["moving_time_sec"] / x["distance"])
        pace = a["moving_time_sec"] / a["distance"]
        out.append({
            "label": "Ritmo más rápido (5 km+)", "icon": "⚡",
            "value": f"{_fmt_pace(pace)}/km", "name": a.get("name", ""),
            "date": a.get("date_formatted") or a.get("date"), "id": a.get("id"),
        })
    return out


# ─── TODO JUNTO ───

def build_analytics(activities: list) -> dict:
    """Paquete completo de analítica para el dashboard y el entrenador IA."""
    activities = activities or []
    weeks = weekly_volume(activities, 16)

    # La media de referencia se calcula sobre las 4 últimas semanas COMPLETAS.
    # Antes incluía la semana en curso (a medias), así que la media bajaba sola
    # según avanzaba la semana y el "vs media 4s" salía doblemente falseado.
    this_week = weeks[-1] if weeks else _empty_bucket()
    done = [w for w in weeks[:-1] if not w.get("partial")][-4:] if weeks else []
    n = len(done) or 1

    avg_km = round(sum(w["km"] for w in done) / n, 1)
    avg_hours = round(sum(w["hours"] for w in done) / n, 1)
    avg_load = round(sum(w["effort"] for w in done) / n)

    # Proyección de la semana en curso al ritmo que lleva, para poder
    # compararla con semanas completas sin comparar 5 días contra 7.
    elapsed = this_week.get("days_elapsed") or 7
    factor = 7 / elapsed
    proj_km = round(this_week.get("km", 0) * factor, 1)
    proj_load = round(this_week.get("effort", 0) * factor)

    return {
        "weekly": weeks,
        "monthly": monthly_volume(activities, 12),
        "calendar": calendar_grid(activities, 12),
        "by_sport": sport_totals(activities, 90),
        "weekday": weekday_distribution(activities, 90),
        "time_of_day": time_of_day_distribution(activities, 90),
        "run_trend": pace_trend(activities, "Run", 24),
        "ride_trend": pace_trend(activities, "Ride", 24),
        "records": records(activities),
        "summary": {
            "activities_loaded": len(activities),
            # Semana natural en curso (lunes → hoy). Parcial casi siempre.
            "this_week_km": this_week.get("km", 0),
            "this_week_hours": this_week.get("hours", 0),
            "this_week_sessions": this_week.get("count", 0),
            "this_week_load": this_week.get("effort", 0),
            "this_week_days_elapsed": elapsed,
            "this_week_partial": bool(this_week.get("partial")),
            "this_week_projected_km": proj_km,
            "this_week_projected_load": proj_load,
            # Medias sobre semanas COMPLETAS, sin contar la que está en curso.
            "avg_week_km_4w": avg_km,
            "avg_week_hours_4w": avg_hours,
            "avg_week_load_4w": avg_load,
            "avg_weeks_used": len(done),
            # Ventana móvil de 7 días (hoy-6 → hoy): la que usa el ACWR.
            "last_7d_load": round(rolling_load(activities, 7)),
            "last_7d_km": round(sum(
                a.get("distance", 0) or 0 for a in activities
                if _date(a) and 0 <= (datetime.now().date() - _date(a)).days < 7), 1),
            "streak": current_streak(activities),
        },
    }
