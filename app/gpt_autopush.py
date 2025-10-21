# ===============================================================
# run_autopush.py
# ChatGPT（GPT-5）やWebhookなど外部からRenderをトリガーして、
# gpt_autopush.py をサーバー上で自動実行する小さなFlaskアプリ。
# ===============================================================

from flask import Flask, jsonify, request
import os
import subprocess
from datetime import datetime

app = Flask(__name__)

# ===============================================================
# 1. ヘルスチェック（動作確認用）
# ===============================================================
@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "ok",
        "message": "tousuien-hub autopush endpoint is alive.",
        "timestamp": datetime.utcnow().isoformat()
    })


# ===============================================================
# 2. GPT自動更新トリガーAPI
# ===============================================================
@app.route("/run_gpt_autopush", methods=["POST"])
def run_gpt_autopush():
    """
    ChatGPTやSlack、または他の外部サービスから
    POSTリクエストでこのエンドポイントを叩くことで、
    Renderサーバー上で gpt_autopush.py が実行される。
    """
    try:
        # --- セキュリティチェック（簡易トークン認証） ---
        AUTH_TOKEN = os.getenv("AUTOPUSH_TOKEN")
        incoming_token = request.headers.get("Authorization")

        if AUTH_TOKEN and incoming_token != f"Bearer {AUTH_TOKEN}":
            return jsonify({"error": "Unauthorized"}), 401

        # --- 実行開始 ---
        subprocess.Popen(["python", "app/gpt_autopush.py"])
        return jsonify({
            "status": "started",
            "message": "gpt_autopush.py is running on Render.",
            "timestamp": datetime.utcnow().isoformat()
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# ===============================================================
# 3. メインエントリポイント
# ===============================================================
if __name__ == "__main__":
    # Renderデフォルトポート（環境変数PORT）で起動
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
