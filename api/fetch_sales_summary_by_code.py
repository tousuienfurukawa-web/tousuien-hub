from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
from datetime import datetime, date
import time
import threading
import os

def convert_value(value):
    """セルの値を安全な形式に変換"""
    if value is None:
        return ""
    elif isinstance(value, (datetime, date)):
        return value.isoformat()
    elif isinstance(value, (int, float, str, bool)):
        return value
    else:
        return str(value)

# --- 短期キャッシュ（プロセス内） ---
CACHE = {}  # code -> {'ts': epoch_seconds, 'result': json_string}
CACHE_LOCK = threading.Lock()
CACHE_TTL = int(os.environ.get("CACHE_TTL", "300"))  # default 300s

def get_cached(code):
    with CACHE_LOCK:
        entry = CACHE.get(code)
        if not entry:
            return None
        now = time.time()
        if now - entry['ts'] <= CACHE_TTL:
            return entry['result']
        # TTL expired: still keep entry but mark as expired (we may use as stale)
        return None

def set_cache(code, json_str):
    with CACHE_LOCK:
        CACHE[code] = {'ts': time.time(), 'result': json_str}

def get_stale_if_any(code):
    with CACHE_LOCK:
        entry = CACHE.get(code)
        return entry['result'] if entry else None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed_path = urlparse(self.path)
            params = parse_qs(parsed_path.query)

            if 'code' not in params:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "Missing 'code' parameter",
                    "usage": "/api/fetch_sales_summary_by_code?code=BPR"
                }).encode('utf-8'))
                return

            code = params['code'][0].upper().strip()

            # 1) キャッシュを参照（短期）
            cached = get_cached(code)
            if cached:
                # すでにJSON文字列をキャッシュしているのでそのまま返す
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                # キャッシュレスポンスは "cached": true を付与するため、デコード→再ラップして返す
                try:
                    parsed = json.loads(cached)
                    parsed['_meta'] = parsed.get('_meta', {})
                    parsed['_meta']['cached'] = True
                    parsed['_meta']['cache_ttl'] = CACHE_TTL
                    out = json.dumps(parsed, ensure_ascii=False, indent=2)
                    self.wfile.write(out.encode('utf-8'))
                    return
                except Exception:
                    # もしキャッシュが文字列化できない場合は生返却
                    self.wfile.write(cached.encode('utf-8'))
                    return

            # 2) キャッシュが無ければ GitHub から Excel を取得して解析（read_only）
            import requests
            import io
            import openpyxl

            github_url = "https://raw.githubusercontent.com/tousuienfurukawa-web/tousuien-hub/main/data/Customer_Management_latest.xlsx"
            try:
                # タイムアウトは短めに設定（秒）
                response = requests.get(github_url, timeout=30)
                response.raise_for_status()
            except Exception as e:
                # GitHub 側の取得が失敗した場合、可能であれば stale キャッシュを返す
                stale = get_stale_if_any(code)
                if stale:
                    try:
                        parsed = json.loads(stale)
                    except Exception:
                        parsed = {"error": "使用可能な stale キャッシュがありますが、解析できません。", "raw": stale}
                    parsed['_meta'] = parsed.get('_meta', {})
                    parsed['_meta']['cached'] = True
                    parsed['_meta']['cache_ttl'] = CACHE_TTL
                    parsed['_meta']['stale'] = True
                    parsed['_meta']['notice'] = f"GitHub fetch failed: {str(e)}"
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    out = json.dumps(parsed, ensure_ascii=False, indent=2)
                    self.wfile.write(out.encode('utf-8'))
                    return
                else:
                    # キャッシュ無し -> エラーを返す
                    self.send_response(500)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.end_headers()
                    error_response = json.dumps({
                        "error": "Failed to fetch Excel from GitHub and no cache available",
                        "detail": str(e),
                        "type": type(e).__name__
                    }, ensure_ascii=False)
                    self.wfile.write(error_response.encode('utf-8'))
                    return

            # load_workbook を read_only モードで使う（メモリ節約）
            workbook = openpyxl.load_workbook(io.BytesIO(response.content), data_only=True, read_only=True)

            target_sheets = ["会社情報登録", "原料登録", "商品登録", "受注登録"]
            result = {
                "code": code,
                "found": False,
                "data": {},
                "_meta": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "cached": False,
                    "cache_ttl": CACHE_TTL
                }
            }

            for sheet_name in target_sheets:
                if sheet_name not in workbook.sheetnames:
                    result["data"][sheet_name] = {
                        "error": "シートが見つかりません",
                        "headers": [],
                        "rows": [],
                        "count": 0
                    }
                    continue

                ws = workbook[sheet_name]
                # ヘッダー行を取得（read_only モードでは iter_rows を使う）
                headers = []
                try:
                    first_row_iter = ws.iter_rows(min_row=1, max_row=1, values_only=True)
                    first_row = next(first_row_iter, None)
                except Exception:
                    first_row = None

                if first_row and first_row[0] is not None:
                    headers = [convert_value(cell) for cell in first_row]
                else:
                    # ヘッダーなし（想定外）
                    headers = []

                # 企業コード列を探す
                code_col_index = None
                for idx, header in enumerate(headers):
                    if header and "企業コード" in str(header):
                        code_col_index = idx
                        break

                if code_col_index is None:
                    result["data"][sheet_name] = {
                        "error": "企業コード列が見つかりません",
                        "headers": headers,
                        "rows": [],
                        "count": 0
                    }
                    continue

                matched_rows = []
                # read_only の iter_rows で 2 行目以降を逐次処理（メモリ節約）
                for row in ws.iter_rows(min_row=2, values_only=True):
                    # もし row が None の行が続く場合もあるので保護
                    if not row or len(row) <= code_col_index:
                        continue
                    row_code = str(row[code_col_index]).strip().upper() if row[code_col_index] else ""
                    if row_code == code:
                        result["found"] = True
                        matched_row = [convert_value(cell) for cell in row]
                        row_dict = {}
                        for i, header in enumerate(headers):
                            if i < len(matched_row):
                                row_dict[header] = matched_row[i]
                        matched_rows.append(row_dict)

                result["data"][sheet_name] = {
                    "headers": headers,
                    "rows": matched_rows,
                    "count": len(matched_rows)
                }

            # レスポンスをキャッシュして返す
            output_json = json.dumps(result, ensure_ascii=False, indent=2)
            set_cache(code, output_json)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(output_json.encode('utf-8'))

        except Exception as e:
            import traceback
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            error_response = json.dumps({
                "error": str(e),
                "type": type(e).__name__,
                "traceback": traceback.format_exc()
            }, ensure_ascii=False)
            self.wfile.write(error_response.encode('utf-8'))
