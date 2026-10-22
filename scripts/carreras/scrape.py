"""Descarga el calendario de carreras y lo deja en un JSON para la app.

Lo ejecuta .github/workflows/carreras.yml una vez al día (o a mano con
«Run workflow») y publica el resultado en la rama `datos`; el servidor de la
app lo lee de ahí (api/_lib/races.py). Basado en los scrapers que ya usaba:

- Carreiras Galegas (www.carreirasgalegas.com/events): es una app Angular, así
  que se abre con un navegador sin ventana y se leen las tablas del
  calendario (fecha, nombre, lugar). De las próximas semanas se entra además
  en la ficha para sacar la hora y el circuito.
- CCNorte (ccnorte.com): HTML normal; de cada evento salen las categorías con
  su distancia, hora de salida, precio vigente y plazo de inscripción.

Uso:  python scripts/carreras/scrape.py salida.json
Requisitos: requests, beautifulsoup4, selenium (y Chrome, que ya traen los
runners de GitHub).
"""
import json
import re
import sys
import time
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
FGA = "https://www.carreirasgalegas.com"
CCN = "https://ccnorte.com/evento/index/dp/1"
DIAS_FICHA = 60          # de las carreras de los próximos 60 días se abre la ficha

MESES_GL = {"xan": 1, "feb": 2, "mar": 3, "abr": 4, "maio": 5, "mai": 5, "xuñ": 6, "xuño": 6,
            "xul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dec": 12}

GALICIA = ("lugo", "coruña", "ourense", "orense", "pontevedra", "vigo", "santiago", "ferrol",
           "galicia", "galiza", "vilagarcía", "ribeira", "narón", "oleiros", "cambre", "arteixo",
           "carballo", "boiro", "cangas", "marín", "redondela", "moaña", "tui", "o grove",
           "sanxenxo", "lalín", "monforte", "burela", "viveiro", "vilalba", "sarria", "chantada",
           "xinzo", "verín", "o barco", "carballiño", "celanova", "ribadavia")


def es_galicia(txt):
    t = (txt or "").lower()
    return any(k in t for k in GALICIA)


def fecha_gl(txt):
    """«8 de mar. de 2026» → date."""
    p = txt.replace(".", "").lower().split()
    try:
        return date(int(p[4]), MESES_GL[p[2]], int(p[0]))
    except (IndexError, KeyError, ValueError):
        return None


def metros(txt):
    """«10.000 m», «21,097 km», «5000 m» → metros (como en scraper_ccnorte.py)."""
    t = (txt or "").lower()
    m = re.search(r"[\d.,]+", t)
    if not m:
        return 0.0
    n = m.group()
    if "." in n and "," in n:
        n = n.replace(".", "").replace(",", ".")
    elif "." in n and len(n.split(".")[-1]) == 3:
        n = n.replace(".", "")
    elif "," in n:
        n = n.replace(",", "") if len(n.split(",")[-1]) == 3 else n.replace(",", ".")
    try:
        v = float(n)
    except ValueError:
        return 0.0
    return v * 1000 if "km" in t and v < 500 else v


HORA = re.compile(r"\b([01]?\d|2[0-3])\s*[:.h]\s*([0-5]\d)\b")
CLAVE_HORA = re.compile(r"sa[ií]da|salida|hora|comez|comienz|inicio|a partir d|dará comezo|darase", re.I)


def hora_y_salida(txt):
    """Hora y lugar de salida de la ficha de Carreiras Galegas. La hora se
    toma de la primera línea que hable de salida o comienzo (nunca de las
    de inscripción, que traen «ata as 23:59»)."""
    hora, lugar = None, None
    lines = txt.splitlines()
    for i, line in enumerate(lines):
        if re.search(r"inscri|ata as|hasta las|prazo|plazo", line, re.I):
            continue
        if hora is None and CLAVE_HORA.search(line):
            txt_h = line.split("/20")[-1] if re.search(r"\d{1,2}/\d{1,2}/20\d\d", line) else line
            # Ficha en formato «Saída» / «11:00»: la hora va en la línea siguiente
            if not HORA.search(txt_h) and len(line) < 40 and i + 1 < len(lines):
                txt_h = lines[i + 1]
            m = HORA.search(txt_h)
            if m and (m.group(1), m.group(2)) != ("0", "00"):
                hora = f"{int(m.group(1)):02d}:{m.group(2)}"
        if lugar is None:
            m = re.search(r"sa[ií]da(?:\s+e\s+(?:chegada|meta))?\s*[:,]?\s*(?:dar[aá]se\s+|ser[aá]\s+|estará\s+|situada\s+)?(?:(?:n[ao]s?|en|desde)\s+|(?<=:)\s*|(?<=: ))([^,\n]{3,60})", line, re.I)
            if m:
                cand = HORA.sub("", m.group(1)).strip(" .,:-")
                if re.search(r"[A-Za-zÁÉÍÓÚáéíóúñÑ]{3}", cand) and not re.search(r"^(ás|a las|horas?)\b", cand, re.I):
                    lugar = cand
    return hora, lugar


