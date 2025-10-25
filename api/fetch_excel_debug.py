from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # URLパラメータを解析
            parsed_path = urlparse(self.path)
            params = parse_qs(parsed_path.query)
            
            if 'path' not in params:
                self.send_error(400, "Missing 'path' parameter")
                return
            
            path = params['path'][0]
            
            # GitHubからExcelファイルを取得
            import requests
            import io
            import openpyxl
            
            base_raw_url = "https://raw.githubusercontent.com/tousuienfurukawa-web/tousuien-hub/main/"
            url = base_raw_url + path
            
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # Excelファイルを読み込み
            workbook = openpyxl.load_workbook(io.BytesIO(response.content), data_only=True)
            result = {}
            
            # 各シートのヘッダーと最初の行を取得
            for sheet_name in workbook.sheetnames:
                ws = workbook[sheet_name]
                
                # ヘッダー行を取得
                headers = []
                first_row = list(ws.iter_rows(min_row=1, max_row=1, values_only=True))
                if first_row:
                    headers = [str(cell) if cell is not None else "" for cell in first_row[0]]
                
                # データの最初の行を取得
                first_data = []
                second_row = list(ws.iter_rows(min_row=2, max_row=2, values_only=True))
                if second_row:
                    first_data = [str(cell) if cell is not None else "" for cell in second_row[0]]
                
                result[sheet_name] = {
                    "headers": headers,
                    "first_row": first_data
                }
            
            # JSON形式で返す
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            output = json.dumps(result, ensure_ascii=False, indent=2)
            self.wfile.write(output.encode('utf-8'))
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            error_response = json.dumps({
                "error": str(e),
                "type": type(e).__name__
            }, ensure_ascii=False)
            self.wfile.write(error_response.encode('utf-8'))
