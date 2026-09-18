"""
Calculador de Métricas Derivadas
CTL/ATL/TSB, Ratio Agudo:Crónico, Predicciones de carrera, Training Readiness.
"""

import math
from datetime import datetime, timedelta


def current_body_battery(garmin_data: dict) -> int:
    """Body Battery de ahora mismo: el resumen diario y, si no, el último punto
    de la curva del día. Nunca el máximo, que al despertarte es casi siempre 100."""
    daily = garmin_data.get("daily") or {}
    value = daily.get("body_battery_current") or 0
    if not value:
        timeline = garmin_data.get("body_battery") or []
        if timeline:
            value = timeline[-1].get("battery") or 0
    return int(value or 0)


def calculate_fitness_fatigue_form(activities: list, max_history_days: int = 400) -> dict:
    """
    Calcula CTL (Fitness), ATL (Fatiga), TSB (Forma) usando
    los valores de Relative Effort (suffer_score) de Strava.

    CTL = media exponencial ponderada de 42 días
    ATL = media exponencial ponderada de 7 días
    TSB = CTL - ATL

    La simulación arranca en la actividad más antigua disponible (con tope de
    max_history_days) y siembra ambas medias con la carga media de las dos
    primeras semanas. Antes arrancaba 56 días atrás con un CTL fijo de 20: como
    el CTL tarda ~42 días en olvidar de dónde parte, ese 20 seguía pesando un
    26% en el valor final, infravaloraba el Fitness y hundía la Forma.
    """
    if not activities:
        return {"timeline": [], "current": {"ctl": 0, "atl": 0, "tsb": 0}}

    # Crear mapa de carga diaria
    today = datetime.now().date()

    daily_load = {}
    for a in activities:
        try:
            date = datetime.fromisoformat(a["date"]).date()
        except (ValueError, KeyError):
            continue
        if date > today:
            continue
        effort = a.get("effort", 0) or 0
        daily_load[date] = daily_load.get(date, 0) + effort

    if not daily_load:
        return {"timeline": [], "current": {"ctl": 0, "atl": 0, "tsb": 0}}

    start_date = max(min(daily_load), today - timedelta(days=max_history_days))
    history_days = (today - start_date).days + 1

    # Semilla: carga media diaria de las dos primeras semanas que conocemos.
    # Representa el entrenamiento que ya arrastrabas antes de los datos.
    seed_days = min(14, history_days)
    seed = sum(
        daily_load.get(start_date + timedelta(days=i), 0) for i in range(seed_days)
    ) / seed_days

    # Calcular CTL/ATL/TSB día a día
    ctl = float(seed)
    atl = float(seed)
    timeline = []

    current_date = start_date
    while current_date <= today:
        load = daily_load.get(current_date, 0)
        ctl = ctl + (load - ctl) / 42
        atl = atl + (load - atl) / 7
        tsb = ctl - atl

        timeline.append({
            "date": current_date.isoformat(),
            "ctl": round(ctl, 1),
            "atl": round(atl, 1),
            "tsb": round(tsb, 1),
            "load": load,
        })
        current_date += timedelta(days=1)

    current = timeline[-1] if timeline else {"ctl": 0, "atl": 0, "tsb": 0}

    # Interpretar forma
    tsb_val = current["tsb"]
    if tsb_val > 15:
        status = "desentrenado"
        emoji = "📉"
        advice = "Llevas mucho tiempo sin carga — vuelve progresivamente"
    elif tsb_val > 5:
        status = "descansado"
        emoji = "🟢"
        advice = "Buen momento para competir o hacer un test"
    elif tsb_val > -5:
        status = "equilibrado"
        emoji = "🟡"
        advice = "Puedes entrenar con normalidad"
    elif tsb_val > -15:
        status = "cargando"
        emoji = "🔶"
        advice = "Acumulando fatiga — vigila la recuperación"
    else:
        status = "fatigado"
        emoji = "🔴"
        advice = "Considera descanso activo o descarga"

    return {
        "timeline": timeline[-28:],  # Últimos 28 días
        "current": {
            "ctl": current["ctl"],
            "atl": current["atl"],
            "tsb": current["tsb"],
            "status": status,
            "emoji": emoji,
            "advice": advice,
            # Con menos de 42 días de historial el CTL aún no ha convergido:
            # el Fitness (y por tanto la Forma) hay que cogerlos con pinzas.
            "history_days": history_days,
            "warmup": history_days < 42,
        },
    }


