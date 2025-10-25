from fastapi import FastAPI, Query
import requests, base64, io, openpyxl, json, os

app = FastAPI()

@app.get("/fetch_excel_from_github")
def fetch_excel_from_github(path: str = Query(...)):
    owner = "tousuienfurukawa-web"
    repo = "tousuien-hub"
    branch = "main"
    token = os.environ.get("GITHUB_TOKEN")

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    headers = {"Authorization": f"token {token}"} if token else {}
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    data = res.json()

    content = base64.b64decode(data["content"])
    workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    sheet = workbook.active

    headers = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
    records = [dict(zip(headers, row)) for row in sheet.iter_rows(min_row=2, values_only=True)]

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

    return json.dumps(summary, ensure_ascii=False, indent=2)
