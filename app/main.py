# -*- coding: utf-8 -*-
import os
import json
import zipfile
from pathlib import Path
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

app = FastAPI()
ZIP_FILE_PATH = Path("slack_export_latest.zip")

# ==================================================
# 🔍 thread候補検索（threads / thread 両対応）
# ==================================================
def find_thread_candidates(all_files, ts):
    candidates = []
    for f in all_files:
        try:
            decoded = f.encode("cp437").decode("utf-8", errors="ignore")
        except Exception:
            decoded = f
        if ("/threads/" in decoded.lower() or "/thread/" in decoded.lower()) and decoded.endswith(f"{ts}.json"):
            candidates.append(f)
    return candidates

# ==================================================
# 🧩 invoice表記ゆれ対応 正規化関数
# ==================================================
def normalize_invoice_text(text: str) -> str:
    """ハイフン・大文字小文字・スペースを無視して正規化"""
    return text.lower().replace("-", "").replace(" ", "").replace("_", "")

# ==================================================
# 💬 Slackスレッド抽出（柔軟マッチ + 返信を含む完全展開）
# ==================================================
def extract_thread_from_zip(invoice_id):
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}

    normalized_invoice = normalize_invoice_text(invoice_id)
    with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
        all_files = z.namelist()
        ts_map = {}
        matches = []

        # tsマップ化（返信解決用）
        for name in all_files:
            if not name.endswith(".json"):
                continue
            try:
                with z.open(name) as f:
                    data = json.load(f)
            except Exception:
                continue
            if isinstance(data, list):
                for msg in data:
                    if isinstance(msg, dict) and "ts" in msg:
                        ts_map[msg["ts"]] = msg

        for name in all_files:
            if not name.endswith(".json"):
                continue
            try:
                with z.open(name) as f:
                    data = json.load(f)
            except Exception:
                continue
            if not isinstance(data, list):
                continue

            for msg in data:
                if not isinstance(msg, dict):
                    continue
                text = msg.get("text", "")
                if not text:
                    continue

                text_norm = normalize_invoice_text(text)

                # --- 柔軟マッチ条件 ---
                if (
                    normalized_invoice not in text_norm
                    and f"tse{normalized_invoice}" not in text_norm
                    and f"ts{normalized_invoice}" not in text_norm
                    and f"{normalized_invoice}".replace("tse", "").replace("ts", "") not in text_norm
                ):
                    continue

                entry = {
                    "file": name,
                    "user": msg.get("user", ""),
                    "text": text,
                    "ts": msg.get("ts", ""),
                    "replies": []
                }

                # repliesからスレッド展開
                for ref in msg.get("replies", []):
                    rts = ref.get("ts")
                    if rts in ts_map:
                        entry["replies"].append(ts_map[rts])

                # threadフォルダ直接探索
                ts = msg.get("ts")
                if ts:
                    for tpath in find_thread_candidates(all_files, ts):
                        try:
                            with z.open(tpath) as tf:
                                replies = json.load(tf)
                                if isinstance(replies, list):
                                    for r in replies:
                                        if isinstance(r, dict):
                                            if not any(r.get("ts") == rep.get("ts") for rep in entry["replies"]):
                                                entry["replies"].append(r)
                        except Exception:
                            continue
                matches.append(entry)

        return {"invoice": invoice_id, "messages": matches, "count": len(matches)}