def calculate_acwr(activities: list) -> dict:
    """
    Ratio Agudo:Crónico (Acute:Chronic Workload Ratio).

    Trabaja con VENTANAS MÓVILES de 7 días que terminan hoy, no con semanas
    naturales de lunes a domingo: aguda = hoy-6→hoy, crónica = media de los
    últimos 28 días. Es lo correcto para el ACWR (siempre 7 días completos),
    pero NO es el mismo número que la barra de la gráfica «Volumen por
    semana», que va de lunes a hoy y está a medias hasta el domingo.

    Esa diferencia es la que hacía que la misma carga apareciese como 202 en
    la gráfica y como 400 en el informe. Ahora la salida dice explícitamente
    qué ventana cubre cada valor para que no se puedan confundir.

    Zona segura: 0.8 — 1.3. Riesgo: > 1.5.
    """
    today = datetime.now().date()

    def window_load(days_back_start, days_back_end):
        """Carga en la ventana [days_back_end, days_back_start) días atrás."""
        total = 0
        for a in activities:
            try:
                date = datetime.fromisoformat(a["date"]).date()
            except (ValueError, KeyError):
                continue
            days_ago = (today - date).days
            if days_back_end <= days_ago < days_back_start:
                total += a.get("effort", 0) or 0
        return total

    w1 = window_load(7, 0)       # hoy-6  → hoy
    w2 = window_load(14, 7)      # hoy-13 → hoy-7
    w3 = window_load(21, 14)
    w4 = window_load(28, 21)
    acute = w1
    chronic = (w1 + w2 + w3 + w4) / 4

    ratio = round(acute / chronic, 2) if chronic > 0 else 0

    if ratio > 1.5:
        risk = "alto"
        emoji = "⚠️"
        color = "red"
    elif ratio > 1.3:
        risk = "atención"
        emoji = "⚡"
        color = "orange"
    elif ratio >= 0.8:
        risk = "óptimo"
        emoji = "✅"
        color = "green"
    else:
        risk = "bajo"
        emoji = "📉"
        color = "blue"

    def _range(days_back_start, days_back_end):
        ini = today - timedelta(days=days_back_start - 1)
        fin = today - timedelta(days=days_back_end)
        return f"{ini.isoformat()}→{fin.isoformat()}"

    return {
        "ratio": ratio,
        "acute_load": acute,
        "acute_days": 7,
        "chronic_load": round(chronic),
        "chronic_days": 28,
        "risk": risk,
        "emoji": emoji,
        "color": color,
        # Ventanas móviles de 7 días, de la más antigua a la más reciente.
        # Ojo: NO son semanas de lunes a domingo (ver docstring).
        "weekly_loads": [w4, w3, w2, w1],
        "window": "rolling_7d",
        "rolling_loads": [
            {"load": w4, "label": "día -28 a -22", "range": _range(28, 21)},
            {"load": w3, "label": "día -21 a -15", "range": _range(21, 14)},
            {"load": w2, "label": "día -14 a -8", "range": _range(14, 7)},
            {"load": w1, "label": "últimos 7 días", "range": _range(7, 0)},
        ],
    }


