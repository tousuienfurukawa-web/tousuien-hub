from flask import Blueprint, request
import os, json, datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

bp = Blueprint("slack_thread", __name__)

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
slack = WebClient(token=SLACK_BOT_TOKEN)

# 🔹 Slackユーザーキャッシュ
USER_CACHE = {}

def get_user_name(user_id: str) -> str:
    """SlackのユーザーIDから表示名を取得（キャッシュ付き）"""
    if not user_id:
        return "不明ユーザー"
    if user_id in USER_CACHE:
        return USER_CACHE[user_id]
    try:
        info = slack.users_info(user=user_id)
        if info.get("ok"):
            profile = info["user"]["profile"]
            name = profile.get("display_name") or profile.get("real_name") or user_id
            USER_CACHE[user_id] = name
            return name
    except SlackApiError:
        pass
    return user_id

@bp.route("/slack/thread_html/<invoice>", methods=["GET"])
def get_slack_thread_html(invoice):
    """SlackスレッドのHTMLビュー（ユーザー名マッピング対応）"""
    mode = request.args.get("mode", "report").lower().strip()
    invoice = invoice.upper().strip()

    # --- 短縮入力・補完 ---
    json_dir = "data/slack_threads"
    json_path = f"{json_dir}/{invoice}.json"
    if not os.path.exists(json_path):
        if os.path.exists(json_dir):
            files = os.listdir(json_dir)
            candidates = [f.replace(".json", "") for f in files if invoice in f or f.startswith(invoice)]
            if candidates:
                invoice = sorted(candidates)[0]
                json_path = f"{json_dir}/{invoice}.json"
            else:
                return f"<p>❌ Thread not found for {invoice}</p>", 404
        else:
            return f"<p>❌ Slack thread data folder not found ({json_dir})</p>", 500

    with open(json_path, "r", encoding="utf-8") as f:
        messages = json.load(f)

    # --- HTML化（ユーザー名変換付き） ---
    html_msgs = ""
    for msg in messages:
        user_id = msg.get("user") or msg.get("user_id") or ""
        user_name = msg.get("user_name") or get_user_name(user_id)
        text = msg.get("text", "")
        ts = msg.get("ts") or msg.get("timestamp", "")
        try:
            ts_str = datetime.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
        except:
            ts_str = ts
        html_msgs += f"""
        <div style='border-bottom:1px solid #e2e8f0;padding:8px 0;'>
            <strong>{user_name}</strong><br>{text}
            <div style='font-size:12px;color:#94a3b8;'>{ts_str}</div>
        </div>
        """

    html = f"""
    <html lang="ja"><head><meta charset="UTF-8">
    <style>
      body{{font-family:'Noto Sans JP',sans-serif;background:#f8fafc;color:#0f172a;padding:24px;line-height:1.6;}}
      .card{{max-width:760px;margin:0 auto;background:white;border-radius:12px;padding:28px;box-shadow:0 10px 30px rgba(0,0,0,0.05);}}
      h1{{font-size:24px;margin-bottom:8px;}}
      .footer{{text-align:right;color:#64748b;font-size:12px;margin-top:24px;}}
    </style></head><body>
      <div class="card">
        <h1>📋 {invoice}</h1>
        <h2>💬 Slackスレッド本文（ユーザー名補完済）</h2>
        {html_msgs}
        <div class="footer">Slackスレッドビュー（Tousuien Hub）</div>
      </div>
    </body></html>
    """
    return html
