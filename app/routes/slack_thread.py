from flask import Blueprint, jsonify, request
import os, json

bp = Blueprint('slack_thread', __name__)

@bp.route("/slack/thread/<invoice>", methods=["GET"])
def get_slack_thread(invoice):
    invoice = invoice.upper().strip()

    # --- ラフ入力補完ロジック ---
    if "-" not in invoice:
        files = os.listdir("data/slack_threads")
        candidates = [f.replace(".json", "") for f in files if invoice in f.upper()]
        if candidates:
            invoice = candidates[0]
        else:
            return jsonify({"message": f"No invoice found for {invoice}"}), 404

    # --- 該当スレッド読込 ---
    path = f"data/slack_threads/{invoice}.json"
    if not os.path.exists(path):
        return jsonify({"message": f"Thread not found: {invoice}"}), 404

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return jsonify({"invoice": invoice, "messages": data.get("messages", [])})
