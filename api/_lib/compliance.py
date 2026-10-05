"""¿Hiciste lo que pedía el entreno?

Con un entreno estructurado, el reloj graba una vuelta por paso (calentamiento,
cada serie, cada recuperación...). Strava recibe esas mismas vueltas, así que
se pueden emparejar 1:1 con los pasos del plan y mirar en cada una:

- la duración o distancia (¿recortaste o te pasaste?),
- el objetivo: ritmo, FC (por zona o en ppm), velocidad o potencia.

Con eso sale una nota de 0 a 100 y unas frases de entrenador. Si las vueltas no
cuadran con los pasos (saltaste pasos, pulsaste vuelta de más...), se compara
solo el total.
"""
import hashlib

EASY = {"warmup": "calentamiento", "recovery": "recuperaciones",
        "rest": "descansos", "cooldown": "vuelta a la calma"}
POINTS = {"ok": 1.0, "warn": 0.5, "bad": 0.0}


def cache_key(activity_id, workout):
    """Las vueltas de una actividad no cambian: el resultado se guarda para siempre."""
    tag = hashlib.sha1(f"{workout.get('date')}|{workout.get('title')}".encode()).hexdigest()[:10]
    return f"compliance:v1:{activity_id}:{tag}"


# ─── Formatos ───

def _mmss(sec):
    sec = int(round(sec or 0))
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _km(m):
    km = (m or 0) / 1000
    return (f"{km:.2f}".rstrip("0").rstrip(".") if km < 10 else f"{km:.1f}").replace(".", ",") + " km"


def _pace(sec_km):
    return f"{int(sec_km // 60)}:{int(round(sec_km % 60)):02d}" if sec_km else "—"


# ─── Pasos ───

def flatten(steps):
    """Despliega las repeticiones: 6×(serie + recuperación) → 12 pasos."""
    out = []
    for st in steps or []:
        if "repeat" in st:
            inner = flatten(st.get("steps"))
            for i in range(int(st.get("repeat") or 1)):
                out.extend(dict(x, rep=i + 1, reps=st["repeat"]) for x in inner)
        else:
            out.append(st)
    return out


def align(flat, laps):
    """Empareja pasos y vueltas; None si no cuadran."""
    laps = list(laps or [])
    # Al parar el reloj suele quedar una vuelta de unos segundos al final
    while len(laps) > len(flat) and laps and (laps[-1]["elapsed"] < 60 or laps[-1]["distance"] < 150):
        laps.pop()
    if not flat or len(laps) != len(flat):
        return None
    return list(zip(flat, laps))


def _zone_bounds(zone, hr_zones):
    if not hr_zones or not 1 <= zone <= len(hr_zones):
        return None
    z = hr_zones[zone - 1]
    hi = z.get("max")
    return z.get("min") or 0, hi if hi and hi > 0 else 250


def _range_check(value, lo, hi, tol):
    """ok dentro del rango (con tolerancia relativa), warn si se sale poco, bad si mucho."""
    if value < lo * (1 - tol):
        return ("warn" if (lo - value) / lo <= 0.05 else "bad"), "baja"
    if value > hi * (1 + tol):
        return ("warn" if (value - hi) / hi <= 0.05 else "bad"), "alta"
    return "ok", ""


