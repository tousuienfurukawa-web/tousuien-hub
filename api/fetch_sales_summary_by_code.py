# /api/fetch_sales_summary_by_code.py
# -------------------------------------------------------
# 顧客データ分割取得API（Flask対応版）
# -------------------------------------------------------

from flask import Flask, request, jsonify
from db import get_sales_summary_by_code  # あなたのDBアクセス関数

app = Flask(__name__)

@app.route("/api/fetch_sales_summary_by_code", methods=["GET"])
def fetch_sales_summary():
    try:
        # --- パラメータ取得 ---
        code = request.args.get("code")
        section = request.args.get("section")  # "company" | "orders" | "products"
        invoice = request.args.get("invoice")  # optional
        limit = int(request.args.get("limit", 100))  # default 100件

        if not code:
            return jsonify({"error": "Missing 'code' parameter"}), 400

        # --- 顧客データ取得 ---
        full_data = get_sales_summary_by_code(code)
        if not full_data:
            return jsonify({"error": f"No data found for code '{code}'"}), 404

        # --- セクション別分岐 ---
        if section == "company":
            return jsonify({
                "code": code,
                "company": full_data.get("company", {})
            })

        elif section == "orders":
            orders = full_data.get("orders", [])

            # invoice指定がある場合は絞り込み
            if invoice:
                orders = [o for o in orders if o.get("invoice") == invoice]

            # 件数制限
            orders = orders[:limit]

            return jsonify({
                "code": code,
                "orders": orders,
                "count": len(orders)
            })

        elif section == "products":
            return jsonify({
                "code": code,
                "products": full_data.get("products", [])
            })

        # --- デフォルト：全体返却（非推奨・大容量注意） ---
        return jsonify(full_data)

    except Exception as e:
        # --- エラーハンドリング ---
        return jsonify({
            "error": str(e),
            "hint": "Check section/invoice/limit parameters to reduce data size."
        }), 500


# ローカル実行用
if __name__ == "__main__":
    app.run(debug=True)
