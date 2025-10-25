from http.server import BaseHTTPRequestHandler
import json

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # まずは基本的なレスポンスのテスト
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # 段階的にテスト
            test_result = {"status": "ok", "message": "Handler is working"}
            
            # パラメータの取得テスト
            from urllib.parse import urlparse, parse_qs
            parsed_path = urlparse(self.path)
            params = parse_qs(parsed_path.query)
            test_result["params"] = params
            
            # requestsのインポートテスト
            try:
                import requests
                test_result["requests_imported"] = True
            except Exception as e:
                test_result["requests_error"] = str(e)
            
            # openpyxlのインポートテスト
            try:
                import openpyxl
                test_result["openpyxl_imported"] = True
                test_result["openpyxl_version"] = openpyxl.__version__
            except Exception as e:
                test_result["openpyxl_error"] = str(e)
            
            # pathパラメータがあれば、実際の処理を試す
            if 'path' in params:
                try:
                    import requests
                    import io
                    import openpyxl
                    
                    path = params['path'][0]
                    base_raw_url = "https://raw.githubusercontent.com/tousuienfurukawa-web/tousuien-hub/main/"
                    url = base_raw_url + path
                    
                    response = requests.get(url, timeout=30)
                    response.raise_for_status()
                    test_result["file_fetched"] = True
                    test_result["file_size"] = len(response.content)
                    
                    workbook = openpyxl.load_workbook(io.BytesIO(response.content), data_only=True)
                    test_result["workbook_loaded"] = True
                    test_result["sheet_names"] = workbook.sheetnames
                    
                    # 最初のシートのヘッダーだけ取得
                    first_sheet = workbook[workbook.sheetnames[0]]
                    headers = [str(cell.value) if cell.value is not None else "" 
                              for cell in next(first_sheet.iter_rows(min_row=1, max_row=1))]
                    test_result["first_sheet_headers"] = headers
                    
                except Exception as e:
                    test_result["processing_error"] = str(e)
                    test_result["error_type"] = type(e).__name__
            
            output = json.dumps(test_result, ensure_ascii=False, indent=2)
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
