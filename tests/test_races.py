from datetime import timedelta

import pytest

from _lib import races
from _lib.tz import hoy


@pytest.fixture
def store(monkeypatch):
    """Redis en memoria para el módulo de carreras."""
    data = {}
    monkeypatch.setattr(races, "save", lambda k, v: data.__setitem__(k, v))
    monkeypatch.setattr(races, "load", lambda k: data.get(k))
    monkeypatch.setenv("CARREIRAS_SEARCH_KEY", "x")
    return data


def _d(n):
    return (hoy() + timedelta(days=n)).isoformat()


def test_normaliza_carreiras_galegas():
    r = races.normalize({"source": "carreirasgalegas", "id": "fga-YjMOoLm4", "date": "2026-10-31",
                         "name": "XII CARREIRA POPULAR CONCELLO DE RIANXO", "place": "Rianxo",
                         "region": "Galicia", "time": "16:30", "url": "https://x/rianxo"})
    assert r["name"] == "XII Carreira Popular Concello de Rianxo"
    assert r["time"] == "16:30" and r["place"] == "Rianxo" and r["province"] == "Galicia"
    assert r["type"] == "Ruta" and r["km"] == [] and r["source"] == "Carreiras Galegas"


def test_normaliza_ccnorte_con_distancias():
    r = races.normalize({"source": "ccnorte", "id": "ccn-1", "name": "Carrera de Llanes", "date": "2026-11-08",
                         "km": [10, 5, 0], "price": "12 €", "deadline": "2026-11-05", "region": "Asturias"})
    assert r["km"] == [10, 5] and r["dist"] == "10K · 5K" and r["price"] == "12 €"
    assert r["deadline"] == "2026-11-05" and r["source"] == "CCNorte"


def test_tipo_y_distancia_por_el_nombre():
    n = lambda name: races.normalize({"name": name, "date": "2026-11-08"})
    assert n("IX TRAIL DAS BESTAS -SERIE OURO")["type"] == "Trail"
    assert n("47º MEMORIAL BELARMINO ALONSO DE CAMPO A TRAVÉS")["type"] == "Cross"
    assert n("IV ANDAINA CONCELLO DE MAÑÓN 2026")["type"] == "Andaina"
    assert n("XXVIII LA21 MEDIA MARATON DE VIGO")["dist"] == "Media"
    assert n("XV CARREIRA POPULAR SIN-SON 10K")["dist"] == "10K"
    assert n("XLVII CARREIRA PEDESTRE SANTIAGO - EL CORREO GALLEGO")["name"] == \
        "XLVII Carreira Pedestre Santiago - El Correo Gallego"


def test_sin_nombre_o_fecha_se_descarta():
    assert races.normalize({"name": "Sin fecha"}) is None
    assert races.normalize({"date": "2026-11-01"}) is None


def test_junta_la_misma_carrera_de_las_dos_webs():
    fga = races.normalize({"source": "carreirasgalegas", "id": "fga-1", "date": "2026-11-15",
                           "name": "XXVIII LA21 MEDIA MARATON DE VIGO", "url": "https://fga/vigo"})
    ccn = races.normalize({"source": "ccnorte", "id": "ccn-9", "date": "2026-11-15", "name": "Media Maratón de Vigo",
                           "km": [21.0975, 10], "time": "10:00", "price": "20 €", "url": "https://ccn/vigo"})
    otra = races.normalize({"source": "ccnorte", "id": "ccn-2", "date": "2026-11-15", "name": "Trail de Moraña"})
    out = races.merge([fga, ccn, otra])
    assert len(out) == 2
    vigo = out[0]
    assert vigo["id"] == "fga-1" and vigo["url"] == "https://fga/vigo"      # manda Carreiras Galegas
    assert vigo["time"] == "10:00" and vigo["price"] == "20 €" and vigo["also"] == "https://ccn/vigo"


