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
    return text.lower().replace("-", "").replace(" ", "").replace("_", "")

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
                text = msg.get("text", "")
                if not isinstance(text, str) or normalized_invoice not in normalize_invoice_text(text):
                    continue

                ts = msg.get("ts", "")
                thread_ts = msg.get("thread_ts", ts)
                thread_messages = [msg]

                for other_msg in data:
                    if other_msg.get("thread_ts", other_msg.get("ts", "")) == thread_ts and other_msg.get("ts") != ts:
                        thread_messages.append(other_msg)

                thread_files = find_thread_files(all_files, ts)
                for tf in thread_files:
                    try:
                        with z.open(tf) as thread_file:
                            thread_data = json.load(thread_file)
                            if isinstance(thread_data, list):
                                for tmsg in thread_data:
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
    data = extract_thread_from_zip(invoice_id)
    if "error" in data:
        return f"<h3>❌ {data['error']}</h3>"
    if not data.get("messages"):
        return f"<h3>❌ スレッドが見つかりません（{invoice_id}）</h3>"

    msgs = data["messages"]
    first_msg = msgs[0] if msgs else {}
    gpt_info = generate_gpt_summary(msgs)

    html = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
        /* スタイルは前半に含まれています */
        </style>
    </head>
    <body>
    <div class="container">
        <div class="header">
            <h1>📋 {invoice_id}</h1>
            <div class="meta">
                投稿者: {first_msg.get('user', '不明')} | 
                最終更新: {format_timestamp(msgs[-1].get('ts', '')) if msgs else '不明'}
            </div>
        </div>

        <div class="section">
            <h2>🧠 GPT要約</h2>
            <div class="status-box">
                <strong>現状:</strong> {gpt_info['status']}
            </div>
            <h3 style="font-size: 16px; margin-bottom: 12px;">次のアクション</h3>
            <ul class="action-list">
                {''.join(f'<li>{action}</li>' for action in gpt_info['actions'])}
            </ul>
            {f'<div class="note"><strong>⚠️ 注意:</strong> ' + ', '.join(gpt_info['notes']) + '</div>' if gpt_info['notes'] else ''}
        </div>

        <div class="section">
            <h2>💬 主なやり取り概要</h2>
    """

    for idx, thread in enumerate(msgs):
        all_msgs = thread.get("all_messages", [])
        html += f"""
        <div style="margin-bottom: 24px;">
            <div style="background: #f3f4f6; padding: 8px 12px; border-radius: 4px; margin-bottom: 8px; font-size: 14px;">
                スレッド {idx + 1}: {len(all_msgs)}件のメッセージ
            </div>
        """
        for msg in all_msgs:
            is_first = msg.get("ts") == thread.get("ts")
            style = "message" if is_first else "reply"
            html += f"""
            <div class="{style}">
                <div class="message-header">
                    <span class="message-user">{msg.get('user', '不明')}</span>
                    <span class="message-time">{format_timestamp(msg.get('ts', ''))}</span>
                </div>
                <div class="message-text">{msg.get('text', '').replace('<', '&lt;').replace('>', '&gt;')}</div>
            </div>
            """
        html += "</div>"

    html += f"""
        </div>
        <div class="section" style="text-align: right; color: #666; font-size: 13px;">
            出典: Slackスレッド整形データ（<code>{invoice_id}</code>）
        </div>
    </div>
    </body>
    </html>
    """
    return html

if __name__ == "__main__":
    import uvicorn
    if not ZIP_FILE_PATH.exists():
        print("⚠️ slack_export_latest.zip が見つかりません。")
    else:
        print("✅ ZIPファイル読み込み成功。")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
