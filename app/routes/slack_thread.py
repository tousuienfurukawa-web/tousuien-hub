from flask import Blueprint, request
import os, json, datetime
from openai import OpenAI
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

bp = Blueprint("slack_thread", __name__)

# === APIキーなど環境変数 ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

client = OpenAI(api_key=OPENAI_API_KEY)
slack = WebClient(token=SLACK_BOT_TOKEN)

# === Slackスレッド取得 + GPT要約 ===
@bp.route("/slack/thread_html/<invoice>", methods=["GET"])
def get_slack_thread_html(invoice):
    """Slackスレッド全文＋GPT要約HTMLビュー"""
    mode = request.args.get("mode", "report").lower().strip()
    refresh = request.args.get("refresh", "false").lower() == "true"
    invoice = invoice.upper().strip()

    # --- 1️⃣ ローカルキャッシュ優先 ---
    json_path = f"data/slack_threads/{invoice}.json"
    messages = []
    if os.path.exists(json_path) and not refresh:
        with open(json_path, "r", encoding="utf-8") as f:
            messages = json.load(f)

    # --- 2️⃣ Slackから最新スレッド取得（refresh指定 or ローカルに存在しない場合） ---
    if not messages or refresh:
        try:
            search = slack.search_messages(query=invoice, sort="timestamp", sort_dir="desc", count=1)
            matches = search["messages"]["matches"]
            if not matches:
                return f"<p>❌ Slack上に {invoice} を含むスレッドが見つかりません</p>", 404

            match = matches[0]
            channel = match["channel"]["id"]
            thread_ts = match.get("thread_ts") or match.get("ts")

            replies = slack.conversations_replies(channel=channel, ts=thread_ts, limit=200)
            messages = replies.get("messages", [])

            # キャッシュ保存
            os.makedirs("data/slack_threads", exist_ok=True)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)

        except SlackApiError as e:
            return f"<p>⚠️ Slack APIエラー: {str(e)}</p>", 500

    # --- 3️⃣ HTML整形（全メッセージを時系列で並べる） ---
    messages.sort(key=lambda m: float(m.get("ts", 0)))
    html_msgs = ""
    plain_texts = []

    for msg in messages:
        user = msg.get("user", "不明ユーザー")
        text = msg.get("text", "")
        ts = msg.get("ts", "")
        ts_str = datetime.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
        html_msgs += f"""
        <div style='border-bottom:1px solid #e2e8f0;padding:8px 0;'>
            <strong>{user}</strong><br>{text}
            <div style='font-size:12px;color:#94a3b8;'>{ts_str}</div>
        </div>
        """
        plain_texts.append(f"[{ts_str}] {user}: {text}")

    # --- 4️⃣ GPTによる要約生成 ---
    summary_text = ""
    if mode == "report":
        prompt = f"""
あなたは社内業務スレッドの要約担当です。
以下のSlackスレッド（{invoice}）を要約し、箇条書きで出力してください。
- 顧客名
- 注文内容
- 納期・出荷予定
- 支払い・入金状況
- 注意点（あれば）

=== スレッド本文 ===
{os.linesep.join(plain_texts)}
        """

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",  # もしくは gpt-5
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=600,
            )
            summary_text = response.choices[0].message.content.strip()
        except Exception as e:
            summary_text = f"⚠️ 要約生成に失敗しました: {e}"

    # --- 5️⃣ 出力HTML生成 ---
    html = f"""
    <html lang="ja"><head><meta charset="UTF-8">
    <style>
      body{{font-family:'Noto Sans JP',sans-serif;background:#f8fafc;color:#0f172a;padding:24px;line-height:1.6;}}
      .card{{max-width:760px;margin:0 auto;background:white;border-radius:12px;padding:28px;box-shadow:0 10px 30px rgba(0,0,0,0.05);}}
      h1{{font-size:24px;margin-bottom:8px;}}
      .summary{{background:#eff6ff;border-left:5px solid #3b82f6;padding:16px;border-radius:8px;margin-bottom:24px;white-space:pre-wrap;}}
      .msg{{border-bottom:1px solid #e2e8f0;padding:8px 0;}}
      .footer{{text-align:right;color:#64748b;font-size:12px;margin-top:24px;}}
    </style></head><body>
      <div class="card">
        <h1>📋 {invoice}</h1>
        <h2>💬 Slackスレッド全文</h2>
        {html_msgs}
        <hr>
        <h2>🧠 GPT要約ビュー</h2>
        <div class="summary">{summary_text}</div>
        <div class="footer">Slackスレッド要約ビュー（Tousuien Hub / mode={mode}）</div>
      </div>
    </body></html>
    """
    return html
