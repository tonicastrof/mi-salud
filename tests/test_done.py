from datetime import timedelta

from _lib.garmin_client import GarminClient
from _lib.tz import hoy
from _lib.workouts import family, mark_done
from conftest import load_endpoint


def test_familias():
    assert family("trail_running") == family("TrailRun") == family("Run") == "run"
    assert family("road_biking") == family("VirtualRide") == "ride"
    assert family("WeightTraining") == family("strength_training") == "strength"
    assert family("") == ""


def test_mark_done_con_strava():
    t = hoy().isoformat()
    ws = [{"date": t, "title": "Base", "sport_key": "running"},
          {"date": t, "title": "Fuerza", "sport_key": "strength_training"}]
    acts = [{"id": 1, "date": t, "sport": "Run", "sport_type": "Run", "name": "Rodaje",
             "distance": 8.2, "time": "45:10"}]
    out = mark_done(ws, acts)
    assert out[0]["done"] and out[0]["done_activity"]["distance"] == 8.2
    assert not out[1].get("done")            # una salida a correr no cumple la fuerza
    assert "done" not in ws[0]               # no toca la lista original


def test_cada_actividad_cuenta_una_vez():
    t = hoy().isoformat()
    ws = [{"date": t, "title": "A", "sport_key": "running"},
          {"date": t, "title": "B", "sport_key": "running"}]
    out = mark_done(ws, [{"id": 1, "date": t, "sport_type": "Run"}])
    assert [w.get("done", False) for w in out] == [True, False]


class Cal:
    def __init__(self, cal):
        self.cal = cal

    def connectapi(self, url):
        return self.cal if "calendar" in url else {}


def test_calendario_garmin_marca_hecho():
    t = hoy().isoformat()
    g = GarminClient()
    g.client = Cal({"calendarItems": [
        {"itemType": "fbtAdaptiveWorkout", "date": t, "title": "Base", "workoutUuid": "u",
         "sportTypeKey": "running"},
        {"itemType": "activity", "date": t, "title": "Carrera", "activityTypeKey": "running"},
    ]})
    out = g.get_scheduled_workouts()
    assert len(out) == 1 and out[0]["done"]


def test_widget_hecho_y_siguiente():
    widget = load_endpoint("widget")
    d = hoy()
    ws = [{"date": d.isoformat(), "title": "Base", "phrase": "BASE", "done": True,
           "done_activity": {"distance": 8.0, "time": "45:10"}},
          {"date": (d + timedelta(days=2)).isoformat(), "title": "Umbral 3x10"}]
    w = widget._next_workout(ws)
    assert w["done"] and w["kind"] == "Base"
    assert w["done_text"] == "8 km · 45:10"
    ws[0]["done_activity"]["distance"] = 8.2
    assert widget._next_workout(ws)["done_text"] == "8,2 km · 45:10"
    assert w["next"]["kind"] == "Umbral"
    # Si queda algo pendiente hoy, se enseña eso
    ws.insert(1, {"date": d.isoformat(), "title": "Fuerza"})
    assert widget._next_workout(ws)["title"] == "Fuerza"
