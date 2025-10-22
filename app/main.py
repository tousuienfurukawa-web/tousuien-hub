# -*- coding: utf-8 -*-
import os
import json
import zipfile
import re
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

app = FastAPI()
ZIP_FILE_PATH = Path("slack_export_latest.zip")

def normalize_invoice_text(text: str) -> str:
    # 全角スペース（ ）も除去するように修正
    return text.lower().replace("-", "").replace(" ", "").replace("_", "").replace(" ", "")

def format_timestamp(ts):
    try:
        dt = datetime.fromtimestamp(float(ts))
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return ts

def find_thread_files(all_files, ts):
    return [f for f in all_files if ("/thread" in f.lower() or "/threads" in f.lower()) and ts in f]

def extract_thread_from_zip(invoice_id):
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}

    normalized_invoice = normalize_invoice_text(invoice_id)
    with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
        all_files = z.namelist()
        matches = []

        for name in all_files:
            if not name.endswith(".json"):
                continue
            try:
                with z.open(name) as f:
                    data = json.load(f)
            except:
                continue
            if not isinstance(data, list):
                continue

            for msg in data:
                if not isinstance(msg, dict):
                    continue
                text = msg.get("text", "")
                if not isinstance(text, str) or normalized_invoice not in normalize_invoice_text(text):
                    continue

                ts = msg.get("ts", "")
                thread_ts = msg.get("thread_ts", ts)
                thread_messages = [msg]

                for other_msg in data:
                    if not isinstance(other_msg, dict):
                        continue
                    if other_msg.get("thread_ts", other_msg.get("ts", "")) == thread_ts and other_msg.get("ts") != ts:
                        thread_messages.append(other_msg)

                thread_files = find_thread_files(all_files, ts)
                for tf in thread_files:
                    try:
                        with z.open(tf) as thread_file:
                            thread_data = json.load(thread_file)
                            if isinstance(thread_data, list):
                                for tmsg in thread_data:
                                    if not isinstance(tmsg, dict):
                                        continue
                                    if tmsg.get("ts") != ts and not any(m.get("ts") == tmsg.get("ts") for m in thread_messages):
                                        thread_messages.append(tmsg)
                    except:
                        continue

                thread_messages.sort(key=lambda x: float(x.get("ts", 0)))
                matches.append({
                    "file": name,
                    "user": msg.get("user", "不明"),
                    "text": text,
                    "ts": ts,
                    "thread_ts": thread_ts,
                    "reply_count": msg.get("reply_count", 0),
                    "all_messages": thread_messages
                })

        return {
            "invoice": invoice_id,
            "messages": matches,
            "count": len(matches)
        }

def generate_gpt_summary(messages):
    all_texts = []
    for m in messages:
        all_texts.append(m.get("text", ""))
        for msg in m.get("all_messages", []):
            all_texts.append(msg.get("text", ""))

    joined_text = "\n".join(all_texts)

    status_parts = []
    if re.search(r"(出荷|発送)", joined_text):
        status_parts.append("出荷対応が進行中")
    if re.search(r"(DHL|UPS)", joined_text):
        status_parts.append("配送業者との調整済み")
    if re.search(r"(入金確認|USD\s?\d+)", joined_text):
        status_parts.append("入金確認済み")
    elif re.search(r"(入金|支払い)", joined_text):
        status_parts.append("入金未確認")
    if re.search(r"(PL|PackingList|Packing)", joined_text):
        status_parts.append("パッキングリスト修正完了")

    current_status = "、".join(status_parts) if status_parts else "受注関連のやり取りが確認されました"

    actions = []
    if re.search(r"(DHL|UPS)", joined_text):
        actions.append("📦 発送書類の最終確認が必要です")
    if re.search(r"(USD\s?\d+)", joined_text):
        actions.append("💰 入金額は確認済み。インボイスと照合済みです")
    elif re.search(r"(入金|支払い)", joined_text):
        actions.append("💰 入金額は未確認。インボイスと照合が必要です")
    else:
        actions.append("💰 入金状況の確認が必要です")
    if re.search(r"\d{4}-\d{2}-\d{2}", joined_text):
        actions.append("📅 納期の確認が必要です")
    if re.search(r"\d+\s?(tins|bags|個|缶)", joined_text):
        actions.append("📦 数量と在庫の確認が必要です")

    notes = []
    if re.search(r"(修正|訂正)", joined_text):
        notes.append("書類の修正履歴があります")

    return {
        "status": current_status,
        "actions": actions,
        "notes": notes
    }

@app.get("/slack/thread_html/{invoice_id}", response_class=HTMLResponse)
async def get_slack_thread_html(invoice_id: str, mode: str = Query(default="report")):
    # 注: 元のコードに含まれていた全角スペース（ ）を半角スペースに修正しています。
    # これらはインデントエラーの原因になる可能性があります。
    data = extract_thread_from_zip(invoice_id)
    if "error" in data:
        return f"<h3>❌ {data['error']}</h3>"
    if not data.get("messages"):
        return f"<h3>❌ スレッドが見つかりません（{invoice_id}）</h3>"

    msgs = data["messages"]
    first_msg = msgs[0] if msgs else {}
    gpt_info = generate_gpt_summary(msgs)

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans JP", sans-serif;
    background: #f5f5f5;
    color: #1a1a1a;
    padding: 20px;
    line-height: 1.6;
}}
.container {{
    max-width: 900px;
    margin: 0 auto;
    background: white;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    overflow: hidden;
}}
.header {{
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 24px;
}}
.header h1 {{ font-size: 24px; margin-bottom: 8px; }}
.header .meta {{ opacity: 0.9; font-size: 14px; }}
.section {{
    padding: 24px;
    border-bottom: 1px solid #e5e5e5;
}}
.section:last-child {{ border-bottom: none; }}
.section h2 {{
    font-size: 18px;
    margin-bottom: 16px;
    color: #667eea;
}}
.message {{
    background: #f9fafb;
    border-left: 3px solid #667eea;
    padding: 12px 16px;
    margin-bottom: 12px;
    border-radius: 4px;
}}
.message-header {{
    display: flex;
    justify-content: space-between;
    margin-bottom: 8px;
    font-size: 13px;
}}
.message-user {{
    font-weight: 600;
    color: #667eea;
}}
.message-time {{ color: #666; }}
.message-text {{
    color: #333;
    white-space: pre-wrap;
}}
.reply {{
    background: white;
    border-left: 3px solid #94a3b8;
    padding: 10px 14px;
    margin: 8px 0 8px 24px;
    border-radius: 4px;
}}
.status-box {{
    background: #f0f9ff;
    border-left: 4px solid #0ea5e9;
    padding: 16px;
    border-radius: 4px;
    margin-bottom: 16px;
}}
.action-list {{ list-style: none; }}
.action-list li {{
    padding: 8px 0;
    padding-left: 24px;
    position: relative;
}}
.action-list li:before {{
    content: "▸";
    position: absolute;
    left: 8px;
    color: #667eea;
}}
.note {{
    background: #fff7ed;
    border-left: 4px solid #fb923c;
    padding: 12px;
    border-radius: 4px;
    margin-top: 12px;
    font-size: 14px;
}}
</style>
""" # <-- 【修正点1】 f-string（三重引用符）をここで閉じる

    # 【修正点2】 HTMLResponseを返す必要があります
    # ※注意: このHTMLは<style>タグで終わっています。
    # 本来は、この """ の直前に </head><body>...</body></html> 
    # といったHTMLの本文が来るはずです。
    # HTMLの本文が欠落している場合は、この上の行に追加してください。
    return HTMLResponse(content=html)
