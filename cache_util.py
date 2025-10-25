# cache_util.py
import os
import json
from redis import Redis

REDIS_URL = os.environ.get("REDIS_URL")
redis_client = None
if REDIS_URL:
    try:
        redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
        # optional: test connection
        redis_client.ping()
    except Exception:
        redis_client = None

def cache_get(key):
    if not redis_client:
        return None
    try:
        val = redis_client.get(key)
        if not val:
            return None
        return json.loads(val)
    except Exception:
        return None

def cache_set(key, obj, ttl_seconds=300):
    if not redis_client:
        return
    try:
        s = json.dumps(obj, ensure_ascii=False)
        redis_client.set(key, s, ex=ttl_seconds)
    except Exception:
        return