def test_refresh_lee_el_json(store, monkeypatch):
    monkeypatch.setattr(races, "fetch_data", lambda: {"generated_at": "2026-10-22T04:30:00Z",
        "sources": {"ccnorte": {"ok": True, "count": 2}},
        "items": [{"source": "ccnorte", "id": "a", "name": "Uno", "date": _d(3)},
                  {"source": "ccnorte", "id": "b", "name": "Pasada", "date": _d(-3)}]})
    assert races.refresh() == {"races": 1, "new": 0}
    p = races.payload()
    assert [r["id"] for r in p["items"]] == ["a"] and p["scraped_at"] == "2026-10-22T04:30:00Z"


def test_primera_descarga_no_avisa_y_luego_si():
    a, b = {"id": "a"}, {"id": "b"}
    first = races.mark_new([a], None)
    assert first["new"] == [] and first["ids"] == ["a"]
    second = races.mark_new([a, b], first)
    assert second["new"] == ["b"] and second["new_key"]
    # Sigue siendo nueva hasta marcarla como vista, aunque no haya más novedades
    third = races.mark_new([a, b], second)
    assert third["new"] == ["b"] and third["new_key"] == second["new_key"]


def test_payload_apuntadas_y_novedades(store):
    store[races.KEY_RACES] = {"items": [
        {"id": "a", "name": "A", "date": _d(3), "time": "10:00", "dist": "10K"},
        {"id": "b", "name": "B", "date": _d(20), "time": None, "dist": ""},
        {"id": "viejo", "name": "Pasada", "date": _d(-2)}]}
    store[races.KEY_SEEN] = {"ids": ["a", "b"], "new": ["b"], "new_key": "k1"}
    races.set_signed("a", True)
    p = races.payload()
    assert [r["id"] for r in p["items"]] == ["a", "b"]          # la pasada no sale
    assert p["items"][0]["signed"] and not p["items"][1]["signed"]
    assert p["new_count"] == 1 and p["items"][1]["is_new"]

    race, news = races.widget_info()
    assert race["name"] == "A" and race["days"] == 3
    assert news["count"] == 1 and news["key"] == "k1"
    assert "A" in races.coach_block()

    races.mark_seen()
    assert races.payload()["new_count"] == 0
    races.set_signed("a", False)
    assert races.widget_info()[0] is None


def test_apuntada_que_desaparece_del_listado_se_mantiene(store):
    store[races.KEY_RACES] = {"items": [{"id": "a", "name": "A", "date": _d(5)}]}
    races.set_signed("a", True)
    store[races.KEY_RACES] = {"items": []}
    assert [r["id"] for r in races.payload()["items"]] == ["a"]


def test_apuntar_una_que_no_existe(store):
    with pytest.raises(KeyError):
        races.set_signed("nada", True)


def test_distancia_a_casa(store, monkeypatch):
    monkeypatch.delenv("CASA_LAT", raising=False)
    store[races.KEY_RACES] = {"items": [
        {"id": "son", "name": "Porto do Son", "date": _d(3), "lat": 42.7236, "lon": -9.0049},
        {"id": "lugo", "name": "Lugo", "date": _d(4), "lat": 43.0097, "lon": -7.5568},
        {"id": "nada", "name": "Sin mapa", "date": _d(5)}]}
    p = races.payload()
    km = {r["id"]: r["km_casa"] for r in p["items"]}
    assert p["home"] == "Noia" and km["nada"] is None
    assert 8 <= km["son"] <= 14 and 100 <= km["lugo"] <= 125
    monkeypatch.setenv("CASA_LAT", "43.0097")
    monkeypatch.setenv("CASA_LON", "-7.5568")
    assert next(r for r in races.payload()["items"] if r["id"] == "lugo")["km_casa"] == 0


def test_normaliza_coordenadas():
    r = races.normalize({"name": "X", "date": "2026-11-08", "lat": 42.7, "lon": -8.9})
    assert r["lat"] == 42.7 and r["lon"] == -8.9
