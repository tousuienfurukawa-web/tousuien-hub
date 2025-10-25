# api/fetch_sheet_slice.py
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json, io, os, re, hashlib, time
import openpyxl, requests
from datetime import datetime

# local cache util
try:
    import cache_util
except Exception:
    cache_util = None

# GitHub raw の Excel ファイル URL（環境変数で上書き可）
GITHUB_XLSX_URL = os.environ.get("GITHUB_XLSX_URL",
    "https://raw.githubusercontent.com/tousuienfurukawa-web/tousuien-hub/main/data/Customer_Management_latest.xlsx")

# default TTL seconds for Redis cache (can be overridden by env CACHE_TTL_SECONDS)
CACHE_TTL = int(os.environ.get("CACHE_TTL_SECONDS", "300"))

def normalize_header(s):
    if s is None:
        return ""
    return str(s).replace("\n"," ").replace("　"," ").strip()

def col_letter_to_index(col):
    col = col.upper()
    idx = 0
    for ch in col:
        if 'A' <= ch <= 'Z':
            idx = idx*26 + (ord(ch)-ord('A') + 1)
    return idx - 1

def parse_col_range(cols_spec, headers):
    if not cols_spec:
        return list(range(len(headers)))
    cols_spec = cols_spec.strip()
    if ':' in cols_spec and re.match(r'^[A-Za-z]+:[A-Za-z]+$', cols_spec):
        a,b = cols_spec.split(':')
        start = col_letter_to_index(a)
        end = col_letter_to_index(b)
        if start < 0: start = 0
        if end >= len(headers): end = len(headers)-1
        return list(range(start, end+1))
    names = [x.strip() for x in cols_spec.split(',') if x.strip()]
    indices = []
    for name in names:
        name_norm = normalize_header(name).lower()
        found = False
        for i,h in enumerate(headers):
            if normalize_header(h).lower() == name_norm:
                indices.append(i)
                found = True
                break
        if not found:
            for i,h in enumerate(headers):
                if name_norm in normalize_header(h).lower():
                    indices.append(i)
                    found = True
                    break
    return indices

def make_cache_key(sheet, start_row, end_row, cols_spec, summary, limit):
    # use a hashed key to avoid too long keys
    raw = f"sheet={sheet}|start={start_row}|end={end_row}|cols={cols_spec or ''}|summary={summary}|limit={limit}"
    h = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return f"sheet_slice:{h}"

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            sheet = params.get('sheet', [None])[0]
            start_row = int(params.get('start_row', ['2'])[0])
            end_row = int(params.get('end_row', ['200'])[0])
            cols_spec = params.get('cols', [None])[0]
            summary = params.get('summary', ['false'])[0].lower() == 'true'
            limit = int(params.get('limit', ['10'])[0])

            if not sheet:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({"error":"missing sheet param"}).encode('utf-8'))
                return

            # ---- Redis cache lookup ----
            cache_key = make_cache_key(sheet, start_row, end_row, cols_spec, summary, limit)
            cached = None
            if cache_util is not None:
                try:
                    cached = cache_util.cache_get(cache_key)
                except Exception:
                    cached = None
            if cached:
                # ensure meta shows cached true
                if isinstance(cached, dict):
                    cached_meta = cached.get("_meta", {})
                    cached_meta["cached"] = True
                    cached["_meta"] = cached_meta
                # return cached JSON
                self.send_response(200)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin','*')
                # custom header to denote cache hit
                self.send_header('X-Cache', 'HIT')
                self.end_headers()
                self.wfile.write(json.dumps(cached, ensure_ascii=False).encode('utf-8'))
                return

            # ---- Not cached: fetch Excel and compute ----
            resp = requests.get(GITHUB_XLSX_URL, timeout=30)
            resp.raise_for_status()
            wb = openpyxl.load_workbook(io.BytesIO(resp.content), data_only=True, read_only=True)

            if sheet not in wb.sheetnames:
                self.send_response(404)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({"error":"sheet not found"}).encode('utf-8'))
                return

            ws = wb[sheet]
            first_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
            headers = [normalize_header(h) for h in (first_row or [])]
            col_indices = parse_col_range(cols_spec, headers)
            if not col_indices:
                col_indices = list(range(len(headers))) if headers else []

            rows = []
            total_count = 0
            end_row_cap = min(end_row, start_row + 20000)

            for i, row in enumerate(ws.iter_rows(min_row=start_row, max_row=end_row_cap, values_only=True), start=start_row):
                rowvals = []
                for ci in col_indices:
                    if ci < len(row):
                        rowvals.append(row[ci])
                    else:
                        rowvals.append(None)
                rows.append(rowvals)
                total_count += 1
                if summary and total_count >= limit:
                    break

            result = {
                "sheet": sheet,
                "requested_rows": f"{start_row}-{end_row}",
                "returned": len(rows),
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "_meta": {
                    "cached": False,
                    "cache_ttl": CACHE_TTL
                }
            }
            if summary:
                result["headers"] = [headers[i] for i in col_indices] if headers else []
                result["top_rows"] = rows[:limit]
                result["note"] = "summary mode - top N rows"
            else:
                result["headers"] = [headers[i] for i in col_indices] if headers else []
                result["rows"] = rows

            # ---- store in Redis cache (if available) ----
            if cache_util is not None:
                try:
                    cache_util.cache_set(cache_key, result, ttl_seconds=CACHE_TTL)
                except Exception:
                    pass

            # return result
            self.send_response(200)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin','*')
            self.send_header('X-Cache', 'MISS')
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            import traceback
            self.send_response(500)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.end_headers()
            error_response = {"error": str(e), "traceback": traceback.format_exc()}
            self.wfile.write(json.dumps(error_response, ensure_ascii=False).encode('utf-8'))