def distancias(txt):
    """Distancias que menciona la ficha («percorrido de 10 km», «8.000 metros»,
    «21,097 km»). Se saltan las líneas de precios e inscripción."""
    kms = set()
    for line in txt.splitlines():
        if re.search(r"inscri|prezo|precio|€|euros|aparcamento|parking", line, re.I):
            continue
        for num, unit in re.findall(r"(\d{1,3}(?:[.,]\d{1,3})?)\s*(km|kms|quil[oó]metros|kil[oó]metros|k)\b", line, re.I):
            v = float(num.replace(".", "").replace(",", ".")) if re.fullmatch(r"\d{1,3}\.\d{3}", num) else float(num.replace(",", "."))
            if 1 <= v <= 120:
                kms.add(round(v, 3))
        for num in re.findall(r"\b(\d{1,2}\.?\d{3})\s*(?:m|metros)\b", line, re.I):
            v = float(num.replace(".", "")) / 1000
            if 1 <= v <= 60:
                kms.add(round(v, 3))
    return sorted(kms, reverse=True)[:6]


# ─── Carreiras Galegas ───

def carreiras_galegas():
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    o = Options()
    for a in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1280,2000",
              f"--user-agent={UA}", "--lang=gl-ES"):
        o.add_argument(a)
    d = webdriver.Chrome(options=o)
    try:
        d.get(FGA + "/events")
        WebDriverWait(d, 40).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "tbody tr td a")))
        time.sleep(2)
        soup = BeautifulSoup(d.page_source, "html.parser")
        out, vistos = [], set()
        for tr in soup.select("tbody tr"):
            tds = tr.find_all("td")
            a = tds[1].find("a") if len(tds) >= 3 else None
            if not a or not a.get("href"):
                continue
            dt = fecha_gl(tds[0].get_text(" ", strip=True))
            href = a["href"]
            rid = href.rstrip("/").split("/")[-1]
            if not dt or rid in vistos:
                continue
            vistos.add(rid)
            reg = tds[3].find("a") if len(tds) > 3 else None
            out.append({
                "source": "carreirasgalegas", "id": "fga-" + rid,
                "name": a.get_text(" ", strip=True), "date": dt.isoformat(),
                "place": tds[2].get_text(" ", strip=True) or None, "region": "Galicia",
                "url": FGA + href if href.startswith("/") else href,
                "regulation": reg.get("href") if reg else None,
            })

        # Ficha de las próximas: hora y circuito
        hasta = (date.today() + timedelta(days=DIAS_FICHA)).isoformat()
        for r in out:
            if not (date.today().isoformat() <= r["date"] <= hasta):
                continue
            try:
                d.get(r["url"])
                WebDriverWait(d, 20).until(lambda x: "Información" in x.find_element(By.TAG_NAME, "body").text)
                txt = d.find_element(By.TAG_NAME, "body").text
            except Exception as e:
                print("  ficha sin cargar:", r["name"], e.__class__.__name__)
                continue
            kms = distancias(txt.split("Información da Carreira")[-1])
            if kms:
                r["km"] = kms
            t, lugar = hora_y_salida(txt)
            if t:
                r["time"] = t
            if lugar:
                r["start"] = lugar
            for line in txt.splitlines():
                if re.search(r"\bcircu[ií]to\b", line, re.I) and len(line) < 90:
                    r["circuit"] = line.strip()
                    break
        return out
    finally:
        d.quit()


# ─── CCNorte ───

