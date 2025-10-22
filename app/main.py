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

# ------------------------------------------------------------
# 🔹 SlackユーザーID → 表示名マッピング
# ------------------------------------------------------------
USER_MAP = {
    "U0331FWGQRM": "（例）山田 太郎",
    "U0331FZTHEK": "（例）佐藤 花子",
    "U041RJKV5JA": "（例）中村 一郎",
    "U05KGS6HN9H": "（例）田中 美咲",
    "U0606SPN4BW": "（例）鈴木 健",
    "U082R7FU1V": "（例）高橋 優",
    "U08U8MMTH43": "（例）渡辺 真理",
}

def resolve_user_name(user_id: str) -> str:
    if not user_id:
        return "不明"
    return USER_MAP.get(user_id, user_id)

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
# 🔹 Slack ZIPからスレッド抽出（堅牢版）
# ------------------------------------------------------------
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
            except Exception as e:
                continue

            # ✅ JSONがlistでない場合スキップ
            if not isinstance(data, list):
                continue

            for msg in data:
                # ✅ dict型でない要素をスキップ
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

                # スレッド返信を集約
                for other_msg in data:
                    if not isinstance(other_msg, dict):
                        continue
                    other_thread_ts = other_msg.get("thread_ts", other_msg.get("ts"))
                    if other_thread_ts == thread_ts and other_msg.get("ts") != ts:
                        thread_messages.append(other_msg)

                matches.append({
                    "user": resolve_user_name(msg.get("user")),
                    "text": text,
                    "ts": ts,
                    "thread_ts": thread_ts,
                    "all_messages": thread_messages,
                })

        return {"invoice": invoice_id, "messages": matches}

# ------------------------------------------------------------
# 🔹 要約生成
# ------------------------------------------------------------
def generate_gpt_summary(messages):
    all_texts = []
    for m in messages:
        all_texts.append(m.get("text", ""))
        for msg in m.get("all_messages", []):
            all_texts.append(msg.get("text", ""))
    joined = "\n".join(all_texts)

    if any(x in joined for x in ["出荷完了", "発送完了"]):
        status = "✅ 出荷完了済み"
    else:
        status = "⚠️ 明確な進捗報告がSlack上に見つかりません"

    actions = ["📋 スレッド内容を確認してください（AIによる推測なし）"]
    return {"status": status, "actions": actions, "notes": []}

# ------------------------------------------------------------
# 🔹 HTML生成（report / raw両対応）
# ------------------------------------------------------------
def build_report_html(invoice_id, msgs, gpt_info):
    total_threads = len(msgs)
    total_messages = sum(len(m.get("all_messages", [])) for m in msgs)
    participants = sorted({resolve_user_name(m.get("user")) for t in msgs for m in t.get("all_messages", [])})
    latest_ts = max((float(m.get("ts", 0)) for t in msgs for m in t.get("all_messages", []) if m.get("ts")), default=0)
    last_updated = format_timestamp(latest_ts)

    html = f"""
    <!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8">
    <style>
      body{{font-family:"Noto Sans JP",sans-serif;background:#f8fafc;color:#0f172a;padding:24px;line-height:1.6;}}
      .card{{max-width:760px;margin:0 auto;background:white;border-radius:12px;padding:28px;box-shadow:0 10px 30px rgba(0,0,0,0.05);}}
      h1{{font-size:24px;margin-bottom:8px;}}
      .summary{{background:#eff6ff;border-left:5px solid #3b82f6;padding:16px;border-radius:8px;margin-bottom:24px;}}
      .stat{{background:#f1f5f9;border-radius:8px;padding:12px;margin:8px 0;}}
      .footer{{text-align:right;color:#64748b;font-size:12px;margin-top:24px;}}
    </style></head><body>
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

def build_raw_html(invoice_id, msgs):
    html_msgs = ""
    for t in msgs:
        html_msgs += f"<h3>💬 スレッド開始: {escape_html(t['text'])}</h3>"
        for m in t["all_messages"]:
            user = resolve_user_name(m.get("user"))
            ts = format_timestamp(m.get("ts"))
            text = escape_html(m.get("text", ""))
            html_msgs += f"<div style='margin:6px 0;padding:4px;border-bottom:1px solid #eee;'><strong>{user}</strong> ({ts})<br>{text}</div>"
    html = f"""
    <!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8">
    <style>body{{font-family:'Noto Sans JP',sans-serif;padding:20px;}}</style></head>
    <body><h1>📋 {invoice_id}</h1>{html_msgs}
    <hr><p style='color:#64748b;font-size:12px;'>mode=raw (Tousuien Hub)</p></body></html>
    """
    return html

# ------------------------------------------------------------
# 🔹 エンドポイント
# ------------------------------------------------------------
@app.get("/slack/thread_html/{invoice_id}", response_class=HTMLResponse)
async def get_slack_thread_html(invoice_id: str, mode: str = Query(default="report")):
    data = extract_thread_from_zip(invoice_id)
    if "error" in data:
        return f"<h3>❌ {data['error']}</h3>"
    if not data.get("messages"):
        return f"<h3>❌ スレッドが見つかりません（{invoice_id}）</h3>"

    msgs = data["messages"]

    if mode == "raw":
        return build_raw_html(invoice_id, msgs)
    else:
        gpt_info = generate_gpt_summary(msgs)
        return build_report_html(invoice_id, msgs, gpt_info)

# ------------------------------------------------------------
# 🔹 アプリ起動
# ------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    if not ZIP_FILE_PATH.exists():
        print("⚠️ slack_export_latest.zip が見つかりません。")
    else:
        print("✅ ZIPファイル読み込み成功。")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
