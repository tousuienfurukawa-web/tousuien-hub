# api/fetch_report.py
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json, os, io
import requests, openpyxl
from datetime import datetime
import pandas as pd

GITHUB_RAW_BASE = os.environ.get("GITHUB_RAW_BASE",
    "https://raw.githubusercontent.com/tousuienfurukawa-web/tousuien-hub/main")

def fetch_raw_json(path):
    url = f"{GITHUB_RAW_BASE}/{path}"
    r = requests.get(url, timeout=30)
    if r.status_code == 200:
        return r.json()
    return None

def try_generate_report_on_the_fly(name):
    """
    簡易フォールバック: '受注登録' シートを解析し、企業別・期間別の集計を作る。
    name のパターンに応じていくつかのレポートを作成。
    （この関数は簡易実装であり、必要に応じて拡張してください）
    """
    # fetch excel
    excel_url = f"{GITHUB_RAW_BASE}/data/Customer_Management_latest.xlsx"
    r = requests.get(excel_url, timeout=30)
    r.raise_for_status()
    # load into pandas for convenience
    xls = pd.ExcelFile(io.BytesIO(r.content), engine='openpyxl')
    if '受注登録' not in xls.sheet_names:
        return None
    df = pd.read_excel(xls, sheet_name='受注登録', engine='openpyxl', dtype=str)

    # try to find date and amount columns
    # candidate names
    date_cols = [c for c in df.columns if '日' in str(c) or 'date' in str(c).lower() or 'order' in str(c).lower()]
    amt_cols = [c for c in df.columns if '金額' in str(c) or '合計' in str(c) or 'amount' in str(c).lower() or 'total' in str(c).lower()]
    code_cols = [c for c in df.columns if '企業' in str(c) or 'company' in str(c).lower()]

    # convert date if available
    if date_cols:
        df['__date__'] = pd.to_datetime(df[date_cols[0]], errors='coerce')
    else:
        df['__date__'] = pd.NaT

    # convert amount if available
    if amt_cols:
        def to_num(x):
            try:
                s = str(x).replace(',','').strip()
                # remove currency prefixes
                s = s.replace('USD','').replace('JPY','').replace('EUR','')
                return float(s) if s not in [None,'nan','NaN',''] else 0.0
            except:
                return 0.0
        df['__amt__'] = df[amt_cols[0]].apply(to_num)
    else:
        df['__amt__'] = 0.0

    if 'ilj-2025-h1-sales' == name:
        # filter for 2025 H1
        mask = (df['__date__'] >= '2025-01-01') & (df['__date__'] < '2025-07-01')
        sub = df[mask]
        if code_cols:
            grp = sub.groupby(code_cols[0])['__amt__'].agg(['count','sum']).reset_index()
            return {
                "report_name": "ILJ 2025年上半期 売上（簡易生成）",
                "generated_at": datetime.utcnow().isoformat()+"Z",
                "group_by_company": grp.to_dict(orient='records'),
                "sample_rows": sub.head(20).to_dict(orient='records')
            }
    # generic fallback: group by company for all years
    if code_cols:
        grp = df.groupby(code_cols[0])['__amt__'].agg(['count','sum']).reset_index()
        return {
            "report_name": f"{name} (generic generated)",
            "generated_at": datetime.utcnow().isoformat()+"Z",
            "group_by_company": grp.to_dict(orient='records'),
            "note": "This is a generic fallback report generated on the fly"
        }
    return None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            name = params.get('name', [None])[0]
            fallback = params.get('fallback', ['true'])[0].lower() == 'true'
            if not name:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({"error":"missing report name"}).encode('utf-8'))
                return

            # try fetch precomputed JSON from GitHub raw
            # expect path: data/reports/{name}.json
            path = f"data/reports/{name}.json"
            try:
                url = f"{GITHUB_RAW_BASE}/data/reports/{name}.json"
                r = requests.get(url, timeout=20)
                if r.status_code == 200:
                    # return direct content
                    content = r.json()
                    self.send_response(200)
                    self.send_header('Content-Type','application/json; charset=utf-8')
                    self.send_header('Access-Control-Allow-Origin','*')
                    self.end_headers()
                    self.wfile.write(json.dumps(content, ensure_ascii=False, indent=2).encode('utf-8'))
                    return
            except Exception:
                pass

            # not found - fallback generation?
            if fallback:
                generated = try_generate_report_on_the_fly(name)
                if generated:
                    self.send_response(200)
                    self.send_header('Content-Type','application/json; charset=utf-8')
                    self.send_header('Access-Control-Allow-Origin','*')
                    self.end_headers()
                    self.wfile.write(json.dumps(generated, ensure_ascii=False, indent=2).encode('utf-8'))
                    return

            # nothing found
            self.send_response(404)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({"error":"report not found", "name": name}).encode('utf-8'))
        except Exception as e:
            import traceback
            self.send_response(500)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False).encode('utf-8'))
