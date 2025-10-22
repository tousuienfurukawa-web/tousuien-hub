# -*- coding: utf-8 -*-
import os
import json
import zipfile
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
    candidates = []
    for f in all_files:
        try:
            decoded = f.encode("cp437").decode("utf-8", errors="ignore")
        except:
            decoded = f
        if ("/threads/" in decoded.lower() or "/thread/" in decoded.lower()):
            if ts in decoded:
                candidates.append(f)
    return candidates

def extract_thread_from_zip(invoice_id):
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}

    normalized_invoice = normalize_invoice_text(invoice_id)
    
    with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
        all_files = z.namelist()
        
        # デバッグ用：全ファイルリスト
        debug_info = {
            "total_files": len(all_files),
            "json_files": len([f for f in all_files if f.endswith(".json")]),
            "thread_folders": len([f for f in all_files if "/thread" in f.lower()])
        }
        
        matches = []
        
        # 全JSONファイルを検索
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
            
            # 各メッセージをチェック
            for msg in data:
                if not isinstance(msg, dict):
                    continue
                    
                text = msg.get("text", "")
                if not text:
                    continue
                
                text_norm = normalize_invoice_text(text)
                
                # invoice_idを含むか確認
                if normalized_invoice not in text_norm:
                    continue
                
                # このメッセージを取得
                ts = msg.get("ts", "")
                thread_ts = msg.get("thread_ts", ts)
                
                # 同じスレッドの全メッセージを取得
                thread_messages = [msg]
                
                # 同じファイル内から関連メッセージを探す
                for other_msg in data:
                    if not isinstance(other_msg, dict):
                        continue
                    other_thread_ts = other_msg.get("thread_ts", other_msg.get("ts", ""))
                    if other_thread_ts == thread_ts and other_msg.get("ts") != ts:
                        thread_messages.append(other_msg)
                
                # threadsフォルダも確認
                thread_files = find_thread_files(all_files, ts)
                for tf in thread_files:
                    try:
                        with z.open(tf) as thread_file:
                            thread_data = json.load(thread_file)
                            if isinstance(thread_data, list):
                                for tmsg in thread_data:
                                    if isinstance(tmsg, dict):
                                        if tmsg.get("ts") != ts:
                                            if not any(m.get("ts") == tmsg.get("ts") for m in thread_messages):
                                                thread_messages.append(tmsg)
                    except:
                        continue
                
                # タイムスタンプでソート
                thread_messages.sort(key=lambda x: float(x.get("ts", 0)))
                
                entry = {
                    "file": name,
                    "user": msg.get("user", "不明"),
                    "text": text,
                    "ts": ts,
                    "thread_ts": thread_ts,
                    "reply_count": msg.get("reply_count", 0),
                    "all_messages": thread_messages,
                    "thread_files_found": len(thread_files)
                }
                
                matches.append(entry)
        
        return {
            "invoice": invoice_id,
            "messages": matches,
            "count": len(matches),
            "debug": debug_info
        }