def evaluate_step(step, lap, hr_zones=None):
    checks = []          # (estado, qué, sentido)
    end = step.get("end")
    if end and end.get("value"):
        done = lap["elapsed"] if end["type"] == "time" else lap["distance"]
        ratio = done / end["value"]
        status = "ok" if abs(ratio - 1) <= 0.10 else "warn" if abs(ratio - 1) <= 0.20 else "bad"
        checks.append((status, "duración", "corto" if ratio < 1 else "largo"))

    goal = step.get("goal") or {}
    pace = lap["moving"] / (lap["distance"] / 1000) if lap["distance"] > 50 and lap["moving"] else None
    hit = None
    if goal.get("type") == "pace" and pace:
        # Ritmo: menos segundos = más rápido
        if pace < goal["fast"] * 0.98:
            dev = (goal["fast"] - pace) / goal["fast"]
            checks.append(("warn" if dev <= 0.05 else "bad", "ritmo", "rápido"))
        elif pace > goal["slow"] * 1.02:
            dev = (pace - goal["slow"]) / goal["slow"]
            checks.append(("warn" if dev <= 0.05 else "bad", "ritmo", "lento"))
        else:
            checks.append(("ok", "ritmo", ""))
    elif goal.get("type") in ("hr_zone", "hr") and lap.get("hr"):
        bounds = (_zone_bounds(goal["zone"], hr_zones) if goal["type"] == "hr_zone"
                  else (goal["lo"], goal["hi"]))
        if bounds:
            lo, hi = bounds
            if lap["hr"] < lo:
                checks.append(("warn" if lo - lap["hr"] <= 5 else "bad", "FC", "baja"))
            elif lap["hr"] > hi:
                checks.append(("warn" if lap["hr"] - hi <= 5 else "bad", "FC", "alta"))
            else:
                checks.append(("ok", "FC", ""))
            hit = (lo, hi)
    elif goal.get("type") == "speed" and lap["moving"]:
        kmh = lap["distance"] / lap["moving"] * 3.6
        st, sense = _range_check(kmh, goal["lo"], goal["hi"], 0.02)
        checks.append((st, "velocidad", sense))
    elif goal.get("type") == "power" and lap.get("watts"):
        st, sense = _range_check(lap["watts"], goal["lo"], goal["hi"], 0.03)
        checks.append((st, "potencia", sense))

    order = ["ok", "warn", "bad"]
    status = max((c[0] for c in checks), key=order.index) if checks else None
    issues = [f"{what} {sense}".strip() for st, what, sense in checks if st != "ok"]

    done = [_mmss(lap["elapsed"])]
    if lap["distance"] > 50:
        done.append(_km(lap["distance"]))
    if pace and goal.get("type") != "speed":
        done.append(f"{_pace(pace)}/km")
    if lap.get("hr"):
        done.append(f"{lap['hr']} ppm")

    return {
        "label": step.get("label") + (f" {step['rep']}/{step['reps']}" if step.get("rep") else ""),
        "type": step.get("type"),
        "planned": " · ".join(x for x in [step.get("duration"), step.get("target")] if x) or "libre",
        "done": " · ".join(done),
        "status": status,
        # La nota del paso es la media de sus criterios (la intensidad pesa el
        # doble que la duración: es lo que define la sesión); el icono, el peor
        "points": (sum(POINTS[c[0]] * (1 if c[1] == "duración" else 2) for c in checks)
                   / sum(1 if c[1] == "duración" else 2 for c in checks)) if checks else None,
        "issues": issues,
        "pace": pace,
        "hr": lap.get("hr") or 0,
        "hr_bounds": hit,
        "goal": goal,
        "short": any(w == "duración" and s == "corto" and st == "bad" for st, w, s in checks),
    }


# ─── Valoración ───

def _verdict(score):
    if score >= 85:
        return "Clavado: hiciste lo que pedía el plan."
    if score >= 65:
        return "Bien en general, con algún detalle que pulir."
    if score >= 40:
        return "A medias: varias partes se salieron de lo previsto."
    return "No salió como estaba planteado."


def _coach_notes(rows):
    notes = []
    work = [r for r in rows if r["type"] == "interval" and r["goal"].get("type") == "pace" and r["pace"]]
    if work:
        avg = sum(r["pace"] for r in work) / len(work)
        g = work[0]["goal"]
        rango = f"{_pace(g['fast'])}–{_pace(g['slow'])}"
        n_fast = sum("ritmo rápido" in r["issues"] for r in work)
        n_slow = sum("ritmo lento" in r["issues"] for r in work)
        if n_fast > len(work) / 2:
            notes.append(f"Las series fueron rápidas: media {_pace(avg)}/km para un objetivo de "
                         f"{rango}. Ir por encima del ritmo no suma más: cambia el estímulo de "
                         "la sesión y cuesta más recuperar.")
        elif n_slow > len(work) / 2:
            notes.append(f"Las series se quedaron lentas: media {_pace(avg)}/km frente a {rango}. "
                         "Si te costó más de lo normal, puede ser fatiga: mira sueño y HRV antes "
                         "del próximo entreno duro.")
        else:
            notes.append(f"Series en su ritmo (media {_pace(avg)}/km para {rango}): justo lo que tocaba.")
        if len(work) >= 3:
            first, last = work[0]["pace"], work[-1]["pace"]
            if last > first * 1.03:
                notes.append(f"Fuiste perdiendo ritmo: de {_pace(first)} en la primera serie a "
                             f"{_pace(last)} en la última. Mejor empezar un pelín más contenido.")
            elif last < first * 0.97:
                notes.append(f"Acabaste más rápido de lo que empezaste ({_pace(first)} → "
                             f"{_pace(last)}): bien si fue controlado.")

    # Lo suave, ¿fue suave?
    hot = []
    for kind, name in EASY.items():
        rs = [r for r in rows if r["type"] == kind and "FC alta" in r["issues"] and r["hr_bounds"]]
        if rs:
            hot.append((name, round(sum(r["hr"] for r in rs) / len(rs)), rs[0]["hr_bounds"][1]))
    if hot:
        partes = [f"{name} a {hr} ppm" for name, hr, _ in hot]
        lista = partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]
        notes.append(f"Lo suave no fue suave: {lista}, con techo en {hot[0][2]}. "
                     "Así llegas cansado a lo importante: en lo fácil, más fácil.")

    # Rodajes por zona de FC (Base, Larga...)
    steady = [r for r in rows if r["type"] not in EASY and r["goal"].get("type") in ("hr_zone", "hr")
              and r["hr_bounds"]]
    if steady and not work:
        high = [r for r in steady if "FC alta" in r["issues"]]
        if high:
            hr = round(sum(r["hr"] for r in high) / len(high))
            notes.append(f"Te saliste de la zona por arriba: FC media {hr} ppm con techo en "
                         f"{high[0]['hr_bounds'][1]}. Un rodaje de base tiene que sentirse fácil; "
                         "si hace falta, baja el ritmo o camina en las cuestas.")
        elif all(r["status"] == "ok" for r in steady):
            notes.append("FC dentro de la zona todo el rato: rodaje bien controlado.")

    for r in rows:
        if r["short"]:
            notes.append(f"Recortaste {r['label'].lower()} ({r['done'].split(' · ')[0]} de {r['planned'].split(' · ')[0]}).")
            break
    return notes


