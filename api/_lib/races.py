"""Carreras populares (Carreiras Galegas y CCNorte).

Las dos webs se leen con los scrapers de scripts/carreras/scrape.py, que
corren cada día en GitHub Actions (.github/workflows/carreras.yml) y publican
un carreras.json en la rama `datos` del repo. Aquí se descarga ese JSON, se
normalizan las carreras, se juntan las que salen en las dos webs y se
detectan las pruebas nuevas. Así el servidor no necesita navegador ni claves.

  CARRERAS_DATA_URL  de dónde leer el JSON (por defecto, la rama `datos`)
  CASA_LAT / CASA_LON / CASA_NOMBRE  desde dónde se mide la distancia a cada
                     carrera (por defecto, Noia)

Redis:
  races          {"items": [...], "fetched_at", "scraped_at", "sources", "error"}
  races_signed   {id: copia de la carrera}  las que marcaste como apuntado
  races_seen     {"ids": [...], "new": [...], "new_key": "..."}  para avisar
                 de las pruebas que aparecen entre una descarga y la siguiente
"""
import json
import math
import os
import re
import unicodedata
import urllib.request
from datetime import date

from _lib.cache import load, save
from _lib.tz import ahora, hoy

KEY_RACES = "races"
KEY_SIGNED = "races_signed"
KEY_SEEN = "races_seen"
MAX_SEEN = 4000
DATA_URL = "https://raw.githubusercontent.com/tonicastrof/mi-salud/datos/carreras.json"
CASA = (42.7849, -8.8877, "Noia")
FUENTES = {"carreirasgalegas": "Carreiras Galegas", "ccnorte": "CCNorte"}

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
# Palabras que van en minúscula al pasar los nombres (vienen EN MAYÚSCULAS)
MENORES = {"de", "do", "da", "dos", "das", "del", "la", "las", "los", "el", "e", "y", "o", "a",
           "en", "contra", "pola", "polo", "por", "con", "ao", "á", "ó", "no", "na", "nos", "nas"}


def configured():
    return True


# ─── Descarga ───

def fetch_data():
    url = os.getenv("CARRERAS_DATA_URL") or DATA_URL
    req = urllib.request.Request(url, headers={"User-Agent": "MiSalud/1.0", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


# ─── Normalizar ───

def bonito(nombre):
    """«XII CARREIRA POPULAR CONCELLO DE RIANXO» → «XII Carreira Popular Concello de Rianxo».
    Respeta números romanos, siglas cortas y lo que ya venga en minúsculas."""
    s = re.sub(r"\s+", " ", (nombre or "").strip())
    if not s or s != s.upper():
        return s
    out = []
    for i, w in enumerate(s.split(" ")):
        core = re.sub(r"[^\wÁÉÍÓÚÑÜ]", "", w, flags=re.U)
        if re.fullmatch(r"[IVXLCDM]+[ªº]?", core) or re.fullmatch(r"\d+\w*", core) or (core.isalpha() and len(core) <= 3 and core.lower() not in MENORES and not core.lower() in ("cto", "san", "sin")):
            out.append(w)
        elif i and core.lower() in MENORES and out[-1] not in ("-", "–", "—"):
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:].lower() if w[:1].isalpha() else w[:2].upper() + w[2:].lower())
    return " ".join(out)


def _km_label(km):
    km = float(km)
    if abs(km - 42.195) < 0.3:
        return "Maratón"
    if abs(km - 21.0975) < 0.3:
        return "Media"
    if abs(km - 1.609) < 0.05:
        return "Milla"
    return (f"{km:.1f}".rstrip("0").rstrip(".").replace(".", ",")) + "K"


def km_del_nombre(name):
    low = (name or "").lower()
    kms = []
    if re.search(r"medi[oa] marat", low):
        kms.append(21.0975)
    elif re.search(r"\bmarat[oó]n\b", low):
        kms.append(42.195)
    if re.search(r"\bmilla\b", low):
        kms.append(1.609)
    for num in re.findall(r"(\d+(?:[.,]\d+)?)\s*k(?:m|ms)?\b", low):
        kms.append(float(num.replace(",", ".")))
    return kms


def tipo(name):
    low = (name or "").lower()
    if re.search(r"trail|monta[ñn]a|skyrace|ultra\b", low):
        return "Trail"
    if re.search(r"\bcros+\b|campo a trav", low):
        return "Cross"
    if re.search(r"\bpista\b|\bmilla\b", low):
        return "Pista"
    if re.search(r"andaina|sendeirismo|camiñada", low) and not re.search(r"carreira|carrera", low):
        return "Andaina"
    if re.search(r"escolar|infantil|menores|benxam|alev[ií]n|cativ", low):
        return "Infantil"
    return "Ruta"


