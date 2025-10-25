# api/redis_health.py
from http.server import BaseHTTPRequestHandler
import json
import os
import logging

logging.basicConfig(level=logging.INFO)

class handler(BaseHTTPRequestHandler):
    """
    Simple health check endpoint for Redis / Upstash.
    Exposes GET which returns JSON:
      - redis: bool
      - ping: bool or null
      - dbsize: int or null
      - message/error: text on failure
    """

    def _write_json(self, status_code:int, obj:dict):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # Allow CORS for convenience
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        # CORS preflight
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        try:
            # 1) Check configuration
            REDIS_URL = os.environ.get("REDIS_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
            if not REDIS_URL:
                logging.info("REDIS_URL not configured")
                return self._write_json(200, {
                    "redis": False,
                    "message": "REDIS_URL not configured"
                })

            # 2) Import redis library lazily (avoid failing at module import time)
            try:
                from redis import Redis
            except Exception as e:
                logging.exception("redis library not available")
                return self._write_json(200, {
                    "redis": False,
                    "message": "redis lib not installed",
                    "error": str(e),
                })

            # 3) Try connecting via redis-py (supports rediss://)
            try:
                # For Upstash rediss:// (TCP/TLS) the password is usually embedded in the URL.
                # For most Upstash cases this will work: Redis.from_url(REDIS_URL, decode_responses=True)
                r = Redis.from_url(REDIS_URL, decode_responses=True)
                pong = False
                try:
                    pong = bool(r.ping())
                except Exception as e_ping:
                    logging.warning("Ping failed: %s", e_ping)
                    # keep pong False

                dbsize = None
                try:
                    # dbsize may not be available on REST endpoints or restricted accounts
                    dbsize = int(r.dbsize())
                except Exception as e_db:
                    logging.info("dbsize not available: %s", e_db)
                    dbsize = None

                info = {"redis": True, "ping": pong, "dbsize": dbsize}
                return self._write_json(200, info)

            except Exception as e:
                logging.exception("Redis connection error")
                # If using Upstash REST, user might have set REST URL; attempt a fallback
                # But prefer to return the error so user can adjust env var.
                return self._write_json(500, {
                    "redis": False,
                    "error": str(e)
                })

        except Exception as e:
            logging.exception("Unexpected error in redis_health handler")
            self._write_json(500, {"error": str(e)})
