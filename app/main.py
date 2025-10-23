# -*- coding: utf-8 -*-
import os
import re
import json
import zipfile
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# ✅ ローカルモジュール
from user_map import resolve_user_name
from gpt5_summary import generate_slack_summary

app = FastAPI()
ZIP_FILE_PATH = Path("slack_export_latest.zip")
CACHE_DIR = Path("cache_slack_threads")
CACHE_DIR.mkdir(exist_ok=True)

# ------------------------------------------------------------
# 🔹 基本ユーティリティ
# ------------------------------------------------------------
def normalize_invoice_text(text: str) -> str:
    return text.lower().replace("-", "").replace(" ", "").replace("_", "")

def format_timestamp(ts):
    try:
        dt = datetime.fromtimestamp(float(ts))
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return ts

def escape_html(text: str) -> str:
    return (text or "").replace("<", "&lt;").replace(">", "&gt;")

# ------------------------------------------------------------
# 🔹 あいまい検索機能
# ------------------------------------------------------------
def find_invoice_candidates(keyword: str):
    normalized_kw = normalize_invoice_text(keyword)
    candidates = []

    if not ZIP_FILE_PATH.exists():
        return candidates

    with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
        for name in z.namelist():
            if not name.endswith(".json"):
                continue
            try:
                with z.open(name) as f:
                    data = json.load(f)
            except Exception as e:
                print(f"[WARN] JSON load error in {name}: {e}")
                continue

            if not isinstance(data, list):
                continue

            for msg in data:
                if isinstance(msg, dict):
                    text = msg.get("text", "")
                elif isinstance(msg, str):
                    text = msg
                else:
                    continue

                if not text:
                    continue

                norm_text = normalize_invoice_text(text)
                if normalized_kw in norm_text:
                    m = re.search(r"TSE-[A-Z0-9]+-\d{3}-\d{2}", text)
                    if m:
                        invoice = m.group(0)
                        if invoice not in candidates:
                            candidates.append(invoice)
                            print(f"[DEBUG] Found invoice candidate: {invoice} in {name}")

    print(f"[INFO] Candidates found for {keyword}: {candidates}")
    return candidates

# ------------------------------------------------------------
# 🔹 ZIPからスレッド抽出
# ------------------------------------------------------------
def extract_thread_from_zip(invoice_id):
    normalized_invoice = normalize_invoice_text(invoice_id)
    cache_path = CACHE_DIR / f"{invoice_id}.json"

    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}

    print(f"[INFO] Extracting from ZIP for: {invoice_id}")
    matches = []
    with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
        for name in z.namelist():
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
                if isinstance(msg, dict):
                    text = msg.get("text", "")
                elif isinstance(msg, str):
                    text = msg
                else:
                    continue

                if not text:
                    continue
                if normalized_invoice not in normalize_invoice_text(text):
                    continue

                ts = msg.get("ts", "")
                thread_ts = msg.get("thread_ts", ts)
                thread_messages = [msg]

                for other_msg in data:
                    if not isinstance(other_msg, dict):
                        continue
                    other_thread_ts = other_msg.get("thread_ts", other_msg.get("ts"))
                    if other_thread_ts == thread_ts and other_msg.get("ts") != ts:
                        thread_messages.append(other_msg)

                thread_messages = [
                    {**m, "user": resolve_user_name(m.get("user"))} for m in thread_messages
                ]

                matches.append({
                    "user": resolve_user_name(msg.get("user")),
                    "text": text,
                    "ts": ts,
                    "thread_ts": thread_ts,
                    "all_messages": thread_messages,
                })

    data = {"invoice": invoice_id, "messages": matches}
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

# ------------------------------------------------------------
# 🔹 HTML生成
# ------------------------------------------------------------
def build_raw_html(invoice_id, msgs):
    html_msgs = ""
    for t in msgs:
        html_msgs += f"<h2>💬 スレッド開始: {escape_html(t['text'])}</h2>"
        for m in t["all_messages"]:
            user = m.get("user")
            ts = format_timestamp(m.get("ts"))
            text = escape_html(m.get("text", ""))
            html_msgs += f"""
            <div class='msg'>
              <div class='bubble'>
                <div class='meta'><strong>{user}</strong> <span>{ts}</span></div>
                <div class='text'>{text}</div>
              </div>
            </div>
            """
    return f"<div><h1>📋 {invoice_id}</h1>{html_msgs}</div>"

