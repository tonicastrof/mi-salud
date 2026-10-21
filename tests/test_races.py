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


def test_normaliza_campos_habituales():
    r = races.normalize({"id": "abc", "name": "XII Carreira Popular de Rianxo",
                         "date": "2026-10-31T17:30:00", "locality": "Rianxo",
                         "province": "A Coruña", "distances": [10000, 2000]})
    assert r["id"] == "abc" and r["date"] == "2026-10-31" and r["time"] == "17:30"
    assert r["place"] == "Rianxo" and r["province"] == "A Coruña"
    assert r["km"] == [10, 2] and r["dist"] == "10K · 2K"
    assert r["type"] == "Ruta"


def test_normaliza_epoch_y_tipo_por_nombre():
    # 2026-11-08 09:00 en Madrid = 08:00 UTC
    r = races.normalize({"_id": 7, "title": "Trail Monte Pindo 24K", "startDate": 1794124800000})
    assert r["date"] == "2026-11-08" and r["time"] == "09:00"
    assert r["type"] == "Trail" and r["km"] == [24]
    assert races.normalize({"name": "Media Maratón Cidade de Lugo", "date": "2026-11-15"})["dist"] == "Media"
    assert races.normalize({"name": "Cross de Santa Comba", "date": "2026-11-01"})["type"] == "Cross"


def test_sin_nombre_o_fecha_se_descarta():
    assert races.normalize({"name": "Sin fecha"}) is None
    assert races.normalize({"date": "2026-11-01"}) is None


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
