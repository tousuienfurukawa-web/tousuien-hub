from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
from datetime import datetime, date

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
            
            code = params['code'][0].upper()
            
            import requests
            import io
            import openpyxl
            
            # GitHubからExcelファイルを取得
            github_url = "https://raw.githubusercontent.com/tousuienfurukawa-web/tousuien-hub/main/data/Customer_Management_latest.xlsx"
            response = requests.get(github_url, timeout=30)
            response.raise_for_status()
            
            workbook = openpyxl.load_workbook(io.BytesIO(response.content), data_only=True)
            
            # 営業用の4シート
            target_sheets = ["会社情報登録", "原料登録", "商品登録", "受注登録"]
            result = {
                "code": code,
                "found": False,
                "data": {}
            }
            
            # 各シートからデータを取得
            for sheet_name in target_sheets:
                if sheet_name not in workbook.sheetnames:
                    continue
                
                ws = workbook[sheet_name]
                
                # ヘッダー行を取得
                headers = []
                first_row = list(ws.iter_rows(min_row=1, max_row=1, values_only=True))
                if first_row and first_row[0]:
                    headers = [convert_value(cell) for cell in first_row[0]]
                
                # 企業コード列を探す
                code_col_index = None
                for idx, header in enumerate(headers):
                    if header and "企業コード" in str(header):
                        code_col_index = idx
                        break
                
                if code_col_index is None:
                    result["data"][sheet_name] = {
                        "error": "企業コード列が見つかりません",
                        "headers": headers
                    }
                    continue
                
                # 該当する行を検索
                matched_rows = []
                for row in ws.iter_rows(min_row=2, values_only=True):
                    if row and len(row) > code_col_index:
                        row_code = str(row[code_col_index]).strip().upper() if row[code_col_index] else ""
                        if row_code == code:
                            result["found"] = True
                            matched_row = [convert_value(cell) for cell in row]
                            # ヘッダーと値をマッピング
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
            
            # レスポンスを返す
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            output = json.dumps(result, ensure_ascii=False, indent=2)
            self.wfile.write(output.encode('utf-8'))
            
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
