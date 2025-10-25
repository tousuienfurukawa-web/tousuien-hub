# scripts/generate_reports_dynamic.py
# Usage:
#  - Set env COMPANIES="ILJ,MCG,CTP,MEH" to force specific list
#  - Or set AUTO_TOP_N=20 and optionally AUTO_TOP_MONTHS=6 to auto pick top N companies by recent sales
#  - Run: python scripts/generate_reports_dynamic.py

import os, io, json, requests
from datetime import datetime, timedelta
import pandas as pd

GITHUB_XLSX_URL = os.environ.get("GITHUB_XLSX_URL",
    "https://raw.githubusercontent.com/tousuienfurukawa-web/tousuien-hub/main/data/Customer_Management_latest.xlsx")
OUT_BASE = "data/reports"
os.makedirs(OUT_BASE, exist_ok=True)

def fetch_orders_df():
    r = requests.get(GITHUB_XLSX_URL, timeout=60)
    r.raise_for_status()
    xls = pd.ExcelFile(io.BytesIO(r.content), engine="openpyxl")
    if '受注登録' not in xls.sheet_names:
        return pd.DataFrame()
    df = pd.read_excel(xls, sheet_name='受注登録', engine='openpyxl', dtype=str)
    # normalize column names (string)
    df.columns = [str(c) for c in df.columns]
    return df

def detect_columns(df):
    # heuristics for date/amount/company/product columns
    date_candidates = [c for c in df.columns if '日' in c or 'date' in c.lower() or 'order' in c.lower()]
    amt_candidates = [c for c in df.columns if '金額' in c or '合計' in c or 'amount' in c.lower() or 'total' in c.lower()]
    code_candidates = [c for c in df.columns if '企業' in c or 'company' in c.lower()]
    prod_candidates = [c for c in df.columns if '商品' in c or 'product' in c.lower() or '商品コード' in c]
    # fallback
    date_col = date_candidates[0] if date_candidates else None
    amt_col = amt_candidates[0] if amt_candidates else None
    code_col = code_candidates[0] if code_candidates else None
    prod_col = prod_candidates[0] if prod_candidates else None
    return date_col, amt_col, code_col, prod_col

def to_num_series(df, col):
    if col is None:
        return pd.Series([0.0]*len(df))
    s = df[col].astype(str).str.replace(',','').str.replace('USD','').str.replace('JPY','').str.replace('EUR','')
    return pd.to_numeric(s, errors='coerce').fillna(0.0)

def to_date_series(df, col):
    if col is None:
        return pd.Series([pd.NaT]*len(df))
    return pd.to_datetime(df[col], errors='coerce')

def get_companies_from_sheet():
    # fallback: read 会社情報登録 sheet for企業コード column
    r = requests.get(GITHUB_XLSX_URL, timeout=60)
    r.raise_for_status()
    xls = pd.ExcelFile(io.BytesIO(r.content), engine="openpyxl")
    if '会社情報登録' not in xls.sheet_names:
        return []
    df = pd.read_excel(xls, sheet_name='会社情報登録', engine='openpyxl', dtype=str)
    df.columns = [str(c) for c in df.columns]
    code_cols = [c for c in df.columns if '企業' in c or '会社コード' in c or '企業コード' in c]
    if not code_cols:
        # try first column fallback
        vals = df.iloc[:,0].astype(str).str.strip().unique().tolist()
        return [v for v in vals if v]
    code_col = code_cols[0]
    codes = df[code_col].astype(str).str.strip().str.upper().dropna().unique().tolist()
    return codes

def auto_select_top_companies(df, top_n=20, months=6, date_col=None, amt_col=None, code_col=None):
    if df.empty or code_col is None:
        return []
    dates = to_date_series(df, date_col)
    amt_series = to_num_series(df, amt_col)
    df2 = df.copy()
    df2['__date__'] = dates
    df2['__amt__'] = amt_series
    cutoff = datetime.utcnow() - timedelta(days=30*months)
    sub = df2[df2['__date__'] >= cutoff]
    if sub.empty:
        # fallback to overall top by amount
        grp = df2.groupby(code_col)['__amt__'].sum().reset_index().sort_values('__amt__', ascending=False)
    else:
        grp = sub.groupby(code_col)['__amt__'].sum().reset_index().sort_values('__amt__', ascending=False)
    top = grp.head(top_n)
    codes = top[code_col].astype(str).str.strip().str.upper().tolist()
    return codes