def predict_race_times(vo2max: float, best_5k_seconds: int = None) -> list:
    """
    Predice tiempos de carrera desde VO2max usando las tablas de Daniels.
    Si se proporciona un 5K real, ajusta las predicciones.
    """
    if not vo2max or vo2max < 20:
        return []

    # Fórmula de Daniels simplificada: v = VO2max * factor
    # Ajustada con el 5K real si está disponible
    predictions = []

    # Factores de velocidad relativa al VO2max para cada distancia
    # y duración típica (minutos) para calcular el decaimiento
    distances = [
        {"name": "1K", "km": 1, "factor": 1.06},
        {"name": "5K", "km": 5, "factor": 0.97},
        {"name": "10K", "km": 10, "factor": 0.93},
        {"name": "Media Maratón", "km": 21.0975, "factor": 0.87},
        {"name": "Maratón", "km": 42.195, "factor": 0.82},
    ]

    # Velocidad base desde VO2max (km/h aprox)
    # VO2max ≈ velocidad_km/h * 3.5 (simplificado)
    base_speed = vo2max / 3.5  # km/h a VO2max

    # Si tenemos 5K real, calibrar
    if best_5k_seconds and best_5k_seconds > 0:
        real_5k_speed = 5 / (best_5k_seconds / 3600)  # km/h
        calibration = real_5k_speed / (base_speed * 0.97)
    else:
        calibration = 1.0

    for d in distances:
        speed = base_speed * d["factor"] * calibration  # km/h
        time_hours = d["km"] / speed
        time_seconds = int(time_hours * 3600)

        hrs = time_seconds // 3600
        mins = (time_seconds % 3600) // 60
        secs = time_seconds % 60

        if hrs > 0:
            time_fmt = f"{hrs}:{mins:02d}:{secs:02d}"
        else:
            time_fmt = f"{mins}:{secs:02d}"

        pace_sec_per_km = time_seconds / d["km"]
        pace_fmt = f"{int(pace_sec_per_km // 60)}:{int(pace_sec_per_km % 60):02d}/km"

        predictions.append({
            "distance": d["name"],
            "km": d["km"],
            "time": time_fmt,
            "time_seconds": time_seconds,
            "pace": pace_fmt,
        })

    return predictions


def calculate_training_readiness(
    sleep_score: int,
    hrv: int,
    body_battery: int,
    atl: float,
    resting_hr: int = 0,
    resting_hr_baseline: int = 0,
) -> dict:
    """
    Training Readiness — score compuesto (0-100).
    Ponderación: Sueño 30%, HRV 25%, Body Battery 25%, Carga 20%.
    Bonus/penalización por FC reposo vs baseline.
    """
    # Normalizar HRV a 0-100 (asumiendo rango típico 20-100ms)
    hrv_norm = min(100, max(0, (hrv - 20) * 100 / 80))

    # Penalización por carga reciente (ATL alta = más fatiga)
    load_score = max(0, 100 - atl * 1.5)

    # Score base
    readiness = (
        sleep_score * 0.30 +
        hrv_norm * 0.25 +
        body_battery * 0.25 +
        load_score * 0.20
    )

    # Ajuste por FC reposo elevada vs baseline
    if resting_hr and resting_hr_baseline:
        hr_diff = resting_hr - resting_hr_baseline
        if hr_diff > 5:
            readiness -= 8  # FC significativamente elevada
        elif hr_diff > 3:
            readiness -= 4

    readiness = max(0, min(100, round(readiness)))

    # Recovery time estimado (basado en última carga)
    if atl > 50:
        recovery_hours = 48
    elif atl > 30:
        recovery_hours = 36
    elif atl > 15:
        recovery_hours = 24
    else:
        recovery_hours = 12

    if readiness >= 75:
        status = "Listo para entrenar fuerte"
        emoji = "🟢"
    elif readiness >= 55:
        status = "OK para entreno moderado"
        emoji = "🟡"
    elif readiness >= 35:
        status = "Entreno suave o descanso activo"
        emoji = "🟠"
    else:
        status = "Día de descanso recomendado"
        emoji = "🔴"

    return {
        "score": readiness,
        "status": status,
        "emoji": emoji,
        "recovery_hours": recovery_hours,
        "breakdown": {
            "sleep": {"value": sleep_score, "weight": 30},
            "hrv": {"value": round(hrv_norm), "weight": 25},
            "body_battery": {"value": body_battery, "weight": 25},
            "load": {"value": round(load_score), "weight": 20},
        },
    }