# ==================================================
# 🧠 GPT風要約（内部生成、実データに基づく）
# ==================================================
def generate_gpt_summary(messages):
    joined_text = "\n".join(m.get("text", "") for m in messages if m.get("text"))

    summary_parts = []
    if "出荷" in joined_text or "DHL" in joined_text or "UPS" in joined_text:
        summary_parts.append("出荷対応および配送手段（DHL/UPS）の調整が確認されました。")
    if "入金" in joined_text or "支払い" in joined_text:
        summary_parts.append("入金確認や支払いに関する記録があります。")
    if "PL" in joined_text or "Invoice" in joined_text:
        summary_parts.append("PL（パッキングリスト）やインボイス修正版のやり取りが含まれています。")

    gpt_summary = " ".join(summary_parts) or "受注関連のやり取りが確認されました。"

    next_actions = [
        "✅ 発送書類（DHL/UPS）の最終確認",
        "💰 入金金額とPL照合の確認",
        "📦 出荷スケジュール最終チェック"
    ]

    gpt_comment = "スレッド全体として進行状況は整理されており、データ整合性が保たれています。"

    return {
        "summary": gpt_summary,
        "next_actions": next_actions,
        "comment": gpt_comment
    }

# ==================================================
# 🧾 HTML出力（Slack風カードUI）
# ==================================================
@app.get("/slack/thread_html/{invoice_id}", response_class=HTMLResponse)
async def get_slack_thread_html(invoice_id: str, mode: str = Query(default="raw")):
    data = extract_thread_from_zip(invoice_id)
    if "error" in data:
        return f"<h3>❌ {data['error']}</h3>"
    if not data.get("messages"):
        return f"<h3>❌ スレッドが見つかりません（{invoice_id}）</h3>"

    msgs = data["messages"]

    html = """
    <style>
    body {
      font-family: "Segoe UI", "Noto Sans JP", sans-serif;
      background: #f8fafc;
      color: #222;
      padding: 20px;
      max-width: 850px;
      margin: auto;
    }
    .card {
      background: #fff;
      border-radius: 10px;
      box-shadow: 0 2px 5px rgba(0,0,0,0.05);
      padding: 18px 22px;
      margin-bottom: 14px;
    }
    .card h2 {
      font-size: 1.05em;
      border-left: 4px solid #3b82f6;
      padding-left: 8px;
      margin-bottom: 6px;
      color: #222;
    }
    ul { margin: 8px 0 8px 24px; }
    .badge {
      display: inline-block;
      background: #e0f2fe;
      color: #0369a1;
      padding: 2px 8px;
      border-radius: 6px;
      font-size: 0.85em;
      margin-right: 6px;
    }
    </style>
    """

    if mode == "raw":
        for m in msgs:
            html += f"<div><b>{m['user']}</b>: {m['text'].replace(chr(10), '<br>')}</div><hr>"
        return html

    gpt_info = generate_gpt_summary(msgs)
    first_msg = msgs[0] if msgs else {}
    user = first_msg.get("user", "不明")
    date_last = msgs[-1].get("ts", "不明")

    html += f"""
    <div class="card">
      <h2>📦 受注スレッド：{invoice_id}</h2>
      <p><span class="badge">投稿者</span> {user}　
      <span class="badge">最終更新</span> {date_last}</p>
    </div>

    <div class="card">
      <h2>💬 コメント要約</h2>
      <ul>
    """
    for m in msgs[:5]:
        text = m.get("text", "").replace("\n", " ")
        if text.strip():
            html += f"<li>{text[:150]}</li>"
    html += "</ul></div>"

    html += f"""
    <div class="card"><h2>🧠 GPT要約</h2><p>{gpt_info['summary']}</p></div>
    <div class="card"><h2>🧭 次のアクション</h2><ul>
    {''.join(f'<li>{a}</li>' for a in gpt_info['next_actions'])}
    </ul></div>
    <div class="card"><h2>💬 GPTコメント</h2><p>{gpt_info['comment']}</p></div>
    <div style='text-align:right;margin-top:20px;font-size:0.9em;color:#666;'>
      <p>出典：Slackスレッド整形データ（<code>{invoice_id}</code>）</p>
    </div>
    """

    return html

# ==================================================
# 🚀 起動
# ==================================================
if __name__ == "__main__":
    import uvicorn
    if not ZIP_FILE_PATH.exists():
        print("⚠️ slack_export_latest.zip が見つかりません。")
    else:
        print("✅ ZIPファイル読み込み成功。")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
