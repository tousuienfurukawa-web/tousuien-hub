# ============================================================
#  Tousuien Hub - Slack Thread Viewer (GPT要約対応版)
# ============================================================

import os
import json
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from openai import OpenAI

app = FastAPI()

# ------------------------------------------------------------
# 🔹 GPT要約生成関数（新SDK対応）
# ------------------------------------------------------------
def generate_slack_summary(invoice_id: str, messages: list) -> dict:
    """
    Slackスレッドのメッセージ配列からGPT-5で要約を生成する
    """
    try:
        # OpenAIクライアント初期化
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # メッセージ本文をテキスト化
        all_text = "\n".join(
            [f"- {m.get('user', '')}: {m.get('text', '')}" for m in messages]
        )

        # GPTに送るプロンプト
        prompt = f"""
あなたはSlackスレッドの内容を要約するAIです。
以下は注文・出荷・支払いに関するやり取りの全文です。
読みやすく、3〜5行程度で要約してください。

--- スレッド全文 ---
{all_text}
        """

        # 🔥 GPT-5 / GPT-4o-mini で要約生成
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "あなたは有能な業務アシスタントです。"},
                {"role": "user", "content": prompt}
            ],
        )

        summary = completion.choices[0].message.content.strip()
        return {"summary": summary}

    except Exception as e:
        # 失敗時にはログ出力して簡易メッセージを返す
        print(f"[ERROR] GPT summary generation failed: {e}")
        return {"summary": f"⚠️ GPT要約生成に失敗しました: {e}"}


# ------------------------------------------------------------
# 🔹 ZIP / JSON抽出（フォールバック用）
# ------------------------------------------------------------
def extract_thread_from_zip(invoice_id: str) -> dict:
    """
    Slackスレッドデータ（JSON）を data/slack_threads フォルダから読み取る
    """
    base_path = f"data/slack_threads/{invoice_id}.json"
    if not os.path.exists(base_path):
        return {"error": "Not Found"}

    with open(base_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


# ------------------------------------------------------------
# 🔹 全文表示HTML
# ------------------------------------------------------------
def build_raw_html(invoice_id: str, messages: list) -> str:
    html = f"<h2>Slack Thread: {invoice_id}</h2><pre>"
    for m in messages:
        user = m.get("user", "unknown")
        text = m.get("text", "")
        html += f"{user}: {text}\n"
    html += "</pre>"
    return html


# ------------------------------------------------------------
# 🔹 エンドポイント（GPT-5要約対応版）
# ------------------------------------------------------------
@app.get("/slack/thread_html/{invoice_id}", response_class=HTMLResponse)
async def get_slack_thread_html(invoice_id: str, mode: str = Query(default="report")):
    data = extract_thread_from_zip(invoice_id)
    if "error" in data:
        return f"<h3>❌ {data['error']}</h3>"
    if not data.get("messages"):
        return f"<h3>❌ スレッドが見つかりません（{invoice_id}）</h3>"

    msgs = data["messages"]

    # ✅ mode=raw の場合は要約生成をスキップして全文表示
    if mode == "raw":
        return build_raw_html(invoice_id, msgs)

    # ✅ mode=report の場合のみ GPTで要約生成
    gpt_result = generate_slack_summary(invoice_id, msgs)

    # ✅ HTML出力
    html = f"""
    <html lang="ja">
    <head>
      <meta charset="UTF-8">
      <style>
        body {{ font-family: "Noto Sans JP", sans-serif; background:#f8fafc; color:#0f172a; padding:24px; }}
        .card {{ max-width:760px; margin:0 auto; background:white; border-radius:12px; padding:28px;
                 box-shadow:0 10px 30px rgba(0,0,0,0.05); }}
        .summary {{ background:#eff6ff; border-left:5px solid #3b82f6; padding:16px; border-radius:8px; margin-bottom:24px; white-space:pre-wrap; }}
      </style>
    </head>
    <body>
      <div class="card">
        <h1>📋 {invoice_id}</h1>
        <div class="summary">
          <strong>🧠 GPT要約:</strong><br>
          {gpt_result["summary"]}
        </div>
        <p><a href="?mode=raw">📄 全文を表示</a></p>
      </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
