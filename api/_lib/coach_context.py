"""
Construye el dossier que se le pasa a Claude para que ejerce de entrenador.

Resume en texto compacto todo lo que sabemos del atleta: perfil, datos de
Garmin de hoy, tendencias de la semana, métricas calculadas (CTL/ATL/TSB,
ACWR, readiness) y la analítica de Strava (volumen semanal, calendario,
récords y últimas sesiones).

El texto es determinista (sin marcas de tiempo por petición) para que el
caché de prompt de la API funcione entre preguntas.
"""

from datetime import datetime

from .analytics import build_analytics, WEEKDAYS

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _line(label, value, unit=""):
    if value in (None, "", 0, "—"):
        return None
    return f"- {label}: {value}{unit}"


def _block(title, lines):
    lines = [l for l in lines if l]
    if not lines:
        return ""
    return f"## {title}\n" + "\n".join(lines) + "\n"


def build_context(garmin: dict, strava: dict, metrics: dict,
                  analytics: dict = None, max_activities: int = 40) -> str:
    garmin = garmin or {}
    strava = strava or {}
    metrics = metrics or {}
    activities = strava.get("activities", []) or []
    an = analytics or build_analytics(activities)

    profile = strava.get("profile", {}) or {}
    daily = garmin.get("daily", {}) or {}
    sleep = garmin.get("sleep", {}) or {}
    hrv = garmin.get("hrv", {}) or {}
    fitness = (metrics.get("fitness", {}) or {}).get("current", {}) or {}
    acwr = metrics.get("acwr", {}) or {}
    readiness = metrics.get("readiness", {}) or {}
    summary = an.get("summary", {}) or {}

    today = datetime.now().date()
    parts = [f"# Dossier del atleta — {today.isoformat()} ({DIAS[today.weekday()]})\n"]

    # ─── Perfil ───
    parts.append(_block("Perfil", [
        _line("Nombre", profile.get("name")),
        _line("Peso", profile.get("weight"), " kg"),
        _line("FTP", profile.get("ftp"), " W"),
        _line("VO₂max estimado", metrics.get("vo2max_estimated"), " ml/kg/min"),
        _line("Zonas de FC", _zones_text(strava.get("zones", {}))),
    ]))

    # ─── Hoy (Garmin) ───
    parts.append(_block("Estado de hoy (Garmin)", [
        _line("Sueño", sleep.get("total_formatted")),
        _line("Score de sueño", sleep.get("score"), "/100"),
        _line("Fases", _sleep_phases(sleep)),
        _line("HRV última noche", hrv.get("last_night_avg"), " ms"),
        _line("HRV media semanal", hrv.get("weekly_avg"), " ms"),
        _line("Estado HRV", hrv.get("status")),
        _line("FC en reposo", daily.get("resting_hr"), " bpm"),
        _line("Body Battery actual", daily.get("body_battery_current")),
        _line("Body Battery máx hoy", daily.get("body_battery_high")),
        _line("Estrés medio", daily.get("avg_stress")),
        _line("Pasos", daily.get("steps")),
        _line("Minutos activos", daily.get("active_minutes")),
        _line("SpO₂ medio", daily.get("avg_spo2"), " %"),
    ]))

    # ─── Tendencias de la semana ───
    parts.append(_block("Tendencias de los últimos 7 días (Garmin)", [
        _line("Sueño por noche", _week_series(garmin.get("sleep_week", []), "d", "hours", "h")),
        _line("Score de sueño", _week_series(garmin.get("sleep_week", []), "d", "score")),
        _line("HRV", _week_series(garmin.get("hrv_week", []), "d", "hrv", " ms")),
        _line("FC reposo", _week_series(garmin.get("hrv_week", []), "d", "rhr", " bpm")),
        _line("Estrés medio", _week_series(garmin.get("stress_week", []), "d", "stress")),
        _line("Pasos", _week_series(garmin.get("steps_week", []), "d", "steps")),
    ]))

    # ─── Carga de entrenamiento ───
    parts.append(_block("Carga de entrenamiento (calculada)", [
        _line("Fitness (CTL)", fitness.get("ctl")),
        _line("Fatiga (ATL)", fitness.get("atl")),
        _line("Forma (TSB)", fitness.get("tsb")),
        _line("Estado de forma", fitness.get("status")),
        _line("Ratio agudo:crónico", acwr.get("ratio")),
        _line("Riesgo por ACWR", acwr.get("risk")),
        _line("Carga semanal (4 semanas, antigua→reciente)",
              ", ".join(str(x) for x in acwr.get("weekly_loads", [])) or None),
        _line("Training readiness", readiness.get("score"), "/100"),
        _line("Lectura de readiness", readiness.get("status")),
    ]))

    # ─── Volumen ───
    weekly = an.get("weekly", [])[-8:]
    parts.append(_block("Volumen semanal (últimas 8 semanas, antigua→actual)", [
        f"- Semana del {w['label']}: {w['km']} km · {w['hours']} h · "
        f"{w['elev']} m D+ · {w['count']} sesiones · carga {w['effort']}"
        for w in weekly
    ] + [
        _line("Media 4 semanas", f"{summary.get('avg_week_km_4w')} km / "
                                 f"{summary.get('avg_week_hours_4w')} h"),
        _line("Racha de días seguidos", summary.get("streak")),
    ]))

    # ─── Reparto por deporte ───
    parts.append(_block("Reparto por deporte (90 días)", [
        f"- {s['label']}: {s['count']} sesiones · {s['km']} km · "
        f"{s['hours']} h · {s['elev']} m D+"
        for s in an.get("by_sport", [])
    ]))

    # ─── Días de la semana ───
    wd = an.get("weekday", [])
    if wd:
        parts.append(_block("Días en los que suele entrenar (90 días)", [
            "- " + " · ".join(f"{WEEKDAYS[i]} {r['count']}" for i, r in enumerate(wd))
        ]))

    # ─── Calendario reciente ───
    cal = an.get("calendar", {})
    recent = (cal.get("weeks") or [])[-4:]
    cal_lines = []
    for w in recent:
        dias = []
        for i, d in enumerate(w["days"]):
            if d["future"]:
                continue
            mark = f"{'/'.join(d['sports'])} {d['km']}km" if d["count"] else "descanso"
            dias.append(f"{WEEKDAYS[i]} {mark}")
        cal_lines.append(f"- Semana del {w['label']}: " + " | ".join(dias))
    parts.append(_block("Calendario de las últimas 4 semanas", cal_lines))

    # ─── Récords ───
    parts.append(_block("Récords de la ventana descargada", [
        f"- {r['label']}: {r['value']} ({r['name']}, {r['date']})"
        for r in an.get("records", [])
    ]))

    # ─── Predicciones ───
    parts.append(_block("Predicción de carreras (desde VO₂max)", [
        f"- {p['distance']}: {p['time']} ({p['pace']})"
        for p in metrics.get("race_predictions", [])
    ]))

    # ─── Últimas actividades ───
    acts = []
    for a in activities[:max_activities]:
        bits = [f"{a.get('date')} {a.get('sport_type') or a.get('sport')}",
                f'"{a.get("name", "")}"',
                f"{a.get('distance')} km", a.get("time")]
        if a.get("pace"):
            bits.append(f"{a['pace']}/km")
        if a.get("avg_speed"):
            bits.append(a["avg_speed"])
        if a.get("elevation"):
            bits.append(f"{a['elevation']} m D+")
        if a.get("avg_hr"):
            bits.append(f"FC {round(a['avg_hr'])}")
        if a.get("avg_watts"):
            bits.append(f"{round(a['avg_watts'])} W")
        if a.get("effort"):
            bits.append(f"RE {a['effort']}")
        acts.append("- " + " · ".join(str(b) for b in bits if b))
    parts.append(_block(f"Últimas {len(acts)} actividades (reciente→antigua)", acts))

    # ─── Material ───
    parts.append(_block("Material", [
        f"- {g['name']} ({g['type']}): {g['distance_km']} km"
        for g in strava.get("gear", [])
    ]))

    return "\n".join(p for p in parts if p)


def _zones_text(zones: dict) -> str:
    hr = (zones or {}).get("heart_rate") or (zones or {}).get("heartrate")
    if not hr:
        return ""
    return " / ".join(f"Z{i + 1} {z['min']}-{z['max']}" for i, z in enumerate(hr))


def _sleep_phases(sleep: dict) -> str:
    keys = [("deep_min", "profundo"), ("light_min", "ligero"),
            ("rem_min", "REM"), ("awake_min", "despierto")]
    bits = [f"{label} {sleep.get(k)} min" for k, label in keys if sleep.get(k)]
    return ", ".join(bits)


def _week_series(rows: list, label_key: str, value_key: str, unit: str = "") -> str:
    if not rows:
        return ""
    bits = [f"{r.get(label_key)} {r.get(value_key)}{unit}"
            for r in rows if r.get(value_key) not in (None, "")]
    return ", ".join(bits)
