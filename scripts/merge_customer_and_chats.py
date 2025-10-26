# scripts/merge_customer_and_chats.py
from __future__ import annotations

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

INVOICE_RE = re.compile(r"(TSE-[A-Z0-9-_.]+)", re.IGNORECASE)


def read_dist_csv(name_guess: str):
    """
    name_guess: 部分一致で該当シート名のファイルを探す
    """
    files = list(DIST_DIR.glob(f"*{name_guess}*.csv.gz"))
    if not files:
        files = list(DIST_DIR.glob(f"*{name_guess}*.csv"))
    if not files:
        return None
    path = files[0]
    df = pd.read_csv(path, compression="gzip" if str(path).endswith(".gz") else None, dtype=object)
    return df


def load_customer_tables():
    # 代表的なものを読み込む（カスタマイズ可）
    orders = read_dist_csv("受注登録")
    companies = read_dist_csv("会社情報登録")
    return companies, orders


def extract_invoice_from_text(text):
    if not isinstance(text, str):
        return None
    m = INVOICE_RE.search(text)
    return m.group(1) if m else None


def _empty_chat_df():
    return pd.DataFrame(columns=["invoice", "text", "source_file", "ts", "ts_parsed"])


def load_slack_messages():
    # slack csv を想定：columns: ts, user, text, thread_ts, channel
    dfs = []
    if not SLACK_DIR.exists():
        return _empty_chat_df()
    for f in SLACK_DIR.glob("**/*"):
        if f.suffix.lower() in [".csv", ".gz"]:
            try:
                df = pd.read_csv(f, compression="gzip" if f.suffix.lower() == ".gz" else None, dtype=object)
            except Exception:
                # 読み込みで失敗した場合はスキップ
                continue
            df["source_file"] = f.name
            dfs.append(df)
    if not dfs:
        return _empty_chat_df()
    all_df = pd.concat(dfs, ignore_index=True, sort=False)

    # normalize text column
    if "text" not in all_df.columns:
        text_cols = [c for c in all_df.columns if "text" in c.lower() or "message" in c.lower()]
        if text_cols:
            all_df = all_df.rename(columns={text_cols[0]: "text"})
        else:
            all_df["text"] = ""

    # parse timestamp if exists
    if "ts" in all_df.columns:
        try:
            all_df["ts_parsed"] = all_df["ts"].apply(lambda x: dateparser.parse(str(x)) if pd.notnull(x) else None)
        except Exception:
            all_df["ts_parsed"] = None
    else:
        all_df["ts_parsed"] = None

    # extract invoice mentions
    all_df["invoice"] = all_df["text"].astype(str).apply(extract_invoice_from_text)
    if "invoice" not in all_df.columns:
        all_df["invoice"] = None
    return all_df


def load_alibaba_messages():
    dfs = []
    if not ALIBABA_DIR.exists():
        return _empty_chat_df()
    for f in ALIBABA_DIR.glob("**/*"):
        if f.suffix.lower() in [".csv", ".gz", ".txt"]:
            try:
                if f.suffix.lower() in [".csv", ".gz"]:
                    df = pd.read_csv(f, compression="gzip" if f.suffix.lower() == ".gz" else None, dtype=object)
                else:
                    lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
                    df = pd.DataFrame({"text": lines})
            except Exception:
                continue
            df["source_file"] = f.name
            dfs.append(df)
    if not dfs:
        return _empty_chat_df()
    all_df = pd.concat(dfs, ignore_index=True, sort=False)

    # normalize text column
    if "text" not in all_df.columns:
        text_cols = [c for c in all_df.columns if "text" in c.lower() or "message" in c.lower()]
        if text_cols:
            all_df = all_df.rename(columns={text_cols[0]: "text"})
        else:
            all_df["text"] = ""

    # extract invoice mentions
    all_df["invoice"] = all_df["text"].astype(str).apply(extract_invoice_from_text)

    # timestamp parse (best-effort)
    time_cols = [c for c in all_df.columns if "time" in c.lower() or "date" in c.lower()]
    if time_cols:
        try:
            all_df["ts_parsed"] = all_df[time_cols[0]].apply(lambda x: dateparser.parse(str(x)) if pd.notnull(x) else None)
        except Exception:
            all_df["ts_parsed"] = None
    else:
        all_df["ts_parsed"] = None

    if "invoice" not in all_df.columns:
        all_df["invoice"] = None
    return all_df


def _find_invoice_in_row(row):
    for s in row:
        try:
            m = INVOICE_RE.search(str(s))
            if m:
                return m.group(1)
        except Exception:
            continue
    return None


def merge_data(companies, orders, slack_df, ali_df):
    # Prepare orders: try to ensure invoice column exists
    if orders is None:
        print("orders is None")
        orders = pd.DataFrame()

    # If an obvious invoice column exists, use it; otherwise attempt to detect
    candidate_invoice_cols = [c for c in orders.columns if "invoice" in c.lower() or "Invoice" in c or "TSE-" in c]
    if candidate_invoice_cols:
        # prefer an explicit 'invoice' name
        if "invoice" not in orders.columns and candidate_invoice_cols:
            orders = orders.rename(columns={candidate_invoice_cols[0]: "invoice"})
    else:
        # attempt: find a column that contains TSE pattern anywhere
        found = None
        for c in orders.columns:
            try:
                if orders[c].astype(str).str.contains("TSE-").any():
                    found = c
                    break
            except Exception:
                continue
        if found:
            orders = orders.rename(columns={found: "invoice"})

    if "invoice" not in orders.columns:
        # create invoice column by scanning any text columns (safe implementation)
        orders["invoice"] = orders.apply(lambda row: _find_invoice_in_row(row), axis=1)

    # Normalize company code: assume orders has '企業コード' or 'company_code' or 'Company Code'
    possible_company_cols = [c for c in orders.columns if "会社" in c or "企業" in c or "company" in c.lower()]
    if possible_company_cols:
        orders = orders.rename(columns={possible_company_cols[0]: "company_code"})

    # Ensure slack/ali have invoice column
    if "invoice" not in slack_df.columns:
        slack_df = slack_df.assign(invoice=None)
    if "invoice" not in ali_df.columns:
        ali_df = ali_df.assign(invoice=None)

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
        company_key = None
        for c in companies.columns:
            if "会社" in c or "企業" in c or "company" in c.lower() or "code" in c.low