def normalize(it):
    """Una carrera del JSON del scraper → la forma que usa la app."""
    name, d = it.get("name"), it.get("date")
    try:
        date.fromisoformat(d or "")
    except ValueError:
        return None
    if not name:
        return None
    kms = sorted({round(float(k), 3) for k in (it.get("km") or km_del_nombre(name)) if 0.1 <= float(k) <= 200},
                 reverse=True)
    if kms and kms[0] >= 5:
        kms = [k for k in kms if k >= 3]      # fuera las categorías infantiles
    kms = kms[:4]
    region = re.sub(r"^\((.*)\)$", r"\1", it.get("region") or "").strip() or None
    place = it.get("place") or None
    if place and region and (place[:1].islower() or "/" in place):
        place = region      # la web puso la calle en el campo de la localidad
    return {
        "id": str(it.get("id") or f"{d}-{name}"),
        "name": bonito(name),
        "date": d,
        "time": it.get("time") or None,
        "place": place,
        "province": region,
        "km": kms,
        "dist": " · ".join(_km_label(k) for k in kms),
        "type": tipo(name),
        "circuit": bonito(it["circuit"]) if it.get("circuit") else None,
        "deadline": it.get("deadline") or None,
        "price": it.get("price") or None,
        "start": it.get("start") or None,
        "url": it.get("url"),
        "lat": it.get("lat"),
        "lon": it.get("lon"),
        "source": FUENTES.get(it.get("source"), it.get("source")),
    }


def _clave(name):
    """Nombre reducido para comparar entre webs: sin acentos, numerales ni palabras vacías."""
    t = unicodedata.normalize("NFD", (name or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    words = re.findall(r"[a-z0-9]+", t)
    vacias = MENORES | {"carreira", "carrera", "popular", "edicion", "edicion", "concello", "ayuntamiento"}
    return {w for w in words if w not in vacias and not re.fullmatch(r"[ivxlcdm]+", w) and len(w) > 2}


def merge(items):
    """Junta la misma carrera publicada en las dos webs (mismo día y nombre
    parecido): se queda la ficha de Carreiras Galegas y completa los huecos
    (distancias, hora, precio, plazo) con lo de CCNorte."""
    out = []
    for r in items:
        twin = None
        for o in out:
            if o["date"] != r["date"] or o["source"] == r["source"]:
                continue
            a, b = _clave(o["name"]), _clave(r["name"])
            if a and b and len(a & b) / min(len(a), len(b)) >= 0.6:
                twin = o
                break
        if not twin:
            out.append(dict(r))
            continue
        main, other = (twin, r) if twin["source"] == "Carreiras Galegas" else (r, twin)
        merged = dict(main)
        for k, v in other.items():
            if merged.get(k) in (None, "", []) and v not in (None, "", []):
                merged[k] = v
        merged["also"] = other["url"]
        out[out.index(twin)] = merged
    return out


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
    """Lee el JSON de los scrapers, normaliza, guarda y actualiza las novedades."""
    data = fetch_data()
    today = hoy().isoformat()
    items = [r for r in (normalize(it) for it in data.get("items") or [] if isinstance(it, dict))
             if r and r["date"] >= today]
    items = merge(sorted(items, key=lambda r: r["source"] != "Carreiras Galegas"))
    items.sort(key=lambda r: (r["date"], r["time"] or "99", r["name"]))
    seen = mark_new(items, load(KEY_SEEN))
    save(KEY_SEEN, seen)
    save(KEY_RACES, {"items": items, "fetched_at": ahora().isoformat(), "error": None,
                     "scraped_at": data.get("generated_at"), "sources": data.get("sources")})
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

def casa():
    try:
        return float(os.environ["CASA_LAT"]), float(os.environ["CASA_LON"]), os.getenv("CASA_NOMBRE") or "casa"
    except (KeyError, ValueError):
        return CASA


def km_desde(lat, lon, origen):
    """Distancia en línea recta (km) entre la carrera y casa; None si no tiene coordenadas."""
    if lat is None or lon is None:
        return None
    la1, lo1, la2, lo2 = map(math.radians, (origen[0], origen[1], float(lat), float(lon)))
    a = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return round(2 * 6371 * math.asin(math.sqrt(a)))


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
    origen = casa()
    items = [dict(r, is_new=r["id"] in new, signed=r["id"] in signed)
             for r in data.get("items") or [] if r["date"] >= today]
    listed = {r["id"] for r in items}
    # Apuntadas que ya no salen en el listado (la quitaron o cambió el id): se enseñan igual
    for r in upcoming_signed(signed):
        if r["id"] not in listed:
            items.append(dict(r, is_new=False, signed=True))
    for r in items:
        r["km_casa"] = km_desde(r.get("lat"), r.get("lon"), origen)
    items.sort(key=lambda r: (r["date"], r.get("time") or "99", r["name"]))
    return {"configured": bool(data), "items": items, "home": origen[2], "fetched_at": data.get("fetched_at"),
            "scraped_at": data.get("scraped_at"), "sources": data.get("sources"),
            "error": data.get("error"), "new_count": sum(1 for r in items if r["is_new"]),
            "new_key": seen.get("new_key")}


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
