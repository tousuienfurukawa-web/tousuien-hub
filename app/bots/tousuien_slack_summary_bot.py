#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tousuien Slack Summary Bot (BGV対応・安定版)
-------------------------------------------
Author: Tousuien / ChatGPT-5
Version: 1.1.0
Date: 2025-10-22

概要:
Tousuien Hub API（https://tousuien-hub.onrender.com/slack/thread/...）から
Slackスレッドを取得し、GPT要約を抽出してレポート化します。

特徴:
- 「BGV」などのキーワード入力だけで該当スレッドを年度を跨いで検索
- 年度サフィックス (-25, -26) 対応
- タイムアウト＆例外処理つきでハング防止
- コマンドライン or API連携どちらでも実行可
"""

import re
import requests
from typing import List, Dict, Tuple

# Tousuien Hub API endpoint
HUB_URL = "https://tousuien-hub.onrender.com/slack/thread/"

# ============================================================
# 1️⃣ ユーティリティ関数群
# ============================================================

def detect_invoice_patterns(keyword: str) -> List[str]:
    """
    年度対応のインボイス番号パターンを生成。
    例: 'BGV' → ['TSE-BGV-001-25', 'TSE-BGV-002-25', ..., '-26']
    """
    years = ['25', '26']  # 対象年度（直近2期分）
    patterns = [fr"TSE-{keyword.upper()}-\d{{3}}-{year}" for year in years]
    return patterns


def get_slack_thread_html(invoice_id: str) -> str:
    """
    Tousuien Hub から対象スレッドHTMLを取得（タイムアウト＆例外対応）
    """
    url = f"{HUB_URL}{invoice_id}"
    try:
        resp = requests.get(url, timeout=10)  # 10秒でタイムアウト
        resp.raise_for_status()
        return resp.text
    except requests.Timeout:
        print(f"⏳ Timeout: {invoice_id}")
        return ""
    except requests.RequestException as e:
        print(f"⚠️ Error fetching {invoice_id}: {e}")
        return ""


# ============================================================
# 2️⃣ データ抽出・整形ロジック
# ============================================================

def fetch_slack_threads(keyword: str) -> List[Tuple[str, str]]:
    """
    指定キーワード（例: 'BGV'）に該当するスレッドをすべて取得
    """
    print(f"🔍 Searching Slack Hub for keyword: {keyword.upper()}")
    threads = []
    for year in ['25', '26']:
        for i in range(1, 200):  # 001〜199まで探索
            invoice_id = f"TSE-{keyword.upper()}-{i:03d}-{year}"
            html = get_slack_thread_html(invoice_id)
            if "GPT要約" in html:
                print(f"✅ Found: {invoice_id}")
                threads.append((invoice_id, html))
    if not threads:
        print(f"⚠️ No threads found for {keyword.upper()}.")
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
        summaries.append({
            "Invoice": invoice_id,
            "Summary": summary
        })
    return summaries


# ============================================================
# 3️⃣ 出力整形
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
# 4️⃣ メイン処理
# ============================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Tousuien Slack Summary Bot")
    parser.add_argument("keyword", help="取引先コード（例: BGV, IST, FRAなど）")
    args = parser.parse_args()

    print("🚀 Tousuien Slack Summary Bot started.\n")
    report = generate_summary_report(args.keyword)
    print(report)