def build_report_html(invoice_id, msgs, gpt_info):
    total_threads = len(msgs)
    total_messages = sum(len(m.get("all_messages", [])) for m in msgs)
    participants = sorted({m.get("user") for t in msgs for m in t.get("all_messages", [])})
    latest_ts = max((float(m.get("ts", 0)) for t in msgs for m in t.get("all_messages", []) if m.get("ts")), default=0)
    last_updated = format_timestamp(latest_ts)
    return f"""
      <div class="card">
        <h2>🧠 要約ビュー: {invoice_id}</h2>
        <p style="color:#475569;">最終更新: {last_updated}</p>
        <div class="summary">{escape_html(gpt_info["status"])}</div>
        <div class="stat"><strong>スレッド数:</strong> {total_threads}</div>
        <div class="stat"><strong>総メッセージ数:</strong> {total_messages}</div>
        <div class="stat"><strong>関係者:</strong> {", ".join(participants[:10])}</div>
      </div>
    """

# ------------------------------------------------------------
# 🔹 HTML & GPT出力（曖昧検索対応）
# ------------------------------------------------------------
@app.get("/slack/thread_html/{keyword}", response_class=HTMLResponse)
async def get_slack_thread_html(keyword: str):
    candidates = find_invoice_candidates(keyword)

    if len(candidates) == 1:
        invoice_id = candidates[0]
        data = extract_thread_from_zip(invoice_id)
        if "error" in data:
            return f"<h3>❌ {data['error']}</h3>"
        if not data.get("messages"):
            return f"<h3>❌ スレッドが見つかりません（{invoice_id}）</h3>"

        msgs = data["messages"]
        raw_html_section = build_raw_html(invoice_id, msgs)
        all_thread_messages = [m for t in msgs for m in t.get("all_messages", [])]
        gpt_result = generate_slack_summary(invoice_id, all_thread_messages)
        gpt_info = {"status": gpt_result.get("summary", "⚠️ 要約生成中にエラーが発生しました")}
        summary_html_section = build_report_html(invoice_id, msgs, gpt_info)

        return HTMLResponse(f"""
        <html><head><meta charset='utf-8'><title>{invoice_id}</title></head>
        <body><div class='container'>
        <h2>💬 全文表示（Raw）</h2>{raw_html_section}
        <h2>🧠 GPT-5要約</h2>{summary_html_section}
        </div></body></html>
        """)

    elif len(candidates) > 1:
        all_texts = []
        for inv in candidates:
            data = extract_thread_from_zip(inv)
            for t in data.get("messages", []):
                for m in t.get("all_messages", []):
                    txt = f"{inv}: {m.get('user')} - {m.get('text', '')}"
                    all_texts.append(txt)
        joined_text = "\n".join(all_texts)

        gpt_result = generate_slack_summary(f"{keyword.upper()}_SUMMARY", [{"text": joined_text}])
        summary_text = gpt_result.get("summary", "⚠️ 要約生成に失敗しました。")

        html_list = "<ul>" + "".join(
            f"<li><a href='/slack/thread_html/{inv}'>{inv}</a></li>" for inv in candidates
        ) + "</ul>"

        return HTMLResponse(f"""
        <html><head><meta charset='utf-8'><title>{keyword.upper()} 概要</title></head>
        <body>
        <h1>🏢 {keyword.upper()} 関連スレッド一覧</h1>
        {html_list}
        <h2>🧠 企業概要・近況要約</h2>
        <div style='background:#eff6ff;padding:16px;border-left:5px solid #3b82f6;white-space:pre-wrap;'>{escape_html(summary_text)}</div>
        </body></html>
        """)

    return HTMLResponse(f"<h3>❌ 該当するスレッドが見つかりません（{keyword}）</h3>")

# ------------------------------------------------------------
# 🔹 JSON API & ZIPアップロード
# ------------------------------------------------------------
@app.get("/api/slack_threads/{invoice_id}.json", response_class=JSONResponse)
async def get_slack_thread_json(invoice_id: str):
    data = extract_thread_from_zip(invoice_id)
    return data

@app.post("/api/upload_zip")
async def upload_zip(file: UploadFile = File(...)):
    content = await file.read()
    with open(ZIP_FILE_PATH, "wb") as f:
        f.write(content)
    for p in CACHE_DIR.glob("*.json"):
        p.unlink()
    return {"status": "✅ ZIP uploaded successfully. Cache cleared."}

# ------------------------------------------------------------
# ✅ Render向けヘルスチェック & JITプラグインAPI
# ------------------------------------------------------------
@app.get("/")
def healthcheck():
    return {"status": "ok", "message": "Tousuien Hub is live 🚀"}

class SlackRequest(BaseModel):
    invoice: str
    mode: str | None = "raw"

@app.post("/jit_plugin/get_slack_thread_html")
def get_slack_thread_html_jit(req: SlackRequest):
    try:
        data = extract_thread_from_zip(req.invoice)
        if "error" in data:
            raise HTTPException(status_code=404, detail=data["error"])
        return {
            "invoice": req.invoice,
            "mode": req.mode,
            "messages": data.get("messages", []),
            "summary": f"{req.invoice} のスレッドデータを取得しました。",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------------------------------------------------
# 🔹 アプリ起動
# ------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
