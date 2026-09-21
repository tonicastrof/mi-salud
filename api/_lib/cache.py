import os, json
from upstash_redis import Redis

_client = None


def _r():
    # Reutilizar el cliente: archivar un día hace varias llamadas seguidas y
    # antes cada save/load montaba un Redis nuevo.
    global _client
    if _client is None:
        _client = Redis(url=os.environ["UPSTASH_REDIS_URL"], token=os.environ["UPSTASH_REDIS_TOKEN"])
    return _client


def _decode(raw):
    if not raw:
        return None
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except ValueError:
        return None


def save(key, data):
    _r().set(key, json.dumps(data, default=str))


def load(key):
    return _decode(_r().get(key))


def mload(keys):
    """Varias claves de golpe. Devuelve una lista alineada con `keys` (None donde falte).

    Leer 90 días del archivo son 90 GET sueltos; con MGET es una petición por
    cada 100 claves.
    """
    keys = list(keys)
    if not keys:
        return []
    out = []
    for i in range(0, len(keys), 100):
        chunk = keys[i:i + 100]
        got = _r().mget(*chunk)
        out.extend(got if got else [None] * len(chunk))
    return [_decode(v) for v in out]
