# api/redis_health.py
from http.server import BaseHTTPRequestHandler
import json, os
try:
    from redis import Redis
except Exception:
    Redis = None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            REDIS_URL = os.environ.get("REDIS_URL")
            if not REDIS_URL or Redis is None:
                self.send_response(200)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({"redis": False, "message": "REDIS_URL not configured or redis lib missing"}).encode('utf-8'))
                return
            try:
                r = Redis.from_url(REDIS_URL, decode_responses=True)
                pong = r.ping()
                info = {"redis": True, "ping": pong}
                # also show some small stats if available
                try:
                    size = r.dbsize()
                    info["dbsize"] = size
                except Exception:
                    pass
                self.send_response(200)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps(info).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({"redis": False, "error": str(e)}).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
