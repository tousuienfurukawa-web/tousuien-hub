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

# ======================================================
# 🚀 FastAPI アプリ設定
# ======================================================
app = FastAPI()

# Slackクライアント設定
slack_token = os.getenv("SLACK_BOT_TOKEN")
if not slack_token:
    print("⚠️ SLACK_BOT_TOKEN が未設定のため、Slack API 同期は無効です。")
    client = None
else:
    client = WebClient(token=slack_token)

# Slack対象チャンネル一覧
channels = {
    "なんでもOK": "C033G42K9DG",
    "サンプル出荷": "C05G1KRTDF1",
    "groene-company": "C033G4QF8BD",
    "受注": "C03C62NBSDP"
}

ZIP_FILE_PATH = Path("slack_export_latest.zip")

# ======================================================
# 🧾 Slack API 同期ロジック
# ======================================================
def fetch_messages(channel_name, channel_id):
    if not client:
        return []

    try:
        print(f"🔄 {channel_name}（{channel_id}） のメッセージを取得中...")
        response = client.conversations_history(channel=channel_id, limit=200)
        messages = response.get("messages", [])
        print(f"✅ {channel_name}: {len(messages)} 件のメッセージを取得しました。")
        return messages

    except SlackApiError as e:
        error_msg = e.response.get('error', 'unknown')
        print(f"⚠️ {channel_name} エラー: {error_msg}")
        return []

def sync_slack_messages():
    if not client:
        print("⚠️ Slack API機能が無効です。")
        return {"error": "Slack API disabled"}

    all_messages = []
    success_count = 0
    error_count = 0

    print("=" * 50)
    print("📡 Slack同期処理を開始します")
    print("=" * 50)

    for name, cid in channels.items():
        msgs = fetch_messages(name, cid)
        if msgs:
            all_messages.extend(msgs)
            success_count += 1
        else:
            error_count += 1
        time.sleep(1)

    print("=" * 50)
    print(f"📦 結果: 成功 {success_count}件 / エラー {error_count}件")
    print(f"📦 合計 {len(all_messages)} 件のメッセージを収集しました")
    print("=" * 50)

    return {
        "success": success_count,
        "error": error_count,
        "total_messages": len(all_messages)
    }

# ======================================================
# 🌐 FastAPI エンドポイント
# ======================================================
@app.get("/")
async def root():
    return {
        "status": "ok",
        "message": "Tousuien Hub API is running 🚀",
        "slack_api_enabled": slack_token is not None,
        "zip_file_found": ZIP_FILE_PATH.exists()
    }

@app.get("/sync")
async def trigger_sync():
    """Slack APIからメッセージ同期"""
    result = sync_slack_messages()
    return {"status": "completed", "result": result}

# ======================================================
# 📦 SlackエクスポートZIP検索（JSON出力）
# ======================================================
@app.get("/slack/thread/{invoice_id}")
async def get_slack_thread(invoice_id: str):
    """SlackエクスポートZIPから受注番号スレッドを検索"""
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}

    try:
        with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
            matches = []
            for name in z.namelist():
                if not name.endswith(".json"):
                    continue
                try:
                    with z.open(name) as f:
                        data = json.load(f)
                except Exception:
                    continue

                # 💡 想定外フォーマット（文字列・dictなど）はスキップ
                if not isinstance(data, list):
                    continue

                for msg in data:
                    if not isinstance(msg, dict):
                        continue
                    text = msg.get("text", "")
                    if invoice_id in text:
                        matches.append({
                            "file": name,
                            "user": msg.get("user"),
                            "text": text
                        })

            if not matches:
                return {"status": "not found", "invoice": invoice_id}
            return {"invoice": invoice_id, "count": len(matches), "messages": matches}
    except Exception as e:
        return {"error": str(e)}

# ======================================================
# 🌸 Slack風HTML出力（人間が読みやすい）
# ======================================================
@app.get("/slack/thread_html/{invoice_id}", response_class=HTMLResponse)
async def get_slack_thread_html(invoice_id: str):
    """SlackエクスポートZIPをSlack風HTMLに整形表示"""
    if not ZIP_FILE_PATH.exists():
        return "<h3>⚠️ ZIP file not found</h3>"

    with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
        matches = []
        for name in z.namelist():
            if not name.endswith(".json"):
                continue
            try:
                with z.open(name) as f:
                    data = json.load(f)
            except Exception:
                continue

            # 💡 想定外フォーマットスキップ
            if not isinstance(data, list):
                continue

            for msg in data:
                if not isinstance(msg, dict):
                    continue
                text = msg.get("text", "")
                if invoice_id in text:
                    matches.append({
                        "file": name,
                        "user": msg.get("user"),
                        "text": text.replace("\n", "<br>")
                    })

        if not matches:
            return f"<h3>❌ 該当スレッドが見つかりません（{invoice_id}）</h3>"

        html = f"<h2>🧾 受注番号：{invoice_id}</h2>"
        html += "<style>body{font-family:sans-serif;} .msg{border:1px solid #ccc;padding:10px;margin:10px;border-radius:8px;background:#f9f9f9;} .user{color:#0366d6;font-weight:bold;}</style>"
        for m in matches:
            html += f"<div class='msg'><p class='user'>👤 {m['user']}</p><p>{m['text']}</p><small>{m['file']}</small></div>"
        return html

# ======================================================
# 📦 ZIPファイル提供
# ======================================================
@app.get("/slack_export_latest.zip")
async def get_zip():
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}
    return FileResponse(
        path=str(ZIP_FILE_PATH),
        media_type="application/zip",
        filename="slack_export_latest.zip"
    )

# ======================================================
# 🏁 CLI実行時（ローカルで同期確認用）
# ======================================================
if __name__ == "__main__":
    sync_slack_messages()
