"""Carreras populares de Galicia (calendario de Carreiras Galegas, FGA).

La web oficial es una app Angular: el listado no viene en el HTML, lo pide a
un buscador Meilisearch con una clave de solo búsqueda que publica en su
propio JavaScript. Aquí se hace la misma consulta una vez al día desde el
servidor. La clave y el índice NO están en el código: se configuran en
Vercel (decisión del dueño de la app):

  CARREIRAS_SEARCH_KEY    clave de búsqueda (obligatoria; sin ella, no hay carreras)
  CARREIRAS_SEARCH_INDEX  índice (por defecto "competitions")
  CARREIRAS_SEARCH_HOST   por defecto https://search.carreirasgalegas.com
  CARREIRAS_SEARCH_FILTER filtro Meilisearch opcional (p. ej. para solo futuras)

Los nombres de los campos de cada carrera no están documentados, así que
`normalize` prueba los nombres habituales y guarda en Redis qué claves trae
el primer resultado (`sample_keys`) para poder afinarlo.

Redis:
  races          {"items": [...], "fetched_at", "error", "sample_keys"}
  races_signed   {id: copia de la carrera}  las que marcaste como apuntado
  races_seen     {"ids": [...], "new": [...], "new_key": "..."}  para avisar
                 de las pruebas que aparecen entre una descarga y la siguiente
"""
import json
import os
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone

from _lib.cache import load, save
from _lib.tz import ahora, hoy, MADRID

KEY_RACES = "races"
KEY_SIGNED = "races_signed"
KEY_SEEN = "races_seen"
MAX_SEEN = 4000

TIPOS = ("Ruta", "Trail", "Cross", "Pista", "Infantil")
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def configured():
    return bool(os.getenv("CARREIRAS_SEARCH_KEY"))


# ─── Descarga ───

def _search(offset=0, limit=1000):
    host = (os.getenv("CARREIRAS_SEARCH_HOST") or "https://search.carreirasgalegas.com").rstrip("/")
    index = os.getenv("CARREIRAS_SEARCH_INDEX") or "competitions"
    body = {"q": "", "limit": limit, "offset": offset}
    if os.getenv("CARREIRAS_SEARCH_FILTER"):
        body["filter"] = os.getenv("CARREIRAS_SEARCH_FILTER")
    req = urllib.request.Request(
        f"{host}/indexes/{index}/search", data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": "Bearer " + os.environ["CARREIRAS_SEARCH_KEY"],
                 "Content-Type": "application/json", "User-Agent": "MiSalud/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def fetch_raw():
    hits, offset = [], 0
    while offset < 3000:
        page = _search(offset)
        got = page.get("hits") or []
        hits.extend(got)
        if len(got) < 1000:
            break
        offset += 1000
    return hits


# ─── Normalizar ───

def _first(d, *keys):
    """Primer valor no vacío entre varias claves; admite rutas «a.b»."""
    for k in keys:
        v = d
        for part in k.split("."):
            v = v.get(part) if isinstance(v, dict) else None
        if v not in (None, "", [], {}):
            return v
    return None


def _when(v):
    """Fecha (y hora si la trae) desde ISO, epoch (s o ms) o {seconds} de Firestore."""
    if v is None:
        return None, None
    if isinstance(v, dict):
        v = v.get("seconds") or v.get("_seconds") or v.get("date")
    try:
        if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
            n = float(v)
            dt = datetime.fromtimestamp(n / 1000 if n > 1e11 else n, tz=timezone.utc).astimezone(MADRID)
        else:
            s = str(v).strip().replace("Z", "+00:00")
            m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
            if m:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1))), None
            dt = datetime.fromisoformat(s[:25] if "T" in s else s[:10])
            if dt.tzinfo:
                dt = dt.astimezone(MADRID)
        t = dt.strftime("%H:%M") if (dt.hour, dt.minute) != (0, 0) else None
        return dt.date(), t
    except (ValueError, TypeError, OSError, OverflowError):
        return None, None


def _km_label(km):
    km = float(km)
    if abs(km - 42.195) < 0.3:
        return "Maratón"
    if abs(km - 21.0975) < 0.3:
        return "Media"
    return (f"{km:.1f}".rstrip("0").rstrip(".").replace(".", ",")) + "K"


