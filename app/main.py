# -*- coding: utf-8 -*-
import os
import zipfile
import json
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse

# ======================================================
# 🚀 FastAPI アプリケーション設定
# ======================================================
app = FastAPI()

# ZIPファイルのパス
ZIP_FILE_PATH = Path("slack_export_latest.zip")

# ======================================================
# 🧾 JSON出力（全フォルダ・旧形式対応）
# ======================================================
@app.get("/slack/thread/{invoice_id}")
async def get_slack_thread(invoice_id: str):
    """SlackエクスポートZIP内の全ファイル（旧形式・新形式両対応）から受注番号を検索しJSONで返す"""
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}

    try:
        with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
            matches = []
            all_files = z.namelist()

            for name in all_files:
                try:
                    decoded_name = name.encode("cp437").decode("utf-8", errors="ignore")
                except Exception:
                    decoded_name = name

                if not decoded_name.endswith(".json"):
                    continue

                try:
                    with z.open(name) as f:
                        data = json.load(f)
                except Exception:
                    continue

                if not isinstance(data, list):
                    continue

                for msg in data:
                    text = msg.get("text", "")
                    if invoice_id not in text:
                        continue

                    entry = {
                        "file": decoded_name,
                        "channel": decoded_name.split("/")[0] if "/" in decoded_name else "(root)",
                        "user": msg.get("user", ""),
                        "text": text,
                        "ts": msg.get("ts", ""),
                        "replies": []
                    }

                    ts = msg.get("ts")
                    if ts:
                        thread_path_new = f"{entry['channel']}/threads/{ts}.json"
                        thread_path_old = f"{ts}.json"

                        for tpath in [thread_path_new, thread_path_old]:
                            if tpath in all_files:
                                try:
                                    with z.open(tpath) as tf:
                                        replies = json.load(tf)
                                        if isinstance(replies, list):
                                            for r in replies:
                                                entry["replies"].append({
                                                    "user": r.get("user", ""),
                                                    "text": r.get("text", "")
                                                })
                                except Exception:
                                    pass

                    matches.append(entry)

            if not matches:
                return {"status": "not found", "invoice": invoice_id}

            return {
                "invoice": invoice_id,
                "count": len(matches),
                "messages": matches
            }

    except Exception as e:
        return {"error": str(e)}


# ======================================================
# 🌸 HTML出力（Slack風整形表示・スレッド返信対応）
# ======================================================
@app.get("/slack/thread_html/{invoice_id}", response_class=HTMLResponse)
async def get_slack_thread_html(invoice_id: str):
    """SlackエクスポートZIPのスレッドをHTML整形で表示（旧形式・新形式両対応）"""
    if not ZIP_FILE_PATH.exists():
        return "<h3>⚠️ ZIPファイルが見つかりません。</h3>"

    try:
        with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
            matches = []
            all_files = z.namelist()

            for name in all_files:
                try:
                    decoded_name = name.encode("cp437").decode("utf-8", errors="ignore")
                except Exception:
                    decoded_name = name

                if not decoded_name.endswith(".json"):
                    continue

                try:
                    with z.open(name) as f:
                        data = json.load(f)
                except Exception:
                    continue

                if not isinstance(data, list):
                    continue

                for msg in data:
                    text = msg.get("text", "")
                    if invoice_id not in text:
                        continue

                    entry = {
                        "file": decoded_name,
                        "channel": decoded_name.split("/")[0] if "/" in decoded_name else "(root)",
                        "user": msg.get("user", ""),
                        "text": text.replace("\n", "<br>"),
                        "ts": msg.get("ts", ""),
                        "replies": []
                    }

                    ts = msg.get("ts")
                    if ts:
                        thread_path_new = f"{entry['channel']}/threads/{ts}.json"
                        thread_path_old = f"{ts}.json"

                        for tpath in [thread_path_new, thread_path_old]:
                            if tpath in all_files:
                                try:
                                    with z.open(tpath) as tf:
                                        replies = json.load(tf)
                                        if isinstance(replies, list):
                                            for r in replies:
                                                entry["replies"].append({
                                                    "user": r.get("user", ""),
                                                    "text": r.get("text", "").replace("\n", "<br>")
                                                })
                                except Exception:
                                    pass

                    matches.append(entry)

            if not matches:
                return f"<h3>❌ 該当スレッドが見つかりません（{invoice_id}）</h3>"

            # --- HTML構築 ---
            html = f"<h2>🧾 受注番号：{invoice_id}</h2>"
            html += "<style>body{font-family:sans-serif;background:#fff;color:#333;} .msg{border:1px solid #ccc;border-radius:8px;padding:10px;margin:10px;background:#f9f9f9;} .reply{margin-left:20px;border-left:3px solid #ccc;padding-left:10px;background:#fff;} .user{font-weight:bold;color:#0366d6;} </style>"

            for msg in matches:
                ts = msg.get("ts", "")
                date_str = ""
                if ts:
                    date_str = datetime.fromtimestamp(float(ts.split('.')[0])).strftime("%Y-%m-%d %H:%M:%S")

                html += f"""
                <div class='msg'>
                    <p><span class='user'>👤 {msg['user']}</span> <small>({msg['channel']})</small></p>
                    <p>{msg['text']}</p>
                    <p><i>🕒 {date_str}</i></p>
                """

                if msg["replies"]:
                    html += "<div class='reply'><b>💬 スレッド返信:</b>"
                    for r in msg["replies"]:
                        html += f"<p><span class='user'>👤 {r['user']}</span> {r['text']}</p>"
                    html += "</div>"

                html += "</div>"

            return html

    except Exception as e:
        return f"<h3>⚠️ エラー: {e}</h3>"


# ======================================================
# 📦 ZIPダウンロード確認
# ======================================================
@app.get("/slack_export_latest.zip")
async def get_slack_export():
    """ZIPファイルをダウンロード"""
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}
    return FileResponse(
        path=str(ZIP_FILE_PATH),
        media_type="application/zip",
        filename="slack_export_latest.zip"
    )

# ======================================================
# 🚀 起動時ログ
# ======================================================
@app.on_event("startup")
async def startup_event():
    print("🚀 アプリケーション起動中...")
    if ZIP_FILE_PATH.exists():
        print(f"✅ ZIP found: {ZIP_FILE_PATH}")
    else:
        print("⚠️ ZIP file not found at startup")
