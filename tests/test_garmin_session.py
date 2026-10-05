import json

from _lib import garmin_client


class FakeInner:
    def __init__(self, tokens):
        self.tokens = tokens

    def dumps(self):
        return self.tokens


class FakeGarmin:
    """Imita garminconnect: login(ruta) carga la sesión del fichero si existe
    y, si no, hace login «de verdad» y la escribe."""
    logins = 0

    def __init__(self, email, password):
        self.client = FakeInner(None)
        self.stats_calls = 0

    def login(self, path):
        f = garmin_client.TOKEN_FILE
        if f.exists():
            self.client.tokens = f.read_text()
        else:
            FakeGarmin.logins += 1
            self.client.tokens = json.dumps({"di_token": f"nuevo{FakeGarmin.logins}"})
            f.write_text(self.client.tokens)

    def get_stats(self, date):
        self.stats_calls += 1
        return {"totalSteps": 1000, "restingHeartRate": 50}


def test_sesion_se_guarda_y_reutiliza(redis, monkeypatch, tmp_path):
    monkeypatch.setattr(garmin_client, "Garmin", FakeGarmin)
    monkeypatch.setattr(garmin_client, "TOKEN_DIR", tmp_path)
    monkeypatch.setattr(garmin_client, "TOKEN_FILE", tmp_path / "garmin_tokens.json")
    FakeGarmin.logins = 0

    assert garmin_client.GarminClient().connect()
    assert FakeGarmin.logins == 1 and "nuevo1" in redis[garmin_client.TOKENS_KEY]

    # Arranque en frío: /tmp vacío, pero la sesión sigue en Redis
    (tmp_path / "garmin_tokens.json").unlink()
    assert garmin_client.GarminClient().connect()
    assert FakeGarmin.logins == 1


def test_stats_semanales_no_se_repiten(redis, monkeypatch, tmp_path):
    monkeypatch.setattr(garmin_client, "Garmin", FakeGarmin)
    monkeypatch.setattr(garmin_client, "TOKEN_DIR", tmp_path)
    monkeypatch.setattr(garmin_client, "TOKEN_FILE", tmp_path / "garmin_tokens.json")
    g = garmin_client.GarminClient()
    g.connect()
    g.get_steps_week()
    g.get_stress_week()
    g.get_body_battery_week()
    assert g.client.stats_calls == 7
