# scripts/create_summary_from_orders.py
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

DIST = Path("dist")
OUT = Path("analysis")
OUT.mkdir(exist_ok=True)

def _find_column(columns: Iterable[str], keywords: Iterable[str]) -> Optional[str]:
    """Return the first column whose lowercased name contains any keyword."""
    lowered = [(c, c.lower()) for c in columns]
    for keyword in keywords:
        key = keyword.lower()
        for original, lower in lowered:
            if key in lower:
                return original
    return None

def read_orders():
    files = list(DIST.glob("*受注登録*.csv.gz")) + list(DIST.glob("*受注登録*.csv"))
    if not files:
        files = list(DIST.glob("*orders*.csv.gz")) + list(DIST.glob("*orders*.csv"))
    if not files:
        return None
    path = files[0]
    print(f"Reading orders from: {path}")
    df = pd.read_csv(path, compression='gzip' if str(path).endswith('.gz') else None, dtype=object)
    return df

def read_companies():
    files = list(DIST.glob("*会社情報登録*.csv.gz")) + list(DIST.glob("*会社情報登録*.csv"))
    if not files:
        files = list(DIST.glob("*company*.csv.gz")) + list(DIST.glob("*company*.csv"))
    if not files:
        return None
    path = files[0]
    print(f"Reading companies from: {path}")
    df = pd.read_csv(path, compression='gzip' if str(path).endswith('.gz') else None, dtype=object)
    return df

def build_summary(orders, companies):
    summary = {}
    if orders is None:
        summary['error'] = 'orders not found in dist/'
        return summary

    # Normalize invoice column
    if 'invoice' not in orders.columns:
        found = None
        # try column that contains TSE-
        for c in orders.columns:
            try:
                if orders[c].astype(str).str.contains("TSE-").any():
                    found = c
                    break
            except Exception:
                continue
        if found:
            orders = orders.rename(columns={found: 'invoice'})

    # Normalize company_code column
    company_col = _find_column(orders.columns, ["会社", "企業", "company", "顧客", "コード"])
    if company_col and company_col != "company_code":
        orders = orders.rename(columns={company_col: "company_code"})

    # If invoice still missing, attempt to extract by scanning row values (safe)
    if 'invoice' not in orders.columns:
        import re
        INVOICE_RE = re.compile(r"(TSE-[A-Z0-9-_.]+)", re.IGNORECASE)
        def _find_invoice_in_row(row):
            for v in row:
                try:
                    m = INVOICE_RE.search(str(v))
                    if m:
                        return m.group(1)
                except Exception:
                    continue
            return None
        orders['invoice'] = orders.apply(_find_invoice_in_row, axis=1)

    # Per-company counts
    if 'company_code' in orders.columns:
        gp = (
            orders.groupby('company_code')
            .size()
            .rename("order_count")
            .reset_index()
            .sort_values("order_count", ascending=False)
        )
        # enrich with company name if available
        if companies is not None:
            company_code_col = _find_column(
                companies.columns,
                ["company_code", "company code", "会社コード", "企業コード", "顧客コード", "コード"],
            )
            if company_code_col:
                companies = companies.rename(columns={company_code_col: "company_code"})
            name_col = _find_column(
                companies.columns,
                ["company_name", "company name", "会社名", "企業名", "name", "名称"],
            )
            if name_col and name_col != "company_name":
                companies = companies.rename(columns={name_col: "company_name"})
            if "company_name" not in companies.columns:
                companies["company_name"] = None
            company_info = companies[["company_code", "company_name"]].drop_duplicates()
            gp = gp.merge(company_info, on="company_code", how="left")
        gp["order_count"] = gp["order_count"].astype(int)
        summary['per_company'] = gp.to_dict(orient='records')
    else:
        summary['per_company'] = []

    summary['total_orders'] = int(len(orders))
    summary['unique_companies'] = int(orders['company_code'].nunique()) if 'company_code' in orders.columns else 0
    summary['orders_without_company'] = int(orders['company_code'].isna().sum()) if 'company_code' in orders.columns else int(len(orders))

    # top invoices by count
    if 'invoice' in orders.columns:
        top = orders['invoice'].value_counts().head(20).reset_index()
        top.columns = ['invoice', 'count']
        top['count'] = top['count'].astype(int)
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
