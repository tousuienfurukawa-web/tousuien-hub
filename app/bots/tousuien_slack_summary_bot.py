#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tousuien Slack Summary Bot (BGV対応・ウォームアップ付き安定版)
-------------------------------------------------------------
Author: Tousuien / ChatGPT-5
Version: 1.2.0
Date: 2025-10-22

概要:
Tousuien Hub API（https://tousuien-hub.onrender.com/slack/thread/...）から
Slackスレッドを取得し、GPT要約を抽出して一覧化します。

改良点:
- Renderスリープ対策としてウォームアップPingを自動実行
- タイムアウトを30秒に延長（cold start対応）
- 通信失敗時は最大3回リトライ
- 初回実行はテスト件数を減らして素早く確認可
"""

import re
import time
import requests
from typing import List, Dict, Tuple

# ============================================================
# 設定
# ============================================================

HUB_BASE = "https://tousuien-hub.onrender.com"
HUB_URL = f"{HUB_BASE}/slack/thread/"
YEARS = ["25", "26"]  # 年度サフィックス (-25=2025年, -26=2026年)
MAX_RETRY = 3         # リトライ回数
TIMEOUT = 30          # 秒
TEST_MODE = True      # Trueの間は最初の10件だけ取得（動作確認用）

# ============================================================
# 1️⃣ ウォームアップ Ping
# ============================================================

def warmup_ping():
    """
    Render（onrender.com）のスリープ対策。
    APIを事前に叩いてcold startを解除。
    """
    print("🔔 Sending warm-up ping to Tousuien Hub...")
    try:
        resp = requests.get(HUB_BASE, timeout=10)
        if resp.status_code == 200:
            print("✅ Hub warm-up successful.\n")
        else:
            print(f"⚠️ Hub responded with status {resp.status_code} (still waking up)\n")
    except Exception as e:
        print(f"⚠️ Warm-up ping failed: {e}\n")


# ============================================================
# 2️⃣ ユーティリティ関数
# ============================================================

def detect_invoice_patterns(keyword: str) -> List[str]:
    """
    年度対応のインボイス番号パターンを生成。
    例: 'BGV' → ['TSE-BGV-001-25', ..., '-26']
    """
    return [fr"TSE-{keyword.upper()}-\d{{3}}-{year}" for year in YEARS]


def get_slack_thread_html(invoice_id: str) -> str:
    """
    Tousuien Hub から対象スレッドHTMLを取得（タイムアウト＆リトライ対応）
    """
    url = f"{HUB_URL}{invoice_id}"
    for attempt in range(MAX_RETRY):
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except requests.Timeout:
            print(f"⏳ Timeout ({attempt+1}/{MAX_RETRY}): {invoice_id}, retrying in 5s...")
            time.sleep(5)
        except requests.RequestException as e:
            print(f"⚠️ Error fetching {invoice_id}: {e}")
            break
    return ""


# ============================================================
# 3️⃣ データ抽出・整形
# ============================================================

def fetch_slack_threads(keyword: str) -> List[Tuple[str, str]]:
    """
    指定キーワード（例: BGV）に該当するスレッドをすべて取得
    """
    print(f"🔍 Searching Tousuien Hub for keyword: {keyword.upper()}")
    threads = []
    for year in YEARS:
        limit = 10 if TEST_MODE else 200
        for i in range(1, limit):
            invoice_id = f"TSE-{keyword.upper()}-{i:03d}-{year}"
            html = get_slack_thread_html(invoice_id)
            if "GPT要約" in html:
                print(f"✅ Found: {invoice_id}")
                threads.append((invoice_id, html))
    if not threads:
        print(f"⚠️ No threads found for {keyword.upper()}.\n")
    return threads


def extract_gpt_summary(html: str) -> str:
    """
    SlackスレッドHTMLから GPT要約セクション（🧠）を抽出
    """
    match = re.search(r"<h2>🧠 GPT要約</h2>(.*?)<h2", html, re.S)
    if not match:
        return "（🧠 要約情報なし）"
    clean = re.sub(r"<[^>]+>", "", match.group(1))  # HTMLタグ除去
    return clean.strip()


def summarize_threads(keyword: str) -> List[Dict[str, str]]:
    """
    全スレッドを要約し、辞書配列で返す
    """
    threads = fetch_slack_threads(keyword)
    summaries = []
    for invoice_id, html in threads:
        summary = extract_gpt_summary(html)
        summaries.append({"Invoice": invoice_id, "Summary": summary})
    return summaries


# ============================================================
# 4️⃣ 出力整形
# ============================================================

def generate_summary_report(keyword: str) -> str:
    """
    最終的なBGVサマリ（テキスト）を生成
    """
    summaries = summarize_threads(keyword)
    if not summaries:
        return f"❌ {keyword.upper()} に該当するスレッドは見つかりませんでした。"

    lines = [f"\n📦 {keyword.upper()} 関連スレッドまとめ\n"]
    for s in summaries:
        lines.append(f"• {s['Invoice']}\n{s['Summary']}\n")
    lines.append("\n✅ 処理完了\n")
    return "\n".join(lines)


# ============================================================
# 5️⃣ メイン処理
# ============================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Tousuien Slack Summary Bot")
    parser.add_argument("keyword", help="取引先コード（例: BGV, IST, FRAなど）")
    args = parser.parse_args()

    print("🚀 Tousuien Slack Summary Bot started.\n")
    warmup_ping()
    report = generate_summary_report(args.keyword)
    print(report)