def ccnorte(max_pages=10):
    s = requests.Session()
    out = []
    for page in range(1, max_pages + 1):
        url = f"{CCN}?search=" if page == 1 else f"{CCN}/page/{page}?search=&"
        resp = s.get(url, headers={"User-Agent": UA}, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        arts = soup.select("article.conjunto-eventos")
        for art in arts:
            ev = _ccnorte_evento(art)
            if ev:
                out.append(ev)
        if len(arts) < 10:
            break
        time.sleep(1)
    return out


def _ccnorte_evento(art):
    nombre = art.select_one("span.nombre-evento")
    fecha = art.select_one("span.evento-fecha")
    if not nombre or not fecha:
        return None
    try:
        dt = datetime.fromisoformat((fecha.get("content") or "").strip()[:19]).date()
    except ValueError:
        try:
            dt = datetime.strptime(fecha.get_text(strip=True)[:10], "%d/%m/%Y").date()
        except ValueError:
            return None
    lugar = [el.get_text(strip=True) for k in ("addressLocality", "addressRegion")
             for el in [art.select_one(f"[itemprop='{k}']")] if el and el.get_text(strip=True)]
    lugar = [re.sub(r"^\((.*)\)$", r"\1", x).strip() for x in lugar]
    region = lugar[-1] if len(lugar) > 1 else None
    # A veces «addressLocality» trae la calle («con C/ …», «anexo al estadio»): entonces vale la zona
    if lugar and (lugar[0][:1].islower() or "/" in lugar[0]) and region:
        lugar[0] = region
    link = next((a["href"] for a in art.select("a[href]")
                 if "/evento/" in a["href"] and "/index" not in a["href"]), None)
    if link and link.startswith("/"):
        link = "https://ccnorte.com" + link

    # Categorías (como en scraper_ccnorte.py): distancia, salida y franjas de precio
    cats, cur = [], None
    for row in art.select("table tbody tr"):
        tds = row.find_all("td")
        rs = [c for c in tds if c.get("rowspan")]
        reg = [c for c in tds if not c.get("rowspan")]
        if rs:
            if cur:
                cats.append(cur)
            dist = next((sp.get_text(strip=True) for sp in rs[0].select("span.info-carrera")
                         if any(ch.isdigit() for ch in sp.get_text()) and "m" in sp.get_text().lower()), "")
            cur = {"m": metros(dist), "salida": rs[1].get_text(strip=True) if len(rs) > 1 else "", "franjas": []}
        if cur is not None and len(reg) >= 3:
            cur["franjas"].append((reg[1].get_text(strip=True), reg[2].get_text(strip=True)))
    if cur:
        cats.append(cur)

    hoy = date.today()
    precio, plazo = None, None
    for c in cats:
        for hasta, p in c["franjas"]:
            try:
                h = datetime.strptime(hasta.replace(" 23:59", "").strip(), "%d/%m/%Y").date()
            except ValueError:
                continue
            if h >= hoy:
                plazo = max(plazo, h) if plazo else h
                if precio is None:
                    precio = p
    horas = sorted(m.group(0) for c in cats for m in [re.search(r"\d{1,2}:\d{2}", c["salida"])] if m)
    rid = (link or "").rstrip("/").split("/")[-1] or re.sub(r"\W+", "-", nombre.get_text(strip=True).lower())
    return {
        "source": "ccnorte", "id": "ccn-" + rid, "name": nombre.get_text(strip=True), "date": dt.isoformat(),
        "time": horas[0] if horas else None, "place": lugar[0] if lugar else None,
        "region": "Galicia" if es_galicia(" ".join(lugar)) else region,
        "km": sorted({round(c["m"] / 1000, 3) for c in cats if c["m"] > 0}, reverse=True),
        "price": precio, "deadline": plazo.isoformat() if plazo else None, "url": link or CCN,
    }


def main():
    salida = sys.argv[1] if len(sys.argv) > 1 else "carreras.json"
    items, fuentes = [], {}
    for nombre, fn in (("carreirasgalegas", carreiras_galegas), ("ccnorte", ccnorte)):
        try:
            got = fn()
            items.extend(got)
            fuentes[nombre] = {"ok": True, "count": len(got)}
            print(f"{nombre}: {len(got)} carreras")
        except Exception as e:
            fuentes[nombre] = {"ok": False, "count": 0, "error": f"{e.__class__.__name__}: {e}"[:300]}
            print(f"{nombre}: ERROR {e!r}")
    if not items:
        sys.exit("Ninguna fuente devolvió carreras")
    with open(salida, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.utcnow().isoformat() + "Z", "sources": fuentes, "items": items},
                  f, ensure_ascii=False, indent=1)
    print(f"Guardado {salida}: {len(items)} carreras")


if __name__ == "__main__":
    main()
