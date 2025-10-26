# scripts/create_summary_from_orders.py
import json
from pathlib import Path
import pandas as pd
from datetime import datetime

DIST = Path("dist")
OUT = Path("analysis")
OUT.mkdir(exist_ok=True)

def read_orders():
    files = list(DIST.glob("*受注登録*.csv.gz")) + list(DIST.glob("*受注登録*.csv"))
    if not files:
        # try common english name
        files = list(DIST.glob("*orders*.csv.gz")) + list(DIST.glob("*orders*.csv"))
    if not files:
        return None
    df = pd.read_csv(files[0], compression='gzip' if str(files[0]).endswith('.gz') else None, dtype=object)
    return df

def read_companies():
    files = list(DIST.glob("*会社情報登録*.csv.gz")) + list(DIST.glob("*会社情報登録*.csv"))
    if not files:
        files = list(DIST.glob("*company*.csv.gz")) + list(DIST.glob("*company*.csv"))
    if not files:
        return None
    return pd.read_csv(files[0], compression='gzip' if str(files[0]).endswith('.gz') else None, dtype=object)

def build_summary(orders, companies):
    summary = {}
    if orders is None:
        summary['error'] = 'orders not found in dist/'
        return summary
    # try to normalize invoice and company_code
    if 'invoice' not in orders.columns:
        # find any column that contains "TSE-"
        for c in orders.columns:
            if orders[c].astype(str).str.contains("TSE-").any():
                orders = orders.rename(columns={c:'invoice'})
                break
    possible_company_cols = [c for c in orders.columns if "会社" in c or "企業" in c or "company" in c.lower()]
    if possible_company_cols:
        orders = orders.rename(columns={possible_company_cols[0]:'company_code'})

    # per company counts
    if 'company_code' in orders.columns:
        gp = orders.groupby('company_code').size().rename("order_count").reset_index()
        summary['per_company'] = gp.to_dict(orient='records')
    else:
        summary['per_company'] = []

    # top invoices by count
    if 'invoice' in orders.columns:
        top = orders['invoice'].value_counts().head(20).reset_index()
        top.columns = ['invoice','count']
        summary['top_invoices'] = top.to_dict(orient='records')
    else:
        summary['top_invoices'] = []

    summary['generated_at'] = datetime.utcnow().isoformat() + 'Z'
    return summary

def main():
    orders = read_orders()
    companies = read_companies()
    s = build_summary(orders, companies)
    with open(OUT / "summary.json", "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    print("Wrote analysis/summary.json")

if __name__ == "__main__":
    main()
