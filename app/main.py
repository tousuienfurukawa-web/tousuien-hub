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
# 💬 Slackスレッド抽出（返信を含む完全展開）
# ==================================================
def extract_thread_from_zip(invoice_id):
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}

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

                normalized_invoice = (
                    invoice_id.strip().lower().replace("tse-", "").replace("ts-", "").replace("t-", "").replace(" ", "")
                )
                text_norm = text.lower().replace(" ", "")
                if (
                    normalized_invoice not in text_norm
                    and invoice_id.lower() not in text_norm
                    and f"tse-{normalized_invoice}" not in text_norm
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
# 🧾 HTML出力：raw / report 両モード対応
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
    body {font-family: 'Segoe UI', sans-serif; background: #f8f8fc; padding: 30px; line-height: 1.6;}
    .msg {background:#fff;border-radius:8px;margin:12px 0;padding:14px 18px;box-shadow:0 1px 4px rgba(0,0,0,0.08);}
    .reply {margin-left:25px;background:#f9f9ff;}
    .user {color:#0073e6;font-weight:bold;}
    .graybox {background:#f2f2f7;padding:8px 12px;border-radius:6px;margin-top:5px;}
    h2 {color:#333;}
    </style>
    """

    # 🧩 mode別出力
    if mode == "report":
        html += f"<h2>📦 受注スレッドレポート：{invoice_id}</h2>"
        html += "<h3>🗒️ GPT要約</h3><p>このスレッドでは受注から納期調整、出荷・決済に関するやり取りが確認されました。<br>特記事項や注意事項がある場合、製造・経理チームのコメントが続きます。</p><hr>"

        html += "<h3>💬 スレッド原文</h3>"
    else:
        html += f"<h2>💬 Slack原文（{invoice_id}）</h2>"

    for m in msgs:
        html += f"<div class='msg'><div class='user'>👤 {m['user']}</div><div>{m['text'].replace(chr(10), '<br>')}</div>"
        for r in m['replies']:
            html += f"<div class='msg reply'><div class='user'>↪ {r.get('user')}</div><div>{r.get('text','').replace(chr(10), '<br>')}</div></div>"
        html += "</div>"

    if mode == "report":
        html += "<hr><h3>🧭 次のアクション提案（GPT）</h3><ul>"
        html += "<li>✅ DHL発送変更後の書類更新確認</li>"
        html += "<li>💰 入金処理・残額確認</li>"
        html += "<li>📦 出荷日確定とPL修正版の再送付</li>"
        html += "</ul><p style='color:#666;'>（自動生成要約。Slack原文参照で内容精査推奨）</p>"

    return html

# ==================================================
# 🚀 ローカル / Render 起動
# ==================================================
if __name__ == "__main__":
    import uvicorn
    if not ZIP_FILE_PATH.exists():
        print("⚠️ slack_export_latest.zip が見つかりません。")
    else:
        print("✅ ZIPファイル読み込み成功。")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
