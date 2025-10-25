git add api/fetch_sales_summary_by_code.py
git commit -m "Add limit and sheet filter to API"
git push origin main
```

### 新しい使い方
```
# 最新10件のみ
https://tousuien-hub.vercel.app/api/fetch_sales_summary_by_code?code=CTP&limit=10

# 受注登録のみ
https://tousuien-hub.vercel.app/api/fetch_sales_summary_by_code?code=CTP&sheet=受注登録&limit=5

# 会社情報のみ
https://tousuien-hub.vercel.app/api/fetch_sales_summary_by_code?code=CTP&sheet=会社情報登録
```

### Custom GPTのInstructionsを更新
```
## パラメータ
- code: 企業コード（必須）
- limit: 取得件数（デフォルト100、最大でも20件程度を推奨）
- sheet: 特定シートのみ取得（会社情報登録、受注登録など）

大量データの場合は、limit=5 や sheet=会社情報登録 を使用してください。
