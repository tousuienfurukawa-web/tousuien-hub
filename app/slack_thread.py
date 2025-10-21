from flask import Blueprint, jsonify
import os
import json

# Blueprintの登録
bp = Blueprint("slack_thread", __name__)

@bp.route("/slack/thread/<invoice>", methods=["GET"])
def get_slack_thread(invoice):
    """
    Slackスレッド情報を返すAPI。
    例:
      /slack/thread/TSE-IST-003-25  → 完全一致検索
      /slack/thread/ctp             → ラフ検索補完（TSE-CTP-001-25を返す）
    """
    invoice = invoice.upper().strip()

    # スレッドデータ格納ディレクトリ
    base_dir = os.path.join(os.getcwd(), "data", "slack_threads")

    if not os.path.exists(base_dir):
        return jsonify({
            "error": "Data directory not found",
            "path": base_dir
        }), 500

    # --- ラフ入力補完 ---
    if "-" not in invoice:
        try:
            files = os.listdir(base_dir)
            candidates = [
                f.replace(".json", "")
                for f in files
                if invoice in f.upper()
            ]
            if not candidates:
                return jsonify({
                    "message": f"No invoice found matching keyword: {invoice}"
                }), 404

            # 最初に一致したスレッドを採用
            invoice = candidates[0]
        except Exception as e:
            return jsonify({
                "error": "Error during fuzzy matching",
                "details": str(e)
            }), 500

    # --- 対象スレッドファイルの取得 ---
    file_path = os.path.join(base_dir, f"{invoice}.json")
    if not os.path.exists(file_path):
        return jsonify({"message": f"Thread not found: {invoice}"}), 404

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return jsonify({
            "error": "Failed to read JSON file",
            "details": str(e)
        }), 500

    # --- 正常応答 ---
    return jsonify({
        "invoice": invoice,
        "count": data.get("count", len(data.get("messages", []))),
        "messages": data.get("messages", []),
    })
