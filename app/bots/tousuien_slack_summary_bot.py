#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tousuien Slack Summary Bot (BGV対応版)
---------------------------------------
Author: Tousuien / ChatGPT-5
Version: 1.0.0
Date: 2025-10-22

概要:
Slackスレッド (https://tousuien-hub.onrender.com) から
「TSE-XXX-###-YY」形式の受注データを取得し、
GPT要約を整形して出力する自動サマリBotです。

特徴:
- "BGV" のようなキーワード入力だけで該当スレッドを自動探索
- 年度サフィックス (-25, -26) に対応
- GPT要約セクションを抽出し、自然言語で統合出力
- Slackメッセージ用 or PDFレポート用フォーマット拡張が可能
"""

import re
import requests
from typing import List, Dict, Tuple

# Tousuien Hub API endpoint
HUB_URL = "https://tousuien-hub.onrender.com/slack/thread/"

# -----------------------------
# 1️⃣ ユーティリティ関数群
# -----------------------------

def detect_invoice_patterns(keyword: str) -> List[str]:
    """
    年度対応のインボイス番号パターンを生成。
    例: 'BGV' -> ['TSE-BGV-001-25', 'TSE-BGV-002-25', ..., '-26']
    """
    years = ['25', '26']  # 直近2年度分を対象
    patterns = [fr"TSE-{keyword.upper()}-\d{{3}}-{year}" for year in years]
    return patterns


def get_slack_thread_html(invoice_id: str) -> str:
    """
    Tousuien Hub から対象スレッドのHTMLを取得
    """
    url = f"{HUB_URL}{invoice_id}"
    resp = requests.get(url)
    if resp.status_code != 200:
        raise ValueError(f"⚠️ Slackスレッド取得エラー: {invoice_id}")
    return resp.text


# -----------------------------
# 2️⃣ データ抽出・整形ロジック
# -----------------------------

def fetch_slack_threads(keyword: str) -> List[Tuple[str, str]]:
    """
    指定キーワード（例: 'BGV'）に該当するスレッドをすべて取得
    """
    patterns = detect_invoice_patterns(keyword)
    threads = []
    for year in ['25', '26']:
        for i in range(1, 200):  # 001〜199まで探索
            invoice_id = f"TSE-{keyword.upper()}-{i:03d}-{year}"
            try:
                html = get_slack_thread_html(invoice_id)
                if "GPT要約" in html:
                    threads.append((invoice_id, html))
            except Exception:
                continue
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


# -----------------------------
# 3️⃣ 出力整形
# -----------------------------

def generate_summary_report(keyword: str) -> str:
    """
    最終的なBGVサマリ（テキスト）を生成
    """
    summaries = summarize_threads(keyword)
    if not summaries:
        return f"❌ {keyword.upper()} に該当するスレッドは見つかりませんでした。"

    lines = [f"📦 {keyword.upper()} 関連スレッドまとめ\n"]
    for s in summaries:
        lines.append(f"• {s['Invoice']}\n{s['Summary']}\n")
    return "\n".join(lines)


# -----------------------------
# 4️⃣ メイン処理
# -----------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Tousuien Slack Summary Bot")
    parser.add_argument("keyword", help="取引先コード（例: BGV, IST, FRAなど）")
    args = parser.parse_args()

    print("🔍 Slackスレッドを検索中...\n")
    report = generate_summary_report(args.keyword)
    print(report)