def compare(workout, activity, laps, hr_zones=None):
    """Compara el entreno programado con la actividad hecha (y sus vueltas)."""
    flat = flatten(workout.get("steps"))
    pairs = align(flat, laps)
    total_time = sum(l["elapsed"] for l in laps or []) or activity.get("moving_time_sec") or 0
    total_dist = sum(l["distance"] for l in laps or []) or (activity.get("distance") or 0) * 1000

    out = {"title": workout.get("title"), "date": workout.get("date"),
           "activity": activity.get("name") or "", "aligned": bool(pairs), "steps": []}

    if pairs:
        rows = [evaluate_step(s, l, hr_zones) for s, l in pairs]
        # Las series pesan el doble: son lo que define la sesión
        graded = [(r, 2 if r["type"] == "interval" else 1) for r in rows if r["points"] is not None]
        weight = sum(w for _, w in graded)
        score = round(100 * sum(r["points"] * w for r, w in graded) / weight) if weight else None
        notes = _coach_notes(rows)
        out["steps"] = [{k: r[k] for k in ("label", "planned", "done", "status", "issues")} for r in rows]
    else:
        score, notes = _totals(workout, total_time, total_dist, flat, laps)

    out["score"] = score
    out["verdict"] = _verdict(score) if score is not None else "Hecho, pero sin objetivos con los que comparar."
    out["notes"] = notes
    out["summary"] = _summary_text(out)
    return out


def _totals(workout, total_time, total_dist, flat, laps):
    """Sin emparejar paso a paso: solo duración y distancia totales."""
    notes, pts = [], []
    if flat and laps:
        notes.append(f"No pude emparejar las vueltas ({len(laps)}) con los pasos del plan "
                     f"({len(flat)}): ¿saltaste pasos o pulsaste vuelta a mano? Comparo solo el total.")
    plan_t, plan_d = workout.get("duration_sec"), workout.get("distance_m")
    for planned, done, what, fmt in ((plan_t, total_time, "Duración", _mmss),
                                     (plan_d, total_dist, "Distancia", _km)):
        if not planned or not done:
            continue
        ratio = done / planned
        st = "ok" if abs(ratio - 1) <= 0.10 else "warn" if abs(ratio - 1) <= 0.20 else "bad"
        pts.append(POINTS[st])
        if st == "ok":
            notes.append(f"{what}: {fmt(done)} para {fmt(planned)} previstos. Bien.")
        else:
            notes.append(f"{what}: {fmt(done)} para {fmt(planned)} previstos "
                         f"({'te quedaste corto' if ratio < 1 else 'te pasaste'}).")
    score = round(100 * sum(pts) / len(pts)) if pts else None
    return score, notes


def _summary_text(c):
    """Texto plano para pasárselo al entrenador (chat o informe)."""
    lines = [f"Entreno «{c['title']}» ({c['date']}) frente a lo hecho («{c['activity']}»): "
             + (f"{c['score']}/100. " if c["score"] is not None else "") + c["verdict"]]
    lines += [f"- {n}" for n in c["notes"]]
    for s in c["steps"]:
        mark = {"ok": "✓", "warn": "≈", "bad": "✗"}.get(s["status"], "·")
        lines.append(f"  {mark} {s['label']}: pedido {s['planned']} → hecho {s['done']}"
                     + (f" ({', '.join(s['issues'])})" if s["issues"] else ""))
    return "\n".join(lines)
