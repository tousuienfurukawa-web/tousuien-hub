from flask import Flask, jsonify, request
import os
import subprocess
from datetime import datetime

app = Flask(__name__)

# --- Blueprintをインポート・登録 ---
from app.slack_thread import bp as slack_bp
app.register_blueprint(slack_bp)

@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "ok",
        "message": "tousuien-hub autopush endpoint is alive.",
        "timestamp": datetime.utcnow().isoformat(),
        "routes": [
            "/",
            "/run_gpt_autopush",
            "/slack/thread/<invoice>"
        ]
    })

@app.route("/run_gpt_autopush", methods=["POST"])
def run_gpt_autopush():
    AUTH_TOKEN = os.getenv("AUTOPUSH_TOKEN")
    incoming = request.headers.get("Authorization")
    if AUTH_TOKEN and incoming != f"Bearer {AUTH_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401
    
    subprocess.Popen(["python", "app/gpt_autopush.py"])
    return jsonify({
        "status": "started",
        "message": "gpt_autopush.py triggered successfully.",
        "timestamp": datetime.utcnow().isoformat()
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
