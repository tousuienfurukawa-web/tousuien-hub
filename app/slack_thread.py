from flask import Blueprint, jsonify, request
import os
import json

# Blueprint定義
bp = Blueprint("slack_thread", __name__)

@bp.route("/slack/thread/<invoice>", methods=["GET"])
def get_slack_thread(invoice):
    """
    Slackスレッド情報を取得するAPI。
    ラフ入力（例: "ctp"）にも対応し、最も近いInvoiceを自動補完。
    """
    invoice = invoice.upper().strip()
    base_dir = os.path.join(os.getcwd(), "data", "slack_threads")

    # --- ラフ入力補完ロジック ---
    if "-" not in invoice:
        try:
            files = [f.replace(".json", "") for f in os.listdir(base_dir) if f.endswith(".json")]
        except FileNotFoundError:
            return jsonify({"error": "Slack threads directory not found"}), 500

        # 部分一致検索（例: "ctp" → "TSE-CTP-001-25"）
        candidates = [f for f in files if invoice in f.upper()]
        if candidates:
            invoice = candidates[0]  # 最初の一致を採用
        else:
            return jsonify({"message": f"No invoice found matching keyword: {invoice}"}), 404

    # --- JSONファイル読込 ---
    file_path = os.path.join(base_dir, f"{invoice}.json")
    if not os.path.exists(file_path):
        return jsonify({"message": f"Thread not found: {invoice}"}), 404

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON format"}), 500

    # --- 整形して返却 ---
    return jsonify({
        "invoice": invoice,
        "count": data.get("count", len(data.get("messages", []))),
        "messages": data.get("messages", [])
    })
