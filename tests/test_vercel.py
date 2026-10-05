import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_como_mucho_12_funciones():
    """El plan Hobby de Vercel no despliega más de 12 funciones: con 13, el
    despliegue falla entero y la web se queda en la versión anterior."""
    builds = json.loads((ROOT / "vercel.json").read_text())["builds"]
    funcs = [b["src"] for b in builds if b["src"].startswith("api/")]
    assert len(funcs) <= 12, funcs


def test_rutas_apuntan_a_ficheros_que_existen():
    routes = json.loads((ROOT / "vercel.json").read_text())["routes"]
    for r in routes:
        dest = r["dest"].split("?")[0]
        if dest.startswith("/api/"):
            assert (ROOT / dest.lstrip("/")).exists(), r
