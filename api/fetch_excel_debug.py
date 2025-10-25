from fastapi import FastAPI, Query
from mangum import Mangum
import requests, io, openpyxl, json

app = FastAPI()

@app.get("/")
@app.get("/fetch_excel_debug")
def fetch_excel_debug(path: str = Query(...)):
    base_raw_url = "https://raw.githubusercontent.com/tousuienfurukawa-web/tousuien-hub/main/"
    url = base_raw_url + path
    res = requests.get(url)
    res.raise_for_status()

    workbook = openpyxl.load_workbook(io.BytesIO(res.content), data_only=True)
    result = {}

    for sheet in workbook.sheetnames:
        ws = workbook[sheet]
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        first_data = [cell.value for cell in next(ws.iter_rows(min_row=2, max_row=2))]
        result[sheet] = {"headers": headers, "first_row": first_data}

    return result

# Vercel用のハンドラー
handler = Mangum(app)
