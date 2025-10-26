# scripts/merge_customer_and_chats.py
import re
import json
from pathlib import Path
import pandas as pd
from datetime import datetime
from dateutil import parser as dateparser

# 設定（必要に応じてパスを変更）
DIST_DIR = Path("dist")
SLACK_DIR = Path("data/slack_threads")
ALIBABA_DIR = Path("data/alibaba_chats")
OUT_DIR = Path("analysis")
OUT_DIR.mkdir(exist_ok=True)

INVOICE_RE = re.compile(r"(TSE-[A-Z]{3}-[A-Z0-9-_.]+)", re.IGNORECASE)

def read_dist_csv(name_guess):
    """
    name_guess: 部分一致で該当シート名のファイルを探す
    """
    files = list(DIST_DIR.glob(f"*{name_guess}*.csv.gz"))
    if not files:
        files = list(DIST_DIR.glob(f"*{name_guess}*.csv"))
    if not files:
        return None
    # 先頭のファイルを読み込む
    path = files[0]
    df = pd.read_csv(path, compression='gzip' if str(path).endswith(".gz") else None, dtype=object)
    return df

def load_customer_tables():
    # 代表的なものを読み込む（カスタマイズ可）
    # 受注登録
    orders = read_dist_csv("受注登録")
    # 会社情報登録
    companies = read_dist_csv("会社情報登録")
    # 受注に合計金額が無ければ、manifest/別シート確認が必要
    return companies, orders

def extract_invoice_from_text(text):
    if not isinstance(text, str):
        return None
    m = INVOICE_RE.search(text)
    return m.group(1) if m else None

def load_slack_messages():
    # slack csv を想定：columns: ts, user, text, thread_ts, channel
    dfs = []
    if not SLACK_DIR.exists():
        return pd.DataFrame()
    for f in SLACK_DIR.glob("**/*"):
        if f.suffix.lower() in [".csv", ".gz"]:
            df = pd.read_csv(f, compression='gzip' if f.suffix.lower()=='.gz' else None, dtype=object)
            df["source_file"] = f.name
            dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    all_df = pd.concat(dfs, ignore_index=True, sort=False)
    # normalize columns
    if "text" not in all_df.columns:
        # guess column
        text_cols = [c for c in all_df.columns if "text" in c.lower() or "message" in c.lower()]
        if text_cols:
            all_df = all_df.rename(columns={text_cols[0]:"text"})
    # parse timestamp if exists
    if "ts" in all_df.columns:
        try:
            all_df["ts_parsed"] = all_df["ts"].apply(lambda x: dateparser.parse(str(x)))
        except Exception:
            all_df["ts_parsed"] = None
    else:
        all_df["ts_parsed"] = None
    # extract invoice mentions
    all_df["invoice"] = all_df["text"].astype(str).apply(extract_invoice_from_text)
    return all_df

def load_alibaba_messages():
    dfs = []
    if not ALIBABA_DIR.exists():
        return pd.DataFrame()
    for f in ALIBABA_DIR.glob("**/*"):
        if f.suffix.lower() in [".csv", ".gz", ".txt"]:
            if f.suffix.lower() in [".csv",".gz"]:
                df = pd.read_csv(f, compression='gzip' if f.suffix.lower()==".gz" else None, dtype=object)
            else:
                # txt: each line is a message
                lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
                df = pd.DataFrame({"text": lines})
            df["source_file"] = f.name
            dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    all_df = pd.concat(dfs, ignore_index=True, sort=False)
    # normalize
    if "text" not in all_df.columns:
        text_cols = [c for c in all_df.columns if "text" in c.lower() or "message" in c.lower()]
        if text_cols:
            all_df = all_df.rename(columns={text_cols[0]:"text"})
    all_df["invoice"] = all_df["text"].astype(str).apply(extract_invoice_from_text)
    # timestamp parse
    time_cols = [c for c in all_df.columns if "time" in c.lower() or "date" in c.lower()]
    if time_cols:
        all_df["ts_parsed"] = all_df[time_cols[0]].apply(lambda x: dateparser.parse(str(x)) if pd.notnull(x) else None)
    else:
        all_df["ts_parsed"] = None
    return all_df

