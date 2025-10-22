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

def escape_html(text: str) -> str:
    return (text or "").replace("<", "&lt;").replace(">", "&gt;")

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
        
        debug_info = {
            "total_files": len(all_files),
            "json_files": len([f for f in all_files if f.endswith(".json")]),
            "thread_folders": len([f for f in all_files if "/thread" in f.lower()])
        }
        
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
                if not text:
                    continue
                text_norm = normalize_invoice_text(text)
                if normalized_invoice not in text_norm:
                    continue
                
                ts = msg.get("ts", "")
                thread_ts = msg.get("thread_ts", ts)
                thread_messages = [msg]
                
                for other_msg in data:
                    if not isinstance(other_msg, dict):
                        continue
                    other_thread_ts = other_msg.get("thread_ts", other_msg.get("ts", ""))
                    if other_thread_ts == thread_ts and other_msg.get("ts") != ts:
                        thread_messages.append(other_msg)
                
                thread_files = find_thread_files(all_files, ts)
                for tf in thread_files:
                    try:
                        with z.open(tf) as thread_file:
                            thread_data = json.load(thread_file)
                            if isinstance(thread_data, list):
                                for tmsg in thread_data:
                                    if isinstance(tmsg, dict) and not any(m.get("ts") == tmsg.get("ts") for m in thread_messages):
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
                    "all_messages": thread_messages,
                    "thread_files_found": len(thread_files)
                })
        
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
    
    return {"status": current_status, "actions": actions, "notes": notes}

# ---------------------------------------------------------------------
# reportモードを含むHTML生成関数
# ---------------------------------------------------------------------

def build_report_html(invoice_id, msgs, gpt_info):
    total_threads = len(msgs)
    total_messages = sum(len(m.get("all_messages", [])) for m in msgs)
    participants = sorted({m.get("user", "不明") for t in msgs for m in t.get("all_messages", [])})
    latest_ts = max((float(m.get("ts", 0)) for t in msgs for m in t.get("all_messages", []) if m.get("ts")), default=0)
    last_updated = format_timestamp(latest_ts)

    html = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
      <meta charset="UTF-8">
      <style>
        body {{font-family: "Noto Sans JP", sans-serif; background:#f8fafc; color:#0f172a; padding:24px; line-height:1.6;}}
        .card {{max-width:760px; margin:0 auto; background:white; border-radius:12px; padding:28px; box-shadow:0 10px 30px rgba(0,0,0,0.05);}}
        h1 {{font-size:24px; margin-bottom:8px;}}
        .summary {{background:#eff6ff; border-left:5px solid #3b82f6; padding:16px; border-radius:8px; margin-bottom:24px;}}
        .stat {{background:#f1f5f9; border-radius:8px; padding:12px; margin:8px 0;}}
        .footer {{text-align:right; color:#64748b; font-size:12px; margin-top:24px;}}
      </style>
    </head>
    <body>
    <div class="card">
      <h1>📋 {invoice_id}</h1>
      <p style="color:#475569;">最終更新: {last_updated}</p>
      <div class="summary">
        <strong>🧠 現状:</strong> {escape_html(gpt_info["status"])}<br>
        <strong>次のアクション:</strong><ul>{"".join(f"<li>{escape_html(a)}</li>" for a in gpt_info["actions"])}</ul>
      </div>
      <div class="stat"><strong>スレッド数:</strong> {total_threads}</div>
      <div class="stat"><strong>総メッセージ数:</strong> {total_messages}</div>
      <div class="stat"><strong>関係者:</strong> {", ".join(participants[:10])}</div>
      <div class="footer">Slackスレッド要約ビュー（{invoice_id}）</div>
    </div>
    </body></html>
    """
    return html

# ---------------------------------------------------------------------
# APIルート
# ---------------------------------------------------------------------

@app.get("/slack/thread_html/{invoice_id}", response_class=HTMLResponse)
async def get_slack_thread_html(invoice_id: str, mode: str = Query(default="normal")):
    data = extract_thread_from_zip(invoice_id)
    if "error" in data:
        return f"<h3>❌ {data['error']}</h3>"
    if not data.get("messages"):
        return f"<h3>❌ スレッドが見つかりません（{invoice_id}）</h3>"

    msgs = data["messages"]
    gpt_info = generate_gpt_summary(msgs)
    mode = (mode or "normal").lower()

    if mode == "report":
        return build_report_html(invoice_id, msgs, gpt_info)

    # 通常モードならreportの詳細版を返す（共通HTML利用）
    return build_report_html(invoice_id, msgs, gpt_info)

if __name__ == "__main__":
    import uvicorn
    if not ZIP_FILE_PATH.exists():
        print("⚠️ slack_export_latest.zip が見つかりません。")
    else:
        print("✅ ZIPファイル読み込み成功。")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
