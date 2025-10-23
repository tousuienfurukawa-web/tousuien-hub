# -*- coding: utf-8 -*-
import os
import json
import zipfile
import requests
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

# ✅ 修正版（同一フォルダ構成に合わせたimport）
from user_map import resolve_user_name
from gpt5_summary import generate_slack_summary

app = FastAPI()
ZIP_FILE_PATH = Path("slack_export_latest.zip")

# ------------------------------------------------------------
# 🔹 基本ユーティリティ
# ------------------------------------------------------------
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

# ------------------------------------------------------------
# 🔹 Slackスレッド抽出（Render API優先 + ZIPフォールバック）
# ------------------------------------------------------------
def extract_thread_from_zip(invoice_id):
    normalized_invoice = normalize_invoice_text(invoice_id)
    render_url = f"https://tousuien-hub.onrender.com/api/slack_threads/{invoice_id}.json"

    # ✅ Render API経由で取得を試行
    try:
        res = requests.get(render_url, timeout=5)
        if res.status_code == 200:
            print(f"[INFO] Fetched from Render API: {invoice_id}")
            return res.json()
    except Exception as e:
        print(f"[WARN] Render API fetch failed: {e}")

    # ✅ フォールバック：ZIPから抽出
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}

    print(f"[INFO] Fallback to ZIP extraction for: {invoice_id}")
    with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
        all_files = z.namelist()
        matches = []

        for name in all_files:
            if not name.endswith(".json"):
                continue
            try:
                with z.open(name) as f:
                    data = json.load(f)
            except Exception:
                continue
            if not isinstance(data, list):
                continue

            for msg in data:
                if not isinstance(msg, dict):
                    continue
                text = msg.get("text", "")
                if not text:
                    continue
                if normalized_invoice not in normalize_invoice_text(text):
                    continue

                ts = msg.get("ts", "")
                thread_ts = msg.get("thread_ts", ts)
                thread_messages = [msg]

                # スレッド内の返信も収集
                for other_msg in data:
                    if not isinstance(other_msg, dict):
                        continue
                    other_thread_ts = other_msg.get("thread_ts", other_msg.get("ts"))
                    if other_thread_ts == thread_ts and other_msg.get("ts") != ts:
                        thread_messages.append(other_msg)

                # 🔹 各メッセージの user_id → 実名変換
                thread_messages = [
                    {**m, "user": resolve_user_name(m.get("user"))} for m in thread_messages
                ]

                matches.append({
                    "user": resolve_user_name(msg.get("user")),
                    "text": text,
                    "ts": ts,
                    "thread_ts": thread_ts,
                    "all_messages": thread_messages,
                })

        return {"invoice": invoice_id, "messages": matches}

# ------------------------------------------------------------
# 🔹 HTML生成（raw, report両方を共用）
# ------------------------------------------------------------
def build_raw_html(invoice_id, msgs):
    html_msgs = ""
    for t in msgs:
        html_msgs += f"<h2>💬 スレッド開始: {escape_html(t['text'])}</h2>"
        for m in t["all_messages"]:
            user = m.get("user")
            ts = format_timestamp(m.get("ts"))
            text = escape_html(m.get("text", ""))
            html_msgs += f"""
            <div class='msg'>
              <div class='bubble'>
                <div class='meta'><strong>{user}</strong> <span>{ts}</span></div>
                <div class='text'>{text}</div>
              </div>
            </div>
            """
    html = f"""
    <div>
      <h1>📋 {invoice_id}</h1>
      {html_msgs}
      <hr>
      <p style='color:#64748b;font-size:12px;'>mode=raw (Tousuien Hub)</p>
    </div>
    """
    return html

def build_report_html(invoice_id, msgs, gpt_info):
    total_threads = len(msgs)
    total_messages = sum(len(m.get("all_messages", [])) for m in msgs)
    participants = sorted({m.get("user") for t in msgs for m in t.get("all_messages", [])})
    latest_ts = max((float(m.get("ts", 0)) for t in msgs for m in t.get("all_messages", []) if m.get("ts")), default=0)
    last_updated = format_timestamp(latest_ts)
    html = f"""
      <div class="card">
        <h2>🧠 要約ビュー: {invoice_id}</h2>
        <p style="color:#475569;">最終更新: {last_updated}</p>
        <div class="summary">
          <strong>🧠 GPT-5要約:</strong><br>
          {escape_html(gpt_info["status"])}
        </div>
        <div class="stat"><strong>スレッド数:</strong> {total_threads}</div>
        <div class="stat"><strong>総メッセージ数:</strong> {total_messages}</div>
        <div class="stat"><strong>関係者:</strong> {", ".join(participants[:10])}</div>
        <div class="footer">Slackスレッド要約ビュー（{invoice_id}）</div>
      </div>
    """
    return html

# ------------------------------------------------------------
# 🔹 エンドポイント（raw＋GPT-5要約の統合表示）
# ------------------------------------------------------------
@app.get("/slack/thread_html/{invoice_id}", response_class=HTMLResponse)
async def get_slack_thread_html(invoice_id: str):
    data = extract_thread_from_zip(invoice_id)
    if "error" in data:
        return f"<h3>❌ {data['error']}</h3>"
    if not data.get("messages"):
        return f"<h3>❌ スレッドが見つかりません（{invoice_id}）</h3>"

    msgs = data["messages"]
    # Raw(全文)表示
    raw_html_section = build_raw_html(invoice_id, msgs)
    # GPT-5要約
    all_thread_messages = []
    for m in msgs:
        all_thread_messages.extend(m.get("all_messages", []))
    gpt_result = generate_slack_summary(invoice_id, all_thread_messages)
    gpt_info = {
        "status": gpt_result.get("summary", "⚠️ 要約生成中にエラーが発生しました"),
        "actions": ["📋 全文表示は上記"],
        "notes": []
    }
    summary_html_section = build_report_html(invoice_id, msgs, gpt_info)

    # 2つを1ページで返す
    combined_html = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
      <meta charset="UTF-8">
      <title>{invoice_id} | Slackスレッド全ビュー</title>
      <style>
        body {{ font-family:"Noto Sans JP",sans-serif; background:#f8fafc; color:#0f172a; }}
        .container {{ max-width: 900px; margin: auto; padding:24px; }}
        .section-title {{ margin-top:32px; font-size:22px; }}
        .divider {{ margin:32px 0 16px 0; border-bottom:2px solid #e5e7eb; }}
        .card {{ background:white;border-radius:12px;padding:28px;box-shadow:0 10px 30px rgba(0,0,0,0.05); }}
        .summary {{background:#eff6ff;border-left:5px solid #3b82f6;padding:16px;border-radius:8px;margin-bottom:24px;white-space:pre-wrap;}}
        .stat {{background:#f1f5f9;border-radius:8px;padding:12px;margin:8px 0;}}
        .footer {{text-align:right;color:#64748b;font-size:12px;margin-top:24px;}}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="section-title">💬 全文表示（Raw）</div>
        <div class="divider"></div>
        {raw_html_section}
        <div class="section-title">🧠 GPT-5要約</div>
        <div class="divider"></div>
        {summary_html_section}
      </div>
    </body>
    </html>
    """
    return HTMLResponse(content=combined_html)

# ------------------------------------------------------------
# 🔹 アプリ起動
# ------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