def _distances(h, name):
    """Lista de km a partir de los campos de distancia o, si no hay, del nombre."""
    kms = []
    raw = _first(h, "distances", "distance", "distanceKm", "km", "races", "categories", "events")
    items = raw if isinstance(raw, list) else [raw] if raw is not None else []
    for it in items:
        if isinstance(it, dict):
            it = _first(it, "distance", "distanceKm", "km", "length", "meters", "name")
        if isinstance(it, (int, float)):
            kms.append(it / 1000 if it > 300 else it)
        elif isinstance(it, str):
            for num, unit in re.findall(r"(\d+(?:[.,]\d+)?)\s*(km|k|m)\b", it.lower()):
                n = float(num.replace(",", "."))
                kms.append(n / 1000 if unit == "m" and n > 50 else n)
    if not kms:
        low = (name or "").lower()
        if "media marat" in low or "medio marat" in low:
            kms.append(21.0975)
        elif "maratón" in low or "maraton" in low:
            kms.append(42.195)
        for num in re.findall(r"(\d+(?:[.,]\d+)?)\s*k(?:m)?\b", low):
            kms.append(float(num.replace(",", ".")))
    out = sorted({round(k, 3) for k in kms if 0.1 <= k <= 200}, reverse=True)
    return out[:4]


def _tipo(h, name):
    txt = " ".join(str(x) for x in [
        _first(h, "type", "modality", "discipline", "category", "sport", "competitionType"),
        name] if x).lower()
    if re.search(r"trail|monta[ñn]a|montaña|monte|serra|skyrace|ultra", txt):
        return "Trail"
    if re.search(r"\bcross\b|campo a trav", txt):
        return "Cross"
    if re.search(r"pista|stadium|estadio", txt):
        return "Pista"
    if re.search(r"escolar|infantil|menores|benxam|alev[ií]n|cativ", txt):
        return "Infantil"
    return "Ruta"


def normalize(h):
    name = _first(h, "name", "title", "nombre", "nome", "competitionName")
    d, t = _when(_first(h, "date", "startDate", "eventDate", "competitionDate", "start",
                        "dateStart", "fecha", "data", "day"))
    if not name or not d:
        return None
    t = t or _first(h, "time", "hour", "startTime", "hora")
    if isinstance(t, str):
        m = re.search(r"(\d{1,2})[:.h](\d{2})", t)
        t = f"{int(m.group(1)):02d}:{m.group(2)}" if m else None
    kms = _distances(h, name)
    rid = str(_first(h, "id", "_id", "objectID", "uid", "slug", "code") or f"{d}-{name}")
    deadline, _ = _when(_first(h, "enrollmentEndDate", "registrationEndDate", "enrollmentEnd",
                               "registrationEnd", "inscriptionEndDate", "closeDate", "endEnrollment"))
    url = _first(h, "url", "link", "web", "website")
    if not (isinstance(url, str) and url.startswith("http")):
        url = f"https://www.carreirasgalegas.com/events/{rid}"
    price = _first(h, "price", "fee", "prize", "precio", "cost")
    return {
        "id": rid,
        "name": str(name).strip(),
        "date": d.isoformat(),
        "time": t,
        "place": _first(h, "locality", "city", "town", "municipality", "location.name",
                        "location.locality", "place", "concello", "localidad"),
        "province": _first(h, "province", "state", "provincia", "location.province"),
        "km": kms,
        "dist": " · ".join(_km_label(k) for k in kms),
        "type": _tipo(h, name),
        "circuit": _first(h, "circuit.name", "circuitName", "circuit"),
        "deadline": deadline.isoformat() if deadline else None,
        "price": price if isinstance(price, (int, float, str)) else None,
        "start": _first(h, "startPlace", "meetingPoint", "address", "location.address"),
        "url": url,
    }


# ─── Novedades ───

def mark_new(items, seen):
    """Cruza la descarga con lo ya visto. La primera vez no avisa de nada
    (todo sería «nuevo»); después, lo que no estaba queda como nuevo hasta
    que se marque como visto."""
    ids_now = [r["id"] for r in items]
    if not seen or not seen.get("ids"):
        return {"ids": ids_now[-MAX_SEEN:], "new": [], "new_key": None}
    known = set(seen["ids"])
    fresh = [i for i in ids_now if i not in known]
    still = [i for i in seen.get("new") or [] if i in set(ids_now)]
    new = still + [i for i in fresh if i not in still]
    out = {"ids": (seen["ids"] + fresh)[-MAX_SEEN:], "new": new,
           "new_key": seen.get("new_key")}
    if fresh:
        out["new_key"] = ahora().isoformat()
    return out


