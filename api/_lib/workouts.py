"""¿Ya hiciste el entreno programado?

Se marca como hecho si ese día hay una actividad del mismo deporte, mirando
dos fuentes: el calendario de Garmin (al hacer el entreno aparece ahí como
actividad; lo marca get_scheduled_workouts) y Strava, que además da la
distancia y el tiempo. Cada actividad cuenta para un solo entreno.
"""


def family(key):
    """Agrupa los nombres de deporte de Garmin y Strava: 'trail_running',
    'TrailRun' y 'running' son todos correr."""
    k = (key or "").lower().replace("_", "").replace(" ", "")
    if "run" in k:
        return "run"
    if any(x in k for x in ("cycl", "ride", "bik")):
        return "ride"
    if "swim" in k:
        return "swim"
    if any(x in k for x in ("walk", "hik")):
        return "walk"
    if any(x in k for x in ("strength", "weight", "crossfit", "hiit")):
        return "strength"
    return ""


def _same_sport(a, b):
    # Si una de las dos no dice el deporte, vale cualquier actividad del día
    return not a or not b or a == b


def mark_done(workouts, activities):
    """Devuelve copias de los entrenos con `done` y, si lo hay, `done_activity`
    (nombre, km y tiempo de la actividad de Strava que lo cumple)."""
    used = set()
    out = []
    for w in workouts or []:
        w = dict(w)
        fam = family(w.get("sport_key") or w.get("sport"))
        for a in activities or []:
            if a.get("id") in used or a.get("date") != w.get("date"):
                continue
            if not _same_sport(fam, family(a.get("sport_type") or a.get("sport"))):
                continue
            used.add(a.get("id"))
            w["done"] = True
            w["done_activity"] = {"id": a.get("id"),
                                  "name": a.get("name") or "",
                                  "distance": a.get("distance") or 0,
                                  "time": a.get("time") or ""}
            break
        out.append(w)
    return out


def attach_compliance(workouts, load):
    """Añade la valoración ya calculada (si la hay) a los entrenos hechos.
    Solo lee lo guardado: calcularla pide las vueltas a Strava."""
    from .compliance import cache_key
    for w in workouts:
        aid = (w.get("done_activity") or {}).get("id")
        if w.get("done") and aid:
            try:
                c = load(cache_key(aid, w))
            except Exception:
                c = None
            if c:
                w["compliance"] = c
    return workouts
