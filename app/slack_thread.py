from flask import Blueprint, request
import os, json

bp = Blueprint("slack_thread", __name__)

@bp.route("/slack/thread/<invoice>", methods=["GET"])
def get_slack_thread(invoice):
    """SlackスレッドのJSONデータを返す（旧API互換）"""
    invoice = invoice.upper().strip()

    # --- ラフ入力補完ロジック ---
    if "-" not in invoice:
        files = os.listdir("data/slack_threads")
        candidates = [f.replace(".json", "") for f in files if f.startswith(invoice)]
        if candidates:
            invoice = candidates[0]
        else:
            return {"message": f"No invoice found for {invoice}"}, 404

    # --- 該当スレッド読み込み ---
    path = f"data/slack_threads/{invoice}.json"
    if not os.path.exists(path):
        return {"message": f"Thread not found: {invoice}"}, 404

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {"invoice": invoice, "messages": data}


@bp.route("/slack/thread_html/<invoice>", methods=["GET"])
def get_slack_thread_html(invoice):
    """SlackスレッドのHTMLビュー（report/raw両対応 + 短縮補完対応）"""
    mode = request.args.get("mode", "report").lower().strip()
    invoice = invoice.upper().strip()

    # --- ✅ 短縮入力・部分一致補完ロジック ---
    json_dir = "data/slack_threads"
    json_path = f"{json_dir}/{invoice}.json"

    if not os.path.exists(json_path):
        if os.path.exists(json_dir):
            files = os.listdir(json_dir)
            # 🔍 invoiceを部分一致 or 先頭一致で検索（例：RNI00125 → TSE-RNI-001-25）
            candidates = [
                f.replace(".json", "")
                for f in files
                if invoice in f or f.startswith(invoice)
            ]
            if candidates:
                # 一致候補が複数ある場合はアルファベット順で最初を採用
                invoice = sorted(candidates)[0]
                json_path = f"{json_dir}/{invoice}.json"
            else:
                return f"<p>❌ Thread not found for {invoice}</p>", 404
        else:
            return f"<p>❌ Slack thread data folder not found ({json_dir})</p>", 500

    # --- 該当スレッドを読み込み ---
    with open(json_path, "r", encoding="utf-8") as f:
        messages = json.load(f)

    # --- raw モード（本文表示） ---
    if mode == "raw":
        html_msgs = ""
        for msg in messages:
            user = msg.get("user_name", "不明なユーザー")
            text = msg.get("text", "")
            ts = msg.get("timestamp", "")
            html_msgs += f"""
            <div style='border-bottom:1px solid #e2e8f0;padding:8px 0;'>
                <strong>{user}</strong><br>{text}
                <div style='font-size:12px;color:#94a3b8;'>{ts}</div>
            </div>
            """

        html = f"""
        <html lang="ja"><head><meta charset="UTF-8">
        <style>body{{font-family:'Noto Sans JP',sans-serif;padding:20px;line-height:1.6;}}</style>
        </head><body>
        <h1>📋 {invoice}</h1>
        <h2>💬 Slackスレッド本文</h2>
        {html_msgs}
        <hr><p style='color:#64748b;font-size:12px;'>mode=raw (Tousuien Hub)</p>
        </body></html>
        """
        return html

    # --- report モード（要約ビュー） ---
    summary_html = f"""
    <html lang="ja"><head><meta charset="UTF-8">
    <style>
      body{{font-family:'Noto Sans JP',sans-serif;background:#f8fafc;color:#0f172a;padding:24px;line-height:1.6;}}
      .card{{max-width:760px;margin:0 auto;background:white;border-radius:12px;padding:28px;box-shadow:0 10px 30px rgba(0,0,0,0.05);}}
      h1{{font-size:24px;margin-bottom:8px;}}
      .summary{{background:#eff6ff;border-left:5px solid #3b82f6;padding:16px;border-radius:8px;margin-bottom:24px;}}
      .stat{{background:#f1f5f9;border-radius:8px;padding:12px;margin:8px 0;}}
      .footer{{text-align:right;color:#64748b;font-size:12px;margin-top:24px;}}
    </style></head><body>
      <div class="card">
        <h1>📋 {invoice}</h1>
        <div class="summary">
          <strong>🧠 現状:</strong> ⚠️ 明確な進捗報告がSlack上に見つかりません<br>
          <strong>次のアクション:</strong><ul><li>📋 スレッド内容を確認してください</li></ul>
