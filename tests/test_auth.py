from _lib import auth


class H(dict):
    def get(self, k, d=None):
        return super().get(k, d)


def test_sin_contrasena_no_hay_candado(monkeypatch):
    monkeypatch.delenv("APP_SECRET", raising=False)
    monkeypatch.delenv("GARMIN_PASSWORD", raising=False)
    assert auth.authorized(H())


def test_cookie_y_cabeceras(monkeypatch):
    monkeypatch.delenv("APP_SECRET", raising=False)
    monkeypatch.setenv("GARMIN_PASSWORD", "garmin-pw")
    monkeypatch.setenv("CRON_SECRET", "cron")
    t = auth.token()
    assert t and "garmin-pw" not in t
    assert not auth.authorized(H())
    assert not auth.authorized(H({"Cookie": "ms_auth=otra"}))
    assert auth.authorized(H({"Cookie": "a=b; ms_auth=" + t}))
    assert auth.authorized(H({"X-App-Token": t}))
    assert auth.authorized(H({"Authorization": "Bearer cron"}))
    assert not auth.authorized(H({"Authorization": "Bearer nope"}))
    assert auth.check_password("garmin-pw") and not auth.check_password("x")


def test_app_secret_manda_sobre_garmin(monkeypatch):
    monkeypatch.setenv("GARMIN_PASSWORD", "garmin-pw")
    monkeypatch.setenv("APP_SECRET", "secreto")
    assert auth.check_password("secreto") and not auth.check_password("garmin-pw")
    assert auth.authorized(H({"X-App-Secret": "secreto"}))
    assert not auth.authorized(H({"X-App-Secret": ""}))
