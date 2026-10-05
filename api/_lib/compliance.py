"""¿Hiciste lo que pedía el entreno?

Con un entreno estructurado, el reloj graba una vuelta por paso (calentamiento,
cada serie, cada recuperación...). Strava recibe esas mismas vueltas, así que
se pueden emparejar 1:1 con los pasos del plan y mirar en cada una:

- la duración o distancia (¿recortaste o te pasaste?),
- el objetivo: ritmo, FC (por zona o en ppm), velocidad o potencia.

Si las vueltas no cuadran con los pasos (lo normal con la vuelta automática
cada km), se corta la grabación segundo a segundo de Strava por los tiempos y
distancias de cada paso del plan, y se mide cada tramo. Así además se sabe qué
parte del tiempo estuviste dentro del rango, no solo la media. Solo si tampoco
hay grabación se compara el total.

Con eso sale una nota de 0 a 100 y unas frases de entrenador.
"""
import hashlib
from bisect import bisect_left

EASY = {"warmup": "calentamiento", "recovery": "recuperaciones",
        "rest": "descansos", "cooldown": "vuelta a la calma"}
POINTS = {"ok": 1.0, "warn": 0.5, "bad": 0.0}


def cache_key(activity_id, workout):
    """Las vueltas de una actividad no cambian: el resultado se guarda para siempre."""
    tag = hashlib.sha1(f"{workout.get('date')}|{workout.get('title')}".encode()).hexdigest()[:10]
    return f"compliance:v2:{activity_id}:{tag}"


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
    # Mismo número no basta: con la vuelta automática cada km puede coincidir
    # por casualidad. Cada vuelta tiene que parecerse a su paso.
    medidos = [(st["end"], lp) for st, lp in zip(flat, laps) if _has_end(st)]
    if medidos:
        parecidos = sum(0.6 <= (lp["elapsed"] if e["type"] == "time" else lp["distance"]) / e["value"] <= 1.4
                        for e, lp in medidos)
        if parecidos < 0.7 * len(medidos):
            return None
    return list(zip(flat, laps))


def _has_end(step):
    return bool(step.get("end") and step["end"].get("value"))


def segment(flat, streams):
    """Corta la grabación en un tramo por paso, según la duración o distancia
    de cada uno. Un paso «hasta pulsar vuelta» se queda con lo que sobra entre
    los de antes y los de después; con más de uno así no se puede: None."""
    t = (streams or {}).get("time") or []
    d = (streams or {}).get("distance") or []
    n = len(t)
    if n < 2 or not flat:
        return None
    if len(d) != n:
        d = None
    opens = [k for k, st in enumerate(flat) if not _has_end(st)]
    if len(opens) > 1:
        return None
    if any(st["end"]["type"] == "distance" for st in flat if _has_end(st)) and d is None:
        return None

    def arr(end):
        return t if end["type"] == "time" else d

    bounds = [None] * len(flat)
    stop = opens[0] if opens else len(flat)
    i = 0
    for k in range(stop):                      # hacia delante hasta el paso abierto
        end = flat[k]["end"]
        a = arr(end)
        j = bisect_left(a, a[i] + end["value"], i)
        bounds[k] = (i, min(j, n - 1), j >= n)
        i = min(j, n - 1)
    if opens:
        j = n - 1
        for k in range(len(flat) - 1, stop, -1):   # hacia atrás desde el final
            end = flat[k]["end"]
            a = arr(end)
            i0 = max(bisect_left(a, a[j] - end["value"], 0, j), i)
            bounds[k] = (i0, j, False)
            j = i0
        bounds[stop] = (i, max(i, j), False)
    return [_segment_stats(streams, i0, i1, cut) for i0, i1, cut in bounds]


def _segment_stats(st, i0, i1, truncated):
    t = st["time"]
    d = st.get("distance") or []
    mv = st.get("moving") or []
    hr = st.get("heartrate") or []
    w = st.get("watts") or []
    v = st.get("velocity_smooth") or []
    dts, moving, hrs, ws, vs = [], 0, [], [], []
    for k in range(i0 + 1, i1 + 1):
        dt = t[k] - t[k - 1]
        if dt <= 0 or dt > 30:          # huecos de pausa: no cuentan
            continue
        is_moving = mv[k] if k < len(mv) else True
        dts.append(dt)
        vs.append((v[k] if k < len(v) else None) if is_moving else None)
        hrs.append(hr[k] if k < len(hr) else None)
        ws.append(w[k] if k < len(w) else None)
        if is_moving:
            moving += dt

    def wmean(vals):
        num = sum(x * dt for x, dt in zip(vals, dts) if x)
        den = sum(dt for x, dt in zip(vals, dts) if x)
        return round(num / den) if den else 0

    return {
        "elapsed": t[i1] - t[i0],
        "moving": moving,
        "distance": (d[i1] - d[i0]) if d else 0,
        "hr": wmean(hrs),
        "watts": wmean(ws),
        "derived": True,
        "truncated": truncated,
        "samples": {"dt": dts, "v": vs, "hr": hrs},
    }


