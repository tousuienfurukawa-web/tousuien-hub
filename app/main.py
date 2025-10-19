# -*- coding: utf-8 -*-
import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import time

# Slackクライアント設定
slack_token = os.getenv("SLACK_BOT_TOKEN")

if not slack_token:
    print("❌ エラー: SLACK_BOT_TOKEN が設定されていません")
    exit(1)

client = WebClient(token=slack_token)

# 対象チャンネル一覧
channels = {
    "なんでもOK": "C033G42K9DG",
    "サンプル出荷": "C05G1KRTDF1",
    "groene-company": "C033G4QF8BD",
    "受注": "C03C62NBSDP"
}

def fetch_messages(channel_name, channel_id):
    try:
        print(f"🔄 {channel_name}（{channel_id}） のメッセージを取得中...")
        response = client.conversations_history(channel=channel_id, limit=200)
        messages = response.get("messages", [])
        print(f"✅ {channel_name}: {len(messages)} 件のメッセージを取得しました。")
        return me
