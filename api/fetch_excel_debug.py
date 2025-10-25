from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests
import io
import openpyxl
import json

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # URLパラメータを解析
        parsed_path = urlparse(self.path)
        params = parse_qs(parsed_path.query)
        
        if 'path' not in params:
            self.send_response(400)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "path parameter is required"}).encode())
            return
        
        path = params['path'][0]
        base_raw_url = "https://raw.githubusercontent.com/tousuienfurukawa-web/tousuien-hub/main/"
        url = base_raw_url + path
        
        try:
            res = requests.get(url)
            res.raise_for_status()
            
            workbook = openpyxl.load_workbook(io.BytesIO(res.content), data_only=True)
            result = {}
            
            for sheet in workbook.sheetnames:
                ws = workbook[sheet]
                headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
                first_data = [cell.value for cell in next(ws.iter_rows(min_row=2, max_row=2))]
                result[sheet] = {"headers": headers, "first_row": first_data}
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8'))
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