def refresh():
    """Descarga, normaliza, guarda y actualiza las novedades. Devuelve un resumen."""
    if not configured():
        raise RuntimeError("Falta CARREIRAS_SEARCH_KEY en Vercel")
    hits = fetch_raw()
    today = hoy().isoformat()
    items, seen_ids = [], set()
    for h in hits:
        r = normalize(h) if isinstance(h, dict) else None
        if r and r["date"] >= today and r["id"] not in seen_ids:
            seen_ids.add(r["id"])
            items.append(r)
    items.sort(key=lambda r: (r["date"], r["time"] or "99", r["name"]))
    seen = mark_new(items, load(KEY_SEEN))
    save(KEY_SEEN, seen)
    save(KEY_RACES, {"items": items, "fetched_at": ahora().isoformat(), "error": None,
                     "total_hits": len(hits),
                     "sample_keys": sorted(hits[0].keys()) if hits and isinstance(hits[0], dict) else []})
    return {"races": len(items), "new": len(seen["new"])}


def mark_seen():
    seen = load(KEY_SEEN) or {}
    seen["new"] = []
    save(KEY_SEEN, seen)


def set_signed(rid, on, snapshot=None):
    signed = load(KEY_SIGNED) or {}
    if on:
        race = snapshot or next((r for r in (load(KEY_RACES) or {}).get("items") or []
                                 if r["id"] == rid), None)
        if not race:
            raise KeyError("Carrera no encontrada")
        signed[rid] = race
    else:
        signed.pop(rid, None)
    save(KEY_SIGNED, signed)
    return signed


# ─── Lectura para la app, el widget y el entrenador ───

def upcoming_signed(signed=None, days=None):
    today = hoy()
    out = []
    for r in (signed if signed is not None else load(KEY_SIGNED) or {}).values():
        try:
            d = date.fromisoformat(r["date"])
        except (KeyError, ValueError):
            continue
        if d >= today and (days is None or (d - today).days <= days):
            out.append(r)
    return sorted(out, key=lambda r: (r["date"], r.get("time") or ""))


def when_label(r):
    d = date.fromisoformat(r["date"])
    return f"{DIAS[d.weekday()]} {d.day}"


def payload():
    data = load(KEY_RACES) or {}
    signed = load(KEY_SIGNED) or {}
    seen = load(KEY_SEEN) or {}
    new = set(seen.get("new") or [])
    today = hoy().isoformat()
    items = [dict(r, is_new=r["id"] in new, signed=r["id"] in signed)
             for r in data.get("items") or [] if r["date"] >= today]
    listed = {r["id"] for r in items}
    # Apuntadas que ya no salen en el listado (la quitaron o cambió el id): se enseñan igual
    for r in upcoming_signed(signed):
        if r["id"] not in listed:
            items.append(dict(r, is_new=False, signed=True))
    items.sort(key=lambda r: (r["date"], r.get("time") or "99", r["name"]))
    return {"configured": configured(), "items": items, "fetched_at": data.get("fetched_at"),
            "error": data.get("error"), "new_count": sum(1 for r in items if r["is_new"]),
            "new_key": seen.get("new_key"), "sample_keys": data.get("sample_keys")}


def widget_info():
    """Lo que necesita el widget: la carrera apuntada de esta semana y las novedades."""
    p = payload()
    nxt = upcoming_signed(days=7)
    race = None
    if nxt:
        r = nxt[0]
        race = {"name": r["name"], "when": when_label(r), "time": r.get("time") or "",
                "dist": r.get("dist") or "", "place": r.get("place") or "",
                "days": (date.fromisoformat(r["date"]) - hoy()).days}
    news = [r for r in p["items"] if r["is_new"]]
    return race, {"count": len(news), "key": p["new_key"] or "",
                  "names": [f"{r['name']} ({when_label(r)})" for r in news[:3]]}


def coach_block():
    rows = upcoming_signed(days=90)
    if not rows:
        return ""
    lines = ["## Carreras en las que está apuntado"]
    for r in rows:
        d = date.fromisoformat(r["date"])
        extra = ", ".join(x for x in [r.get("dist"), r.get("place"), r.get("time")] if x)
        lines.append(f"- {DIAS[d.weekday()]} {d.isoformat()} (en {(d - hoy()).days} días): "
                     f"**{r['name']}**" + (f" ({extra})" if extra else ""))
    return "\n".join(lines)