def generate_reports_for_company(df, code, date_col, amt_col, prod_col, code_col):
    # create outdir for company
    out_dir = os.path.join(OUT_BASE, code)
    os.makedirs(out_dir, exist_ok=True)

    d = df.copy()
    # normalize code column values
    if code_col:
        d['__code__'] = d[code_col].astype(str).str.strip().str.upper()
    else:
        d['__code__'] = ''

    d['__date__'] = to_date_series(d, date_col)
    d['__amt__'] = to_num_series(d, amt_col)

    # 1) 2025 H1 sales for this company
    mask_h1 = (d['__code__'] == code) & (d['__date__'] >= '2025-01-01') & (d['__date__'] < '2025-07-01')
    sub_h1 = d[mask_h1]
    if not sub_h1.empty:
        agg = sub_h1.groupby('__code__')['__amt__'].agg(['count','sum']).reset_index()
    else:
        agg = pd.DataFrame()
    report_h1 = {
        "company": code,
        "report_name": f"{code} 2025 H1 Sales",
        "generated_at": datetime.utcnow().isoformat()+"Z",
        "aggregation": agg.to_dict(orient='records'),
        "sample_rows": sub_h1.head(50).to_dict(orient='records'),
        "meta": {"date_col": date_col, "amt_col": amt_col}
    }
    with open(os.path.join(out_dir, f"{code.lower()}-2025-h1-sales.json"), 'w', encoding='utf-8') as f:
        json.dump(report_h1, f, ensure_ascii=False, indent=2)

    # 2) order history (recent 100)
    mask_code = d['__code__'] == code
    orders = d[mask_code].sort_values('__date__', ascending=False).head(100)
    report_orders = {"company": code, "report_name": f"{code} order history (recent 100)", "generated_at": datetime.utcnow().isoformat()+"Z", "rows": orders.to_dict(orient='records')}
    with open(os.path.join(out_dir, f"{code.lower()}-order-history.json"), 'w', encoding='utf-8') as f:
        json.dump(report_orders, f, ensure_ascii=False, indent=2)

    # 3) major products (top 20 by sales)
    if prod_col:
        d['__prod__'] = d[prod_col].astype(str)
        prod_grp = d[d['__code__']==code].groupby('__prod__')['__amt__'].agg(['count','sum']).reset_index().sort_values('sum', ascending=False).head(20)
        report_prod = {"company": code, "report_name": f"{code} major products", "generated_at": datetime.utcnow().isoformat()+"Z", "product_agg": prod_grp.to_dict(orient='records')}
        with open(os.path.join(out_dir, f"{code.lower()}-major-products.json"), 'w', encoding='utf-8') as f:
            json.dump(report_prod, f, ensure_ascii=False, indent=2)

    return True

def build_index():
    index = {}
    for root, dirs, files in os.walk(OUT_BASE):
        for fname in files:
            if not fname.endswith('.json'):
                continue
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, OUT_BASE)
            # company/report path like ILJ/ilj-2025-h1-sales.json
            try:
                mtime = os.path.getmtime(full)
                index[rel.replace("\\","/")] = {"path": rel.replace("\\","/"), "modified_at": datetime.utcfromtimestamp(mtime).isoformat()+"Z"}
            except:
                index[rel.replace("\\","/")] = {"path": rel.replace("\\","/"), "modified_at": None}
    # write index
    with open(os.path.join(OUT_BASE, "index.json"), 'w', encoding='utf-8') as f:
        json.dump({"generated_at": datetime.utcnow().isoformat()+"Z", "reports": index}, f, ensure_ascii=False, indent=2)
    return index

def main():
    # read env or decide automatically
    forced = os.environ.get("COMPANIES")
    auto_n = os.environ.get("AUTO_TOP_N")
    auto_months = int(os.environ.get("AUTO_TOP_MONTHS", "6"))
    top_n = int(auto_n) if auto_n and auto_n.isdigit() else None

    df = fetch_orders_df()
    if df is None or df.empty:
        print("No orders sheet found or empty, attempting to still build index of existing reports.")
        build_index()
        return

    date_col, amt_col, code_col, prod_col = detect_columns(df)

    # building candidate list
    companies = []
    if top_n:
        # auto select
        companies = auto_select_top_companies(df, top_n=top_n, months=auto_months, date_col=date_col, amt_col=amt_col, code_col=code_col)
        print("Auto-selected top companies:", companies)
    elif forced:
        companies = [c.strip().upper() for c in forced.split(",") if c.strip()]
        print("Using forced companies:", companies)
    else:
        companies = get_companies_from_sheet()
        print("Read companies from sheet:", len(companies), "companies")

    # limit for safety
    max_companies = int(os.environ.get("MAX_GENERATE_COMPANIES", "200"))
    companies = companies[:max_companies]

    # generate per company
    for code in companies:
        try:
            print("Generating reports for", code)
            generate_reports_for_company(df, code, date_col, amt_col, prod_col, code_col)
        except Exception as e:
            print("Error generating for", code, e)

    # build index.json
    idx = build_index()
    print("Index built - reports count:", len(idx))

if __name__ == "__main__":
    main()
