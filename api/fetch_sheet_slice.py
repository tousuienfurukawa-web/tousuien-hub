# api/fetch_sheet_slice.py
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json, io, os, time, re
import openpyxl, requests
from datetime import datetime

# GitHub raw の Excel ファイル URL（必要に応じて環境変数で上書き）
GITHUB_XLSX_URL = os.environ.get("GITHUB_XLSX_URL",
    "https://raw.githubusercontent.com/tousuienfurukawa-web/tousuien-hub/main/data/Customer_Management_latest.xlsx")

def normalize_header(s):
    if s is None:
        return ""
    return str(s).replace("\n"," ").replace("　"," ").strip()

def col_letter_to_index(col):
    # A -> 0, Z -> 25, AA -> 26
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
    # A:C 形式
    if ':' in cols_spec and re.match(r'^[A-Za-z]+:[A-Za-z]+$', cols_spec):
        a,b = cols_spec.split(':')
        start = col_letter_to_index(a)
        end = col_letter_to_index(b)
        if start < 0: start = 0
        if end >= len(headers): end = len(headers)-1
        return list(range(start, end+1))
    # comma-separated header names
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
        # if not found, try partial match
        if not found:
            for i,h in enumerate(headers):
                if name_norm in normalize_header(h).lower():
                    indices.append(i)
                    found = True
                    break
    return indices

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

            # fetch excel
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

            # header from first row
            first_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
            headers = [normalize_header(h) for h in (first_row or [])]

            col_indices = parse_col_range(cols_spec, headers)
            # if no indices resolved and headers empty, just return empty structure
            if not col_indices:
                col_indices = list(range(len(headers))) if headers else []

            rows = []
            total_count = 0
            # guard to not iterate too large loop: cap end_row reasonably (e.g., 10000)
            end_row_cap = min(end_row, start_row + 20000)

            for i, row in enumerate(ws.iter_rows(min_row=start_row, max_row=end_row_cap, values_only=True), start=start_row):
                # construct row values for requested columns
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
                "generated_at": datetime.utcnow().isoformat() + "Z"
            }
            if summary:
                result["headers"] = [headers[i] for i in col_indices] if headers else []
                result["top_rows"] = rows[:limit]
                result["note"] = "summary mode - top N rows"
            else:
                result["headers"] = [headers[i] for i in col_indices] if headers else []
                result["rows"] = rows

            self.send_response(200)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin','*')
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False, default=str).encode('utf-8'))
        except Exception as e:
            import traceback
            self.send_response(500)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.end_headers()
            error_response = {"error": str(e), "traceback": traceback.format_exc()}
            self.wfile.write(json.dumps(error_response, ensure_ascii=False).encode('utf-8'))