def merge_data(companies, orders, slack_df, ali_df):
    # Prepare orders: try to ensure invoice column exists
    if orders is None:
        print("orders is None")
        orders = pd.DataFrame()
    if "Invoice Number" not in orders.columns and "invoice" not in orders.columns and "F" not in orders.columns:
        # attempt: find a column with TSE pattern
        found = None
        for c in orders.columns:
            if orders[c].astype(str).str.contains("TSE-").any():
                found = c
                break
        if found:
            orders = orders.rename(columns={found: "invoice"})
    if "invoice" not in orders.columns:
        # create invoice column by scanning any text columns
        orders["invoice"] = orders.astype(str).apply(lambda row: next((INVOICE_RE.search(s).group(1) for s in row if INVOICE_RE.search(str(s))), None), axis=1)
    # Normalize company code: assume orders has '企業コード' or 'company_code' or 'Company Code'
    possible_company_cols = [c for c in orders.columns if "会社" in c or "企業" in c or "company" in c.lower()]
    if possible_company_cols:
        orders = orders.rename(columns={possible_company_cols[0]:"company_code"})
    # Merge slack by invoice
    slack_matches = slack_df[slack_df["invoice"].notnull()].copy()
    ali_matches = ali_df[ali_df["invoice"].notnull()].copy()

    # Left join orders with slack messages on invoice
    merged = orders.copy()
    merged = merged.astype(object)
    merged["order_invoice"] = merged.get("invoice")
    # attach counts of slack mentions
    invoice_slack_count = slack_matches.groupby("invoice").size().rename("slack_mention_count")
    invoice_ali_count = ali_matches.groupby("invoice").size().rename("alibaba_mention_count")
    merged = merged.merge(invoice_slack_count, left_on="invoice", right_index=True, how="left")
    merged = merged.merge(invoice_ali_count, left_on="invoice", right_index=True, how="left")
    merged["slack_mention_count"] = merged["slack_mention_count"].fillna(0).astype(int)
    merged["alibaba_mention_count"] = merged["alibaba_mention_count"].fillna(0).astype(int)

    # attach company info if companies table exists: try to find company code key
    if companies is not None:
        # find common key (company_code or similar)
        company_key = None
        for c in companies.columns:
            if "会社" in c or "企業" in c or "company" in c.lower() or "code" in c.lower():
                company_key = c
                break
        if company_key:
            # rename to company_code for merge
            companies = companies.rename(columns={company_key: "company_code"})
            merged = merged.merge(companies.add_prefix("company_"), left_on="company_code", right_on="company_company_code", how="left")
    return merged

def summarize_merged(df):
    summary = {}
    # orders per company
    if "company_code" in df.columns:
        gp = df.groupby("company_code").agg({
            "invoice":"count",
            "slack_mention_count":"sum",
            "alibaba_mention_count":"sum"
        }).rename(columns={"invoice":"order_count"})
        summary["per_company"] = gp.reset_index().to_dict(orient="records")
    # top invoices by slack mentions
    top_slack = df.sort_values("slack_mention_count", ascending=False).head(20)
    summary["top_slack"] = top_slack[["invoice","company_code","slack_mention_count"]].to_dict(orient="records")
    summary["generated_at"] = datetime.utcnow().isoformat() + "Z"
    return summary

def main():
    companies, orders = load_customer_tables()
    print("companies:", None if companies is None else companies.shape)
    print("orders:", None if orders is None else orders.shape)
    slack_df = load_slack_messages()
    ali_df = load_alibaba_messages()
    print("slack:", slack_df.shape if not slack_df.empty else (0,0))
    print("ali:", ali_df.shape if not ali_df.empty else (0,0))
    merged = merge_data(companies, orders, slack_df, ali_df)
    merged_out = OUT_DIR / "merged_orders_with_chats.csv.gz"
    merged.to_csv(merged_out, index=False, compression="gzip")
    summary = summarize_merged(merged)
    with open(OUT_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("Written:", merged_out, "and summary.json")

if __name__ == "__main__":
    main()
