# api/redis_health.py
from http.server import BaseHTTPRequestHandler
import json, os

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # 1) 簡易チェック：REDIS_URL が設定されているか
            REDIS_URL = os.environ.get("REDIS_URL")
            if not REDIS_URL:
                self.send_response(200)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "redis": False,
                    "message": "REDIS_URL not configured"
                }, ensure_ascii=False).encode('utf-8'))
                return

            # 2) redis ライブラリが利用可能か確認
            try:
                from redis import Redis
            except Exception as e:
                self.send_response(200)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "redis": False,
                    "message": "redis lib not installed",
                    "error": str(e)
                }, ensure_ascii=False).encode('utf-8'))
                return

            # 3) 接続して ping と dbsize を確認
            try:
                r = Redis.from_url(REDIS_URL, decode_responses=True)
                pong = r.ping()
                info = {"redis": True, "ping": bool(pong)}
                try:
                    size = r.dbsize()
                    info["dbsize"] = int(size)
                except Exception:
                    # dbsize may not be available on some managed services; ignore if fails
                    info["dbsize"] = None
                self.send_response(200)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps(info, ensure_ascii=False).encode('utf-8'))
                return
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "redis": False,
                    "error": str(e)
                }, ensure_ascii=False).encode('utf-8'))
                return

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode('utf-8'))
