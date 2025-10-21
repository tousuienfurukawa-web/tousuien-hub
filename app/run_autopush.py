from flask import Flask, jsonify, request
import os
import json
import subprocess
from datetime import datetime

app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "ok",
        "message": "tousuien-hub autopush endpoint is alive.",
        "timestamp": datetime.utcnow().isoformat(),
        "routes": [
            "/",
            "/run_gpt_autopush",
            "/slack/thread/<invoice>",
            "/debug/paths"
        ]
    })

@app.route("/run_gpt_autopush", methods=["POST"])
def run_gpt_autopush():
    AUTH_TOKEN = os.getenv("AUTOPUSH_TOKEN")
    incoming = request.headers.get("Authorization")
    if AUTH_TOKEN and incoming != f"Bearer {AUTH_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401
    
    subprocess.Popen(["python", "gpt_autopush.py"])
    return jsonify({
        "status": "started",
        "message": "gpt_autopush.py triggered successfully.",
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route("/slack/thread/<invoice>", methods=["GET"])
def get_slack_thread(invoice):
    invoice = invoice.upper().strip()
    
    # データディレクトリのパス（Render環境対応）
    base_dir = os.path.join("/app", "data", "slack_threads")
    
    # ラフ入力補完
    if "-" not in invoice:
        if os.path.exists(base_dir):
            files = os.listdir(base_dir)
            candidates = [f.replace(".json", "") for f in files if invoice in f.upper()]
            if candidates:
                invoice = candidates[0]
            else:
                return jsonify({
                    "error": f"No invoice found matching keyword: {invoice}",
                    "searched_in": base_dir
                }), 404
        else:
            return jsonify({
                "error": "Data directory not found",
                "path": base_dir
            }), 500
    
    # JSONファイル読み込み
    json_path = os.path.join(base_dir, f"{invoice}.json")
    
    if not os.path.exists(json_path):
        return jsonify({
            "error": f"Thread not found: {invoice}",
            "path": json_path
        }), 404
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return jsonify({
            "error": f"Failed to read JSON: {str(e)}",
            "path": json_path
        }), 500
    
    return jsonify({
        "invoice": invoice,
        "count": data.get("count", len(data.get("messages", []))),
        "messages": data.get("messages", []),
        "source": "tousuien-hub"
    })

@app.route("/debug/paths", methods=["GET"])
def debug_paths():
    """デバッグ用：ディレクトリ構造を確認"""
    return jsonify({
        "cwd": os.getcwd(),
        "file_dir": os.path.dirname(os.path.abspath(__file__)),
        "exists_app_data": os.path.exists("/app/data"),
        "exists_data": os.path.exists("data"),
        "exists_dot_data": os.path.exists("./data"),
        "listdir_app": os.listdir("/app") if os.path.exists("/app") else "N/A",
        "listdir_cwd": os.listdir(os.getcwd())
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
