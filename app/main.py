# -*- coding: utf-8 -*-
import os
import zipfile
import json
import time
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ======================================================
# 🚀 FastAPI アプリケーション設定
# ======================================================
app = FastAPI()

# Slackクライアント設定（オプショナル）
slack_token = os.getenv("SLACK_BOT_TOKEN")
if slack_token:
    client = WebClient(token=slack_token)
    print("✅ SLACK_BOT_TOKEN が設定されています。Slack API機能が有効です。")
else:
    client = None
    print("⚠️ SLACK_BOT_TOKEN が設定されていません。zipファイルのみ使用します。")

# 対象チャンネル一覧（Slack API使用時のみ）
channels = {
    "なんでもOK": "C033G42K9DG",
    "サンプル出荷": "C05G1KRTDF1",
    "groene-company": "C033G4QF8BD",
    "受注": "C03C62NBSDP"
}

# ======================================================
# ⚙️ Slack API 関連関数
# ======================================================
def fetch_messages(channel_name, channel_id):
    """Slack APIから特定チャンネルのメッセージを取得"""
    if not client:
        print("⚠️ Slack APIが無効です。SLACK_BOT_TOKENを設定してください。")
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
        
        if error_msg == "channel_not_found":
            print(f"   → チャンネルID {channel_id} が見つかりません")
        elif error_msg == "not_in_channel":
            print(f"   → Botがチャンネル {channel_id} に参加していません")
        return []

def sync_slack_messages():
    """Slack APIからメッセージを同期"""
    if not client:
        print("⚠️ Slack API機能が無効です")
        return
    
    print("=" * 50)
    print("📡 Slack同期処理を開始します")
    print("=" * 50)
    
    all_messages = []
    success_count = 0
    error_count = 0
    
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
    
    if error_count > 0:
        print("⚠️ 一部のチャンネルでエラーが発生しましたが、処理は完了しました")

# ======================================================
# 📦 ZIPファイル設定
# ======================================================
ZIP_FILE_PATH = Path("slack_export_latest.zip")

# ======================================================
# 🌐 基本エンドポイント
# ======================================================
@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {
        "status": "ok",
        "message": "Tousuien Hub API",
        "slack_api_enabled": client is not None,
        "zip_file_available": ZIP_FILE_PATH.exists()
    }

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

@app.get("/sync")
async def trigger_sync():
    """Slack APIからのメッセージ同期をトリガー"""
    if not client:
        return {"error": "SLACK_BOT_TOKEN not configured"}
    
    sync_slack_messages()
    return {"status": "sync completed"}

# ======================================================
# 🧾 SlackエクスポートZIP検索（JSON形式・スレッド返信対応）
# ======================================================
@app.get("/slack/thread/{invoice_id}")
async def get_slack_thread(invoice_id: str):
    """SlackエクスポートZIP内から受注番号スレッドを検索してJSONで返す（全フォルダ＋スレッド返信対応）"""
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}

    try:
        with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
            matches = []
            for name in z.namelist():
                decoded_name = name.encode("cp437").decode("utf-8", errors="ignore")
                if not decoded_name.endswith(".json"):
                    continue

                with z.open(name) as f:
                    try:
                        data = json.load(f)
                        for msg in data:
                            if invoice_id in msg.get("text", ""):
                                entry = {
                                    "channel": decoded_name.split("/")[0],
                                    "user": msg.get("user", ""),
                                    "text": msg.get("text", ""),
                                    "ts": msg.get("ts", ""),
                                    "replies": []
                                }

                                # --- スレッド返信を統合 ---
                                ts = msg.get("ts")
                                if ts:
                                    thread_path = f"{entry['channel']}/threads/{ts}.json"
                                    if thread_path in z.namelist():
                                        with z.open(thread_path) as tf:
                                            try:
                                                replies = json.load(tf)
                                                for r in replies:
                                                    entry["replies"].append({
                                                        "user": r.get("user", ""),
                                                        "text": r.get("text", "")
                                                    })
                                            except Exception:
                                                pass

                                matches.append(entry)
                    except Exception:
                        continue

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
# 🌸 SlackエクスポートZIP検索（HTML形式・スレッド返信対応）
# ======================================================
@app.get("/slack/thread_html/{invoice_id}", response_class=HTMLResponse)
async def get_slack_thread_html(invoice_id: str):
    """SlackエクスポートZIP内の受注スレッドをHTMLで表示（スレッド返信対応）"""
    if not ZIP_FILE_PATH.exists():
        return "<h3>⚠️ ZIPファイルが見つかりません。</h3>"

    try:
        with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
            matches = []
            for name in z.namelist():
                decoded_name = name.encode("cp437").decode("utf-8", errors="ignore")
                if not decoded_name.endswith(".json"):
                    continue
                with z.open(name) as f:
                    try:
                        data = json.load(f)
                        for msg in data:
                            if invoice_id in msg.get("text", ""):
                                matches.append({
                                    "channel": decoded_name.split("/")[0],
                                    "user": msg.get("user", ""),
                                    "text": msg.get("text", ""),
                                    "ts": msg.get("ts", "")
                                })
                    except Exception:
                        continue

        if not matches:
            return f"<h3>❌ 該当スレッドが見つかりません（{invoice_id}）</h3>"

        html = f"<h2>🧾 受注番号：{invoice_id}</h2>"

        for msg in matches:
            ts = msg.get("ts", "")
            text = msg["text"].replace("\n", "<br>")
            text = text.replace(":flag-th:", "🇹🇭")

            # --- スレッド返信を読み込む ---
            thread_replies = []
            thread_path = f"{msg['channel']}/threads/{ts}.json"
            if thread_path in z.namelist():
                with z.open(thread_path) as tf:
                    try:
                        replies = json.load(tf)
                        for r in replies:
                            thread_replies.append({
                                "user": r.get("user", ""),
                                "text": r.get("text", "").replace("\n", "<br>")
                            })
                    except Exception:
                        pass

            # --- HTML整形 ---
            date_str = ""
            if ts:
                date_str = datetime.fromtimestamp(float(ts.split('.')[0])).strftime("%Y-%m-%d %H:%M:%S")

            html += f"""
            <div style='border:1px solid #ccc; border-radius:8px; padding:10px; margin:10px; background:#f9f9f9;'>
                <p><b>チャンネル：</b>{msg['channel']}</p>
                <p><b>投稿者：</b>{msg['user']}</p>
                <p><b>本文：</b><br>{text}</p>
                <p><i>投稿日：{date_str}</i></p>
            """

            if thread_replies:
                html += "<div style='margin-left:20px; border-left:3px solid #ccc; padding-left:10px; background:#fff;'>"
                html += "<p><b>💬 スレッド返信:</b></p>"
                for r in thread_replies:
                    html += f"<p>👤 {r['user']}：{r['text']}</p>"
                html += "</div>"

            html += "</div>"

        return f"<body style='font-family: sans-serif; background:#fff; color:#333;'>{html}</body>"

    except Exception as e:
        return f"<h3>⚠️ エラー: {e}</h3>"

# ======================================================
# 🚀 起動時イベント
# ======================================================
@app.on_event("startup")
async def startup_event():
    print("🚀 アプリケーション起動中...")
    if ZIP_FILE_PATH.exists():
        print(f"✅ ZIP file found: {ZIP_FILE_PATH}")
    else:
        print(f"⚠️ No ZIP file found at {ZIP_FILE_PATH}")