def _in_range(samples, key, lo, hi):
    """% del tiempo (en movimiento) dentro de [lo, hi]."""
    pares = [(x, dt) for x, dt in zip(samples[key], samples["dt"]) if x]
    total = sum(dt for _, dt in pares)
    if total < 30:
        return None
    return round(100 * sum(dt for x, dt in pares if lo <= x <= hi) / total)


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
    if lap.get("derived") and lap["elapsed"] < 5:
        # La actividad terminó antes de llegar a este paso
        return _skipped(step)
    # Con un tramo cortado por el plan la duración cuadra por construcción:
    # solo dice algo si la actividad se acabó antes de tiempo
    if end and end.get("value") and (not lap.get("derived") or lap.get("truncated")):
        done = lap["elapsed"] if end["type"] == "time" else lap["distance"]
        ratio = done / end["value"]
        status = "ok" if abs(ratio - 1) <= 0.10 else "warn" if abs(ratio - 1) <= 0.20 else "bad"
        checks.append((status, "duración", "corto" if ratio < 1 else "largo"))

    goal = step.get("goal") or {}
    pace = lap["moving"] / (lap["distance"] / 1000) if lap["distance"] > 50 and lap["moving"] else None
    hit = None
    samples = lap.get("samples")
    in_range = None
    if samples and goal.get("type") == "pace":
        # velocidad en m/s; el rango de ritmo con la misma tolerancia del 2 %
        in_range = _in_range(samples, "v", 1000 / (goal["slow"] * 1.02), 1000 / (goal["fast"] * 0.98))
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
            if samples:
                in_range = _in_range(samples, "hr", lo, hi)
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

    # Media buena pero ritmo a tirones (menos de la mitad del tiempo en rango)
    if in_range is not None and in_range < 50 and checks and checks[-1][0] == "ok" \
            and checks[-1][1] != "duración":
        checks[-1] = ("warn", checks[-1][1], "irregular")

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
    if in_range is not None:
        done.append(f"{in_range}% en rango")

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
        "in_range": in_range,
    }


def _skipped(step):
    return {
        "label": step.get("label") + (f" {step['rep']}/{step['reps']}" if step.get("rep") else ""),
        "type": step.get("type"),
        "planned": " · ".join(x for x in [step.get("duration"), step.get("target")] if x) or "libre",
        "done": "no llegaste a hacerlo",
        "status": "bad", "points": 0.0, "issues": ["no hecho"], "pace": None, "hr": 0,
        "hr_bounds": None, "goal": step.get("goal") or {}, "short": True, "in_range": None,
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
    if len(rows) == 1 and work:
        # Rodaje de un solo paso (los «Base» de Garmin Coach): ritmo medio y regularidad
        r, g = work[0], work[0]["goal"]
        rango = f"{_pace(g['fast'])}–{_pace(g['slow'])}"
        if "ritmo rápido" in r["issues"]:
            notes.append(f"Ritmo medio {_pace(r['pace'])}/km, más rápido que el objetivo ({rango}). "
                         "En un rodaje así, ir más rápido no suma: el objetivo es acumular "
                         "volumen fácil y llegar fresco a los días de calidad.")
        elif "ritmo lento" in r["issues"]:
            notes.append(f"Ritmo medio {_pace(r['pace'])}/km, más lento que el objetivo ({rango}). "
                         "Si fue por cuestas o calor, perfecto; si fue cansancio, tenlo en cuenta.")
        else:
            notes.append(f"Ritmo medio {_pace(r['pace'])}/km, dentro del objetivo ({rango}).")
        if r["in_range"] is not None:
            if r["in_range"] >= 80:
                notes.append(f"Muy regular: el {r['in_range']}% del tiempo dentro del rango.")
            elif r["in_range"] >= 50:
                notes.append(f"El {r['in_range']}% del tiempo dentro del rango: bien, con algún "
                             "tramo fuera (cuestas, cruces o cambios de ritmo).")
            else:
                notes.append(f"Solo el {r['in_range']}% del tiempo dentro del rango: la media cuadra "
                             "pero fuiste a tirones. Intenta un ritmo más constante.")
        work = []
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


def compare(workout, activity, laps, hr_zones=None, streams=None):
    """Compara el entreno programado con la actividad hecha: por vueltas si
    encajan con los pasos; si no, cortando la grabación por el plan."""
    flat = flatten(workout.get("steps"))
    if len(flat) == 1 and flat[0].get("type") == "interval":
        flat = [dict(flat[0], label="Carrera")]      # un rodaje no es «una serie»
    pairs = align(flat, laps)
    method = "laps" if pairs else None
    if not pairs and streams:
        segs = segment(flat, streams)
        if segs:
            pairs, method = list(zip(flat, segs)), "streams"
    total_time = sum(l["elapsed"] for l in laps or []) or activity.get("moving_time_sec") or 0
    total_dist = sum(l["distance"] for l in laps or []) or (activity.get("distance") or 0) * 1000

    out = {"title": workout.get("title"), "date": workout.get("date"),
           "activity": activity.get("name") or "", "aligned": bool(pairs),
           "method": method or "totals", "steps": []}

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
