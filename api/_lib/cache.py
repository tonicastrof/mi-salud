import os, json
from upstash_redis import Redis

def _r():
    return Redis(url=os.environ["UPSTASH_REDIS_URL"], token=os.environ["UPSTASH_REDIS_TOKEN"])

def save(key, data):
    _r().set(key, json.dumps(data, default=str))

def load(key):
    raw = _r().get(key)
    if raw:
        return json.loads(raw) if isinstance(raw, str) else raw
    return None
