from fastapi import FastAPI, Query
import requests, io, openpyxl, json

app = FastAPI()

@app.get("/fetch_sales_summary_by_code")
def fetch_sales_summary_by_code(
    path: str = Query(...),
    code: str = Query(...)
):
    base_raw_url = "https://raw.githubusercontent.com/tousuienfurukawa-web/tousuien-hub/main/"
    url = base_raw_url + path
    res = requests.get(url)
    res.raise_for_status()

    wb = openpyxl.load_workbook(io.BytesIO(res.content), data_only=True)
    target_sheets = ["会社情報登録", "原料登録", "商品登録", "受注登録"]
    data = {}

    for sheet_name in target_sheets:
        if sheet_name not in wb.sheetnames:
            continue

        sheet = wb[sheet_name]
        headers = [
            str(cell.value).replace("\n", "").strip() if cell.value else ""
            for cell in next(sheet.iter_rows(min_row=1, max_row=1))
        ]
        records = [
            dict(zip(headers, row))
            for row in sheet.iter_rows(min_row=2, values_only=True)
        ]

        # 部分一致検索に変更（TSE-なしでもヒット）
        if sheet_name == "会社情報登録":
            filtered = [
                {
                    "企業コード": r.get("企業コード"),
                    "会社名": r.get("会社名(billing)"),
                    "国": r.get("国(billing)") or r.get("国(shipping)"),
                    "営業担当者": r.get("営業担当者"),
                    "支払方法": r.get("支払方法"),
                    "メール": r.get("メールアドレス"),
                }
                for r in records
                if code in str(r.get("企業コード", ""))
            ]
            if filtered:
                data["会社情報登録"] = filtered

        elif sheet_name == "原料登録":
            # 共通マスタのため全件返す
            data["原料登録"] = [
                {
                    "原料資材コード": r.get("原料資材コード"),
                    "原料名": r.get("原料名 / 資材名"),
                    "有機非有機": r.get("有機非有機"),
                    "仕入れ先": r.get("仕入れ先"),
                    "2025産地": r.get("2025産地"),
                    "2025品種": r.get("2025品種"),
                    "2025原価": r.get("2025原価"),
                }
                for r in records if r.get("原料名 / 資材名")
            ]

        elif sheet_name == "商品登録":
            filtered = [
                {
                    "企業コード": r.get("企業コード"),
                    "商品コード": r.get("商品コード") or r.get("商品番号"),
                    "商品名": r.get("商品名"),
                    "有機非有機": r.get("有機非有機"),
                    "茶種": r.get("茶種"),
                    "売価": r.get("売価"),
                    "通貨": r.get("通貨"),
                    "包装種類": r.get("包装種類"),
                }
                for r in records
                if code in str(r.get("企業コード", ""))
            ]
            if filtered:
                data["商品登録"] = filtered

        elif sheet_name == "受注登録":
            filtered = [
                {
                    "企業コード": r.get("企業コード"),
                    "invoice": r.get("invoice"),
                    "通貨": r.get("通貨"),
                    "商品総額": r.get("商品総額"),
                    "送料": r.get("送料"),
                    "輸送方法": r.get("輸送方法"),
                    "注文日": r.get("注文日"),
                    "出荷日": r.get("出荷日"),
                    "入金確認日": r.get("入金確認日①"),
                }
                for r in records
                if code in str(r.get("企業コード", ""))
            ]
            if filtered:
                data["受注登録"] = filtered

    return json.dumps(data, ensure_ascii=False, indent=2)
