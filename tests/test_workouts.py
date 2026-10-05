from datetime import timedelta

from _lib.garmin_client import GarminClient, _parse_workout, _fmt_pace, _fmt_secs, _fmt_dist
from _lib.coach_context import build_plan_block
from _lib.tz import hoy
from conftest import load_endpoint

DETAIL = {
    "workoutName": "Series 6x800",
    "sportType": {"sportTypeKey": "running"},
    "estimatedDurationInSecs": 3300,
    "workoutSegments": [{"workoutSteps": [
        {"type": "ExecutableStepDTO", "stepOrder": 1, "stepType": {"stepTypeKey": "warmup"},
         "endCondition": {"conditionTypeKey": "time"}, "endConditionValue": 900,
         "targetType": {"workoutTargetTypeKey": "heart.rate.zone"}, "zoneNumber": 2},
        {"type": "RepeatGroupDTO", "stepOrder": 2, "numberOfIterations": 6, "workoutSteps": [
            {"type": "ExecutableStepDTO", "stepOrder": 3, "stepType": {"stepTypeKey": "interval"},
             "endCondition": {"conditionTypeKey": "distance"}, "endConditionValue": 800,
             "targetType": {"workoutTargetTypeKey": "pace.zone"},
             "targetValueOne": 3.7, "targetValueTwo": 3.92},
            {"type": "ExecutableStepDTO", "stepOrder": 4, "stepType": {"stepTypeKey": "recovery"},
             "endCondition": {"conditionTypeKey": "time"}, "endConditionValue": 90}]},
        {"type": "ExecutableStepDTO", "stepOrder": 5, "stepType": {"stepTypeKey": "cooldown"},
         "endCondition": {"conditionTypeKey": "lap.button"}, "description": "suave"}]}],
}


def test_formatos():
    assert _fmt_pace(1000 / 300) == "5:00"
    assert _fmt_secs(900) == "15 min"
    assert _fmt_secs(90) == "1:30"
    assert _fmt_secs(5400) == "1h30"
    assert _fmt_dist(800) == "800 m"
    assert _fmt_dist(10000) == "10 km"


def test_parse_workout_con_series():
    w = _parse_workout({"date": "2026-10-08", "workoutId": 42}, DETAIL)
    assert w["title"] == "Series 6x800" and w["sport"] == "Run" and not w["coach"]
    warm, rep, cool = w["steps"]
    assert (warm["label"], warm["duration"], warm["target"]) == ("Calentamiento", "15 min", "FC zona 2")
    assert rep["repeat"] == 6
    # velocidad alta = ritmo rápido: el rango va de rápido a lento
    assert rep["steps"][0]["target"] == "4:15–4:30 /km"
    assert cool["duration"] == "hasta pulsar vuelta" and cool["note"] == "suave"


def test_parse_workout_sin_detalle():
    w = _parse_workout({"date": "2026-10-06", "title": "Base", "workoutUuid": "abc",
                        "sportTypeKey": "running"}, None)
    assert w["title"] == "Base" and w["coach"] and w["steps"] == []


class FakeGarmin:
    def __init__(self, cal):
        self.cal, self.urls = cal, []

    def connectapi(self, url):
        self.urls.append(url)
        if "calendar" in url:
            return self.cal
        if "fbt-adaptive" in url:
            raise RuntimeError("404")
        return DETAIL


def test_scheduled_workouts_filtra_y_cae_al_siguiente_endpoint():
    t = hoy()
    cal = {"calendarItems": [
        {"itemType": "activity", "date": t.isoformat(), "title": "Hecha"},
        {"itemType": "workout", "date": (t - timedelta(days=1)).isoformat(), "workoutId": 1},
        {"itemType": "fbtAdaptiveWorkout", "date": (t + timedelta(days=1)).isoformat(),
         "workoutUuid": "u1", "workoutId": 7, "title": "Base"},
    ]}
    g = GarminClient()
    g.client = FakeGarmin(cal)
    out = g.get_scheduled_workouts()
    assert len(out) == 1
    assert out[0]["coach"] and out[0]["steps"]           # el UUID falló, el id sí
    assert any("/workout-service/workout/7" in u for u in g.client.urls)
    assert "Calentamiento · 15 min · FC zona 2" in build_plan_block(out)


def test_widget_entreno_de_hoy_o_siguiente():
    widget = load_endpoint("widget")
    t = hoy()
    ws = [
        {"date": (t - timedelta(days=1)).isoformat(), "title": "Pasado"},
        {"date": (t + timedelta(days=2)).isoformat(), "title": "Umbral 3x10", "duration_sec": 3000},
        {"date": (t + timedelta(days=1)).isoformat(), "title": "Rodaje", "phrase": "BASE"},
    ]
    w = widget._next_workout(ws)
    assert (w["when"], w["kind"], w["is_today"]) == ("Mañana", "Base", False)
    hoy_w = widget._next_workout([{"date": t.isoformat(), "title": "Umbral 3x10",
                                   "duration_sec": 3000}])
    assert (hoy_w["when"], hoy_w["kind"], hoy_w["minutes"]) == ("Hoy", "Umbral", 50)
    assert widget._next_workout([]) is None


def test_tipos_por_titulo():
    widget = load_endpoint("widget")
    t = hoy().isoformat()
    kind = lambda title, phrase=None: widget._next_workout(
        [{"date": t, "title": title, "phrase": phrase}])["kind"]
    assert kind("Umbral 3x10") == "Umbral"
    assert kind("6x800") == "VO₂ máx"
    assert kind("Tempo 2x15'") == "Tempo"
    assert kind("Base", "AEROBIC_BASE") == "Base"
    assert kind("Recuperación") == "Recuperación"
    assert kind("Tirada larga") == "Larga"
    assert kind("Paseo") == ""
