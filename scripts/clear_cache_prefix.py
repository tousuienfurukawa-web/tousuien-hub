# scripts/clear_cache_prefix.py
import os
from redis import Redis

REDIS_URL = os.environ.get("REDIS_URL")
PREFIX = os.environ.get("CACHE_CLEAR_PREFIX", "sheet_slice:")  # default prefix

if not REDIS_URL:
    print("REDIS_URL not set")
    exit(1)

r = Redis.from_url(REDIS_URL, decode_responses=True)
# Use scan_iter to avoid blocking
count = 0
for key in r.scan_iter(match=PREFIX + "*"):
    r.delete(key)
    count += 1
print(f"Deleted {count} keys with prefix {PREFIX}")
