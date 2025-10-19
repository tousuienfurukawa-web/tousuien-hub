# -*- coding: utf-8 -*-
import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import time

# ======================
# Slackクライアント設定
# ======================
slack_token = os.getenv("SLACK_BOT_TOKEN")
client = WebClient(token=slack_token)

# ======================
# 対象チャンネル一覧
# ======================
channels = {
    "なんでもOK": "C033G42K9DG",
    "サンプル出荷": "C05G1KRTDF1",
    "groene-company": "C033G4QF8BD"
}

# ======================
# チャンネル同期処理
# ======================
def fetch_messages(channel_name, channel_id):
    try:
        print(f"🔄 {channel_name}（{channel_id}） のメッセージを取得中...")
        response = client.conversations_history(channel=channel_id, limit=200)
        messages = response.get("messages", [])
        print(f"✅ {channel_name}: {len(messages)} 件のメッセージを取得しました。\n")
        return messages

    except SlackApiError as e:
        print(f"⚠️ {channel_name} エラー: {e.response['error']}\n")
        return []

def main():
    all_messages = []

    for name, cid in channels.items():
        msgs = fetch_messages(name, cid)
        all_messages.extend(msgs)
        time.sleep(1)  # Slack API制限回避用のウェイト

    print(f"📦 合計 {len(all_messages)} 件のメッセージを収集しました。")

if __name__ == "__main__":
    main()