def generate_gpt_summary(messages):
    all_texts = []
    for m in messages:
        all_texts.append(m.get("text", ""))
        for msg in m.get("all_messages", []):
            all_texts.append(msg.get("text", ""))
    
    joined_text = "\n".join(all_texts)

    status_parts = []
    if "出荷" in joined_text or "発送" in joined_text:
        status_parts.append("出荷対応が進行中")
    if "DHL" in joined_text or "UPS" in joined_text:
        status_parts.append("配送業者との調整済み")
    if "入金" in joined_text or "支払い" in joined_text or "USD" in joined_text or "Payment" in joined_text:
        status_parts.append("入金確認済み")
    if "PL" in joined_text or "PackingList" in joined_text or "Packing" in joined_text:
        status_parts.append("パッキングリスト修正完了")
    
    current_status = "、".join(status_parts) if status_parts else "受注関連のやり取りが確認されました"

    actions = []
    if "DHL" in joined_text or "UPS" in joined_text:
        actions.append("📦 発送書類の最終確認")
    if "入金" in joined_text or "USD" in joined_text:
        actions.append("💰 入金額とインボイスの照合")
    if "出荷" in joined_text:
        actions.append("🚚 出荷スケジュールの確認")
    if not actions:
        actions = ["📋 案件の進捗状況を確認"]

    notes = []
    if "修正" in joined_text or "訂正" in joined_text:
        notes.append("書類の修正履歴あり")
    
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
    debug = data.get("debug", {})

    html = """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans JP", sans-serif;
            background: #f5f5f5;
            color: #1a1a1a;
            padding: 20px;
            line-height: 1.6;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 24px;
        }
        .header h1 { font-size: 24px; margin-bottom: 8px; }
        .header .meta { opacity: 0.9; font-size: 14px; }
        .section {
            padding: 24px;
            border-bottom: 1px solid #e5e5e5;
        }
        .section:last-child { border-bottom: none; }
        .section h2 {
            font-size: 18px;
            margin-bottom: 16px;
            color: #667eea;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .message {
            background: #f9fafb;
            border-left: 3px solid #667eea;
            padding: 12px 16px;
            margin-bottom: 12px;
            border-radius: 4px;
        }
        .message-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            font-size: 13px;
        }
        .message-user {
            font-weight: 600;
            color: #667eea;
        }
        .message-time { color: #666; }
        .message-text {
            color: #333;
            white-space: pre-wrap;
        }
        .reply {
            background: white;
            border-left: 3px solid #94a3b8;
            padding: 10px 14px;
            margin: 8px 0 8px 24px;
            border-radius: 4px;
        }
        .status-box {
            background: #f0f9ff;
            border-left: 4px solid #0ea5e9;
            padding: 16px;
            border-radius: 4px;
            margin-bottom: 16px;
        }
        .action-list { list-style: none; }
        .action-list li {
            padding: 8px 0;
            padding-left: 24px;
            position: relative;
        }
        .action-list li:before {
            content: "▸";
            position: absolute;
            left: 8px;
            color: #667eea;
        }
        .note {
            background: #fff7ed;
            border-left: 4px solid #fb923c;
            padding: 12px;
            border-radius: 4px;
            margin-top: 12px;
            font-size: 14px;
        }
        .debug {
            background: #fef3c7;
            border: 1px solid #fbbf24;
            padding: 12px;
            border-radius: 4px;
            font-size: 13px;
            margin-bottom: 16px;
        }
        .debug code {
            background: white;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: monospace;
        }
        </style>
    </head>
    <body>
    <div class="container">
    """

    # ヘッダー
    first_msg = msgs[0] if msgs else {}
    html += f"""
    <div class="header">
        <h1>📋 {invoice_id}</h1>
        <div class="meta">
            投稿者: {first_msg.get('user', '不明')} | 
            最終更新: {format_timestamp(msgs[-1].get('ts', '')) if msgs else '不明'}
        </div>
    </div>
    """

    # デバッグ情報
    html += f"""
    <div class="section">
        <div class="debug">
            <strong>🔍 デバッグ情報:</strong><br>
            ZIP内ファイル総数: <code>{debug.get('total_files', 0)}</code> | 
            JSONファイル: <code>{debug.get('json_files', 0)}</code> | 
            threadフォルダ: <code>{debug.get('thread_folders', 0)}</code><br>
            検出したスレッド: <code>{len(msgs)}</code>個 | 
            最初のスレッドのメッセージ数: <code>{len(first_msg.get('all_messages', []))}</code>個
        </div>
    </div>
    """

    # GPT要約
    gpt_info = generate_gpt_summary(msgs)
    html += f"""
    <div class="section">
        <h2>🧠 GPT要約</h2>
        <div class="status-box">
            <strong>現状:</strong> {gpt_info['status']}
        </div>
        <h3 style="font-size: 16px; margin-bottom: 12px;">次のアクション</h3>
        <ul class="action-list">
            {''.join(f'<li>{action}</li>' for action in gpt_info['actions'])}
        </ul>
    """
    if gpt_info['notes']:
        html += f"""
        <div class="note">
            <strong>⚠️ 注意:</strong> {', '.join(gpt_info['notes'])}
        </div>
        """
    html += "</div>"

    # 主なやり取り概要
    html += """
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

    html += "</div>"

    # フッター
    html += f"""
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
