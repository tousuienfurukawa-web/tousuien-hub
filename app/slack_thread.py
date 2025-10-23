from flask import Blueprint, jsonify, request
import os
import json
import requests

bp = Blueprint("slack_thread", __name__)

SLACK_API_BASE = "https://slack.com/api"
SLACK_TOKEN = os.getenv("SLACK_BOT_TOKEN")  # ← 環境変数に設定推奨
DATA_DIR = os.path.join(os.getcwd(), "data", "slack_threads")


@bp.route("/slack/thread/<invoice>", methods=["GET"])
def get_slack_thread(invoice):
    """
    Slackスレッドを返すAPI（ページネーション対応＋ローカルキャッシュ付き）
    例:
      /slack/thread/TSE-CTP-005-25?refresh=true
    """
    invoice = invoice.upper().strip()
    refresh = request.args.get("refresh", "false").lower() == "true"
    mode = request.args.get("mode", "local")

    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    file_path = os.path.join(DATA_DIR, f"{invoice}.json")

    # --- キャッシュが存在する場合 ---
    if os.path.exists(file_path) and not refresh:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify({
            "source": "cache",
            "invoice": invoice,
            "count": data.get("count", len(data.get("messages", []))),
            "messages": data.get("messages", [])
        })

    # --- Slack APIから取得 ---
    if not SLACK_TOKEN:
        return jsonify({"error": "Missing SLACK_BOT_TOKEN env var"}), 500

    # ✅ チャンネルIDとthread_tsを特定する（あなたの既存ロジックに置き換え可）
    channel = _find_channel_by_invoice(invoice)
    thread_ts = _find_thread_ts(invoice)

    all_messages = []
    cursor = None
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    page = 1

    while True:
        params = {"channel": channel, "ts": thread_ts, "limit": 100}
        if cursor:
            params["cursor"] = cursor

        res = requests.get(f"{SLACK_API_BASE}/conversations.replies",
                           headers=headers, params=params).json()

        messages = res.get("messages", [])
        all_messages.extend(messages)
        cursor = res.get("response_metadata", {}).get("next_cursor")

        print(f"📑 Page {page}: {len(messages)} msgs")
        page += 1

        if not cursor:
            break

    # --- 保存 ---
    data = {
        "invoice": invoice,
        "count": len(all_messages),
        "messages": all_messages
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({
        "source": "slack_api",
        "invoice": invoice,
        "count": len(all_messages),
        "messages": all_messages
    })


# 以下は既存関数を呼び出す想定
def _find_channel_by_invoice(invoice: str) -> str:
    """受注番号からチャンネルIDを取得する"""
    # ここはあなたの環境での実装に合わせて書き換え
    return "C1234567890"  # 仮のチャンネルID


def _find_thread_ts(invoice: str) -> str:
    """受注番号からthread_tsを取得する"""
    # Slackスレッドのtimestampを返す処理（要実装）
    return "1726182734.000400"  # 仮のthread_ts
