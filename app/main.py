# -*- coding: utf-8 -*-
import os
import time
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from fastapi import FastAPI

# ======================================
# 🚀 FastAPI アプリ設定
# ======================================
app = FastAPI()

# Slackクライアント設定
slack_token = os.getenv("SLACK_BOT_TOKEN")
if not slack_token:
    print("⚠️ SLACK_BOT_TOKEN が設定されていません。Slack同期APIは無効です。")
    client = None
else:
    client = WebClient(token=slack_token)

# 対象チャンネル一覧
channels = {
    "なんでもOK": "C033G42K9DG",
    "サンプル出荷": "C05G1KRTDF1",
    "groene-company": "C033G4QF8BD",
    "受注": "C03C62NBSDP"
}

# ======================================
# 🧩 Slack メッセージ取得関数
# ======================================
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

        if error_msg == "channel_not_found":
            print(f"   → チャンネルID {channel_id} が見つかりません")
            print(f"   → Botがチャンネルに追加されているか確認してください")
        elif error_msg == "not_in_channel":
            print(f"   → Botがチャンネル {channel_id} に参加していません")

        return []

# ======================================
# 📦 Slack同期処理
# ======================================
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

# ======================================
# 🌐 FastAPI エンドポイント
# ======================================
@app.get("/")
async def root():
    """Renderヘルスチェック & ステータス確認"""
    return {
        "status": "ok",
        "slack_api_enabled": slack_token is not None,
        "message": "Tousuien Hub API is running 🚀"
    }

@app.get("/sync")
async def trigger_sync():
    """Slack同期を手動トリガー"""
    result = sync_slack_messages()
    return {"status": "completed", "result": result}

# ======================================
# 🏁 CLI実行時にも直接動かせるように
# ======================================
if __name__ == "__main__":
    sync_slack_messages()
