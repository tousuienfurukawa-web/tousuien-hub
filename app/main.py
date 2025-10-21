# -*- coding: utf-8 -*-
import os
import json
import zipfile
import time
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

app = FastAPI()

# Slack設定
slack_token = os.getenv("SLACK_BOT_TOKEN")
client = WebClient(token=slack_token) if slack_token else None

channels = {
    "なんでもOK": "C033G42K9DG",
    "サンプル出荷": "C05G1KRTDF1",
    "groene-company": "C033G4QF8BD",
    "受注": "C03C62NBSDP"
}

ZIP_FILE_PATH = Path("slack_export_latest.zip")

# ========================= Slack同期 =========================
def fetch_messages(channel_name, channel_id):
    if not client:
        return []
    try:
        res = client.conversations_history(channel=channel_id, limit=200)
        return res.get("messages", [])
    except SlackApiError as e:
        print(f"⚠️ {channel_name}: {e.response.get('error')}")
        return []

def sync_slack_messages():
    all_msgs, success, error = [], 0, 0
    for name, cid in channels.items():
        msgs = fetch_messages(name, cid)
        if msgs:
            all_msgs.extend(msgs)
            success += 1
        else:
            error += 1
        time.sleep(1)
    return {"success": success, "error": error, "total": len(all_msgs)}

@app.get("/")
async def root():
    return {
        "status": "ok",
        "zip_found": ZIP_FILE_PATH.exists(),
        "slack_api_enabled": client is not None
    }

@app.get("/sync")
async def sync():
    return sync_slack_messages()

# ========================= スレッド検索(JSON) =========================
@app.get("/slack/thread/{invoice_id}")
async def get_thread(invoice_id: str):
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP not found"}

    try:
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
                    if invoice_id not in text:
                        continue

                    entry = {
                        "file": name,
                        "channel": name.split("/")[0] if "/" in name else "(root)",
                        "user": msg.get("user", ""),
                        "text": text,
                        "ts": msg.get("ts", ""),
                        "replies": []
                    }

                    ts = msg.get("ts")
                    if ts:
                        # replies探索
                        thread_path_new = f"{entry['channel']}/threads/{ts}.json"
                        thread_path_old = f"{ts}.json"
                        for tpath in [thread_path_new, thread_path_old]:
                            if tpath in all_files:
                                try:
                                    with z.open(tpath) as tf:
                                        replies = json.load(tf)
                                        if isinstance(replies, list):
                                            for r in replies:
                                                if not isinstance(r, dict):
                                                    continue
                                                entry["replies"].append({
                                                    "user": r.get("user", ""),
                                                    "text": r.get("text", "")
                                                })
                                except Exception as e:
                                    print(f"⚠️ replies読込失敗: {tpath} ({e})")
                    matches.append(entry)

            if not matches:
                return {"status": "not found", "invoice": invoice_id}

            return {"invoice": invoice_id, "count": len(matches), "messages": matches}

    except Exception as e:
        return {"error": str(e)}

# ========================= Slack風HTML出力 =========================
@app.get("/slack/thread_html/{invoice_id}", response_class=HTMLResponse)
async def get_thread_html(invoice_id: str):
    if not ZIP_FILE_PATH.exists():
        return "<h3>⚠️ ZIP file not found</h3>"

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
                if invoice_id not in text:
                    continue

                entry = {
                    "file": name,
                    "channel": name.split("/")[0] if "/" in name else "(root)",
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
                                            if not isinstance(r, dict):
                                                continue
                                            entry["replies"].append({
                                                "user": r.get("user", ""),
                                                "text": r.get("text", "").replace("\n", "<br>")
                                            })
                            except Exception:
                                continue
                matches.append(entry)

        if not matches:
            return f"<h3>❌ 該当スレッドが見つかりません（{invoice_id}）</h3>"

        html = f"<h2>🧾 受注番号：{invoice_id}</h2>"
        html += """
        <style>
        body{font-family: 'Segoe UI',sans-serif;line-height:1.6;background:#f4f4f9;padding:20px;}
        .msg{background:#fff;border-radius:10px;margin:15px 0;padding:12px 18px;box-shadow:0 1px 3px rgba(0,0,0,0.1);}
        .user{color:#0073e6;font-weight:bold;margin-bottom:4px;}
        .reply{margin-left:30px;background:#f8f8ff;}
        .file{font-size:0.8em;color:#888;}
        </style>
        """
        for m in matches:
            html += f"<div class='msg'><div class='user'>👤 {m['user']}</div><div>{m['text']}</div><div class='file'>{m['file']}</div>"
            if m['replies']:
                html += "<div style='margin-top:8px;'><b>💬 スレッド返信:</b>"
                for r in m['replies']:
                    html += f"<div class='msg reply'><div class='user'>↪ {r['user']}</div><div>{r['text']}</div></div>"
                html += "</div>"
            html += "</div>"
        return html

# ========================= ZIP提供 =========================
@app.get("/slack_export_latest.zip")
async def get_zip():
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP not found"}
    return FileResponse(str(ZIP_FILE_PATH), media_type="application/zip", filename="slack_export_latest.zip")

if __name__ == "__main__":
    sync_slack_messages()
