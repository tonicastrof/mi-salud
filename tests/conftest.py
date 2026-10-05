import importlib.util
import os
import sys
from pathlib import Path

import pytest

API = Path(__file__).resolve().parent.parent / "api"
sys.path.insert(0, str(API))

os.environ.setdefault("UPSTASH_REDIS_URL", "https://example.invalid")
os.environ.setdefault("UPSTASH_REDIS_TOKEN", "x")


@pytest.fixture
def redis(monkeypatch):
    """Redis en memoria: sustituye a Upstash en todos los módulos que lo usan."""
    store = {}
    from _lib import cache, garmin_client
    for mod in (cache, garmin_client):
        monkeypatch.setattr(mod, "save", lambda k, v: store.__setitem__(k, v), raising=False)
        monkeypatch.setattr(mod, "load", lambda k: store.get(k), raising=False)
    return store


def load_endpoint(name):
    """Los endpoints tienen guiones en el nombre: se cargan por ruta."""
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), API / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
