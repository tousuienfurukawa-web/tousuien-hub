# cache_util.py
import os
import json
try:
    from redis import Redis
except Exception:
    Redis = None

REDIS_URL = os.environ.get("REDIS_URL")  # set this in Vercel
redis_client = None
if REDIS_URL and Redis is not None:
    try:
        redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        redis_client = None

def cache_get(key):
    """
    Returns Python object (deserialized JSON) or None if not found / redis not configured.
    """
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
    """
    Stores object as JSON string with TTL.
    """
    if not redis_client:
        return
    try:
        s = json.dumps(obj, ensure_ascii=False)
        redis_client.set(key, s, ex=ttl_seconds)
    except Exception:
        return
