from fastapi import FastAPI, Query
import requests, io, openpyxl, json

app = FastAPI()

@app.get("/fetch_excel_from_github")
def fetch_excel_from_github(path: str = Query(...)):
    # 1️⃣ GitHub RAW URL に直接アクセス（サイズ制限なし）
    base_raw_url = "https://raw.githubusercontent.com/tousuienfurukawa-web/tousuien-hub/main/"
    url = base_raw_url + path

    res = requests.get(url)
    res.raise_for_status()

    # 2️⃣ Excelをメモリ上で開く
    workbook = openpyxl.load_workbook(io.BytesIO(res.content), data_only=True)
    sheet = workbook.active

    # 3️⃣ 見出し行の取得
    headers = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
    records = [dict(zip(headers, row)) for row in sheet.iter_rows(min_row=2, values_only=True)]

    # 4️⃣ 要約整形
    summary = [
        {
            "企業コード": r.get("企業コード"),
            "会社名": r.get("会社名"),
            "合計金額": f"{r.get('通貨')} {r.get('合計金額')}" if r.get("通貨") else r.get("合計金額"),
            "入金確認日": r.get("入金確認日"),
            "Invoice番号": r.get("Invoice番号")
        }
        for r in records if r.get("企業コード")
    ]

    return json.dumps(summary[:10], ensure_ascii=False, indent=2)  # 最初の10件を返す