def calculate_training_summary(activities: list, days: int = 21) -> dict:
    """Resumen de entrenamiento de los últimos N días (hoy incluido)."""
    # days-1: con days=21 la ventana es hoy-20→hoy, 21 días. Antes cogía 22.
    cutoff = datetime.now().date() - timedelta(days=days - 1)

    recent = []
    for a in activities:
        try:
            date = datetime.fromisoformat(a["date"]).date()
        except (ValueError, KeyError):
            continue
        if cutoff <= date <= datetime.now().date():
            recent.append(a)

    total_km = sum(a.get("distance", 0) for a in recent)
    total_elev = sum(a.get("elevation", 0) for a in recent)
    total_cal = sum(a.get("calories", 0) for a in recent)
    total_time = sum(a.get("moving_time_sec", 0) for a in recent)

    by_sport = {}
    for a in recent:
        sport = a.get("sport", "Other")
        by_sport[sport] = by_sport.get(sport, 0) + a.get("distance", 0)

    return {
        "days": days,
        "count": len(recent),
        "total_km": round(total_km, 1),
        "total_elevation": total_elev,
        "total_calories": total_cal,
        "total_time_hours": round(total_time / 3600, 1),
        "by_sport": by_sport,
    }


def calculate_all(garmin_data: dict, strava_data: dict) -> dict:
    """Calcula todas las métricas derivadas."""
    activities = strava_data.get("activities", [])
    profile = strava_data.get("profile", {})
    daily = garmin_data.get("daily", {})
    sleep = garmin_data.get("sleep", {})
    hrv = garmin_data.get("hrv", {})

    # VO₂max — el del reloj manda. Garmin lo mide corriendo; la fórmula del
    # FTP es de ciclismo y daba un valor mucho más bajo (52 frente a 71), lo
    # que hundía todas las predicciones de carrera, que son de correr.
    training_status = garmin_data.get("training_status", {}) or {}
    ftp = profile.get("ftp")
    weight = profile.get("weight")

    vo2max_ftp = None
    if ftp and weight:
        # VO2max ≈ (FTP / weight) * 10.8 + 7 (fórmula aproximada ciclismo)
        vo2max_ftp = round((ftp / weight) * 10.8 + 7)

    vo2max_run = training_status.get("vo2max_running")
    vo2max = round(vo2max_run) if vo2max_run else vo2max_ftp
    vo2max_source = "garmin_running" if vo2max_run else ("ftp_estimate" if vo2max_ftp else None)

    # Fitness/Fatigue/Form
    fitness = calculate_fitness_fatigue_form(activities)

    # ACWR
    acwr = calculate_acwr(activities)

    # Race predictions
    best_5k = None
    for a in activities:
        if a.get("sport") == "Run" and a.get("distance", 0) >= 4.8:
            pace = a.get("pace")
            if pace:
                parts = pace.split(":")
                pace_sec = int(parts[0]) * 60 + int(parts[1])
                est_5k = pace_sec * 5
                if best_5k is None or est_5k < best_5k:
                    best_5k = est_5k

    races = predict_race_times(vo2max or 48, best_5k)

    # Training Readiness
    readiness = calculate_training_readiness(
        sleep_score=sleep.get("score", 70),
        hrv=hrv.get("last_night_avg", 60),
        # Body Battery de ahora, no el máximo del día: el máximo es ~100 nada
        # más levantarte y dejaba ese 25% del score clavado en el tope.
        body_battery=current_body_battery(garmin_data) or daily.get("body_battery_high", 70),
        atl=fitness["current"]["atl"],
        resting_hr=daily.get("resting_hr", 0),
        resting_hr_baseline=52,
    )

    # Training summary
    summary = calculate_training_summary(activities)

    return {
        "vo2max_estimated": vo2max,
        "vo2max_source": vo2max_source,
        "vo2max_running_garmin": vo2max_run,
        "vo2max_from_ftp": vo2max_ftp,
        "garmin_training_status": training_status,
        "fitness": fitness,
        "acwr": acwr,
        "race_predictions": races,
        "readiness": readiness,
        "training_summary": summary,
    }
