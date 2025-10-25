# api/redis_health.py
# Health check endpoint for Upstash Redis
# Place this file in your repository under api/ and deploy to Vercel.
from http.server import BaseHTTPRequestHandler
import json
import os
import traceback

class handler(BaseHTTPRequestHandler):
    def send_json(self, status_code, obj):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode('utf-8'))

    def do_GET(self):
        try:
            REDIS_URL = os.environ.get("REDIS_URL")
            if not REDIS_URL:
                self.send_json(200, {"redis": False, "message": "REDIS_URL not configured"})
                return

            # check if redis library is available
            try:
                from redis import Redis
            except Exception as e:
                self.send_json(200, {
                    "redis": False,
                    "message": "redis lib not installed",
                    "error": str(e)
                })
                return

            # try to connect and run simple checks
            try:
                r = Redis.from_url(REDIS_URL, decode_responses=True)
                pong = r.ping()
                info = {"redis": True, "ping": bool(pong)}
                # try to get dbsize (may not be available on some managed services; ignore failures)
                try:
                    size = r.dbsize()
                    # dbsize may return int or string; ensure int or null
                    info["dbsize"] = int(size) if size is not None else None
                except Exception:
                    info["dbsize"] = None
                self.send_json(200, info)
                return
            except Exception as e:
                # return 500 with error details for debugging (stacktrace included)
                self.send_json(500, {
                    "redis": False,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                })
                return

        except Exception as e:
            self.send_json(500, {"error": str(e), "traceback": traceback.format_exc()})
