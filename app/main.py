# -*- coding: utf-8 -*-
import os
import re
import json
import zipfile
import logging
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# basic logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# ------------------------------
# ✅ FastAPI app
# ------------------------------
app = FastAPI()

# ------------------------------
# ✅ Files / Cache setup with fallback for read-only FS
# ------------------------------
ZIP_FILE_PATH = Path("slack_export_latest.zip")

# cache dir with safe fallback to /tmp when deployed on read-only FS (e.g. Vercel)
CACHE_DIR = Path("cache_slack_threads")
try:
    CACHE_DIR.mkdir(exist_ok=True)
except Exception:
    fallback = Path(os.getenv("TMPDIR", "/tmp")) / "cache_slack_threads"
    logging.warning("Filesystem read-only or no permission. Using fallback: %s", fallback)
    fallback.mkdir(parents=True, exist_ok=True)
    CACHE_DIR = fallback

# ------------------------------
# 🔹 Safe import: gpt5_summary (may be missing in some environments)
# ------------------------------
generate_slack_summary = None
try:
    # preferred relative import
    from .gpt5_summary import generate_slack_summary  # type: ignore
    logging.info("Imported gpt5_summary via relative import")
except Exception:
    try:
        from gpt5_summary import generate_slack_summary  # type: ignore
        logging.info("Imported gpt5_summary via absolute import")
    except Exception:
        logging.exception("gpt5_summary could not be imported; functionality will be disabled.")
        generate_slack_summary = None

# Provide a safe fallback implementation if import failed
if generate_slack_summary is None:
    def generate_slack_summary(invoice_id: str, messages: list) -> dict:
        """Fallback: return a simple summary when gpt5_summary is unavailable."""
        try:
            sample_texts = []
            if isinstance(messages, list):
                for m in messages[:5]:
                    if isinstance(m, dict):
                        sample_texts.append(m.get("text", "")[:400])
                    else:
                        sample_texts.append(str(m)[:400])
            joined = "\n\n".join(sample_texts) or "（メッセージがありません）"
            return {
                "summary": f"⚠️ GPT要約機能は無効です（gpt5_summaryがロードされていません）。代替表示:\n\n{joined}"
            }
        except Exception as e:
            logging.exception("Fallback generate_slack_summary failed")
            return {"summary": "⚠️ 要約を生成できませんでした（内部エラー）。"}
    logging.info("Using fallback generate_slack_summary")

# ------------------------------
# 🔹 ユーティリティ関数
# ------------------------------
def normalize_invoice_text(text: str) -> str:
    return (text or "").lower().replace("-", "").replace(" ", "").replace("_", "")

def format_timestamp(ts):
    try:
        dt = datetime.fromtimestamp(float(ts))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)

def escape_html(text: str) -> str:
    return (text or "").replace("<", "&lt;").replace(">", "&gt;")

def resolve_user_name(user_id: str):
    # lightweight fallback — the original project likely replaced user ids with readable names earlier.
    if not user_id:
        return "unknown"
    return str(user_id)

# ------------------------------
# 🔹 あいまい検索（ZIPからinvoice候補抽出）
# ------------------------------
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
                logging.warning("JSON load error in %s: %s", name, e)
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

                if normalized_kw in normalize_invoice_text(text):
                    m = re.search(r"(TSE-[A-Z0-9]+-\d{3}-\d{2})", text)
                    if m:
                        invoice = m.group(1)
                        if invoice not in candidates:
                            candidates.append(invoice)
                            logging.debug("Found invoice candidate: %s in %s", invoice, name)

    logging.info("Candidates found for %s: %s", keyword, candidates)
    return candidates

# ------------------------------
# 🔹 ZIPからスレッド抽出（キャッシュ利用）
# ------------------------------
def extract_thread_from_zip(invoice_id):
    normalized_invoice = normalize_invoice_text(invoice_id)
    cache_path = CACHE_DIR / f"{invoice_id}.json"

    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logging.exception("Failed to read cache %s, will re-extract.", cache_path)

    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}

    logging.info("Extracting from ZIP for: %s", invoice_id)
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
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        logging.exception("Failed to write cache %s", cache_path)
    return data

# ------------------------------
# 🔹 HTMLビルダー
# ------------------------------
def build_raw_html(invoice_id, msgs):
    html_msgs = ""
    for t in msgs:
        html_msgs += f"<h2>💬 スレッド開始: {escape_html(t.get('text',''))}</h2>"
        for m in t.get("all_messages", []):
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
    participants = sorted({m.get("user") for t in msgs for m in t.get("all_messages", []) if m.get("user")})
    latest_ts = max((float(m.get("ts", 0)) for t in msgs for m in t.get("all_messages", []) if m.get("ts")), default=0)
    last_updated = format_timestamp(latest_ts)
    return f"""
      <div class="card">
        <h2>🧠 要約ビュー: {invoice_id}</h2>
        <p style="color:#475569;">最終更新: {last_updated}</p>
        <div class="summary">{escape_html(gpt_info.get("status") or gpt_info.get("summary",""))}</div>
        <div class="stat"><strong>スレッド数:</strong> {total_threads}</div>
        <div class="stat"><strong>総メッセージ数:</strong> {total_messages}</div>
        <div class="stat"><strong>関係者:</strong> {", ".join(participants[:10])}</div>
      </div>
    """

# ------------------------------
# 🔹 Slack スレッド関連 API
# ------------------------------
@app.get("/slack/thread_html/{keyword}", response_class=HTMLResponse)
async def get_slack_thread_html(keyword: str):
    candidates = find_invoice_candidates(keyword)

    if len(candidates) == 1:
        invoice_id = candidates[0]
        data = extract_thread_from_zip(invoice_id)
        if "error" in data:
            return HTMLResponse(f"<h3>❌ {data['error']}</h3>", status_code=500)
        if not data.get("messages"):
            return HTMLResponse(f"<h3>❌ スレッドが見つかりません（{invoice_id}）</h3>", status_code=404)

        msgs = data["messages"]
        raw_html_section = build_raw_html(invoice_id, msgs)
        all_thread_messages = [m for t in msgs for m in t.get("all_messages", [])]
        try:
            gpt_result = generate_slack_summary(invoice_id, all_thread_messages) or {}
        except Exception:
            logging.exception("generate_slack_summary failed")
            gpt_result = {"summary": "⚠️ 要約生成中にエラーが発生しました。"}
        gpt_info = {"status": gpt_result.get("summary", "⚠️ 要約生成中にエラーが発生しました")}
        summary_html_section = build_report_html(invoice_id, msgs, gpt_info)

        return HTMLResponse(f"""
        <html><head><meta charset='utf-8'><title>{invoice_id}</title></head>
        <body><div class='container' style='font-family: Arial, Helvetica, sans-serif;'>
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

        try:
            gpt_result = generate_slack_summary(f"{keyword.upper()}_SUMMARY", [{"text": joined_text}]) or {}
            summary_text = gpt_result.get("summary", "⚠️ 要約生成に失敗しました。")
        except Exception:
            logging.exception("generate_slack_summary failed for multi candidates")
            summary_text = "⚠️ 要約生成に失敗しました。"

        html_list = "<ul>" + "".join(
            f"<li><a href='/slack/thread_html/{inv}'>{inv}</a></li>" for inv in candidates
        ) + "</ul>"

        return HTMLResponse(f"""
        <html><head><meta charset='utf-8'><title>{keyword.upper()} 概要</title></head>
        <body style='font-family: Arial, Helvetica, sans-serif;'>
        <h1>🏢 {keyword.upper()} 関連スレッド一覧</h1>
        {html_list}
        <h2>🧠 企業概要・近況要約</h2>
        <div style='background:#eff6ff;padding:16px;border-left:5px solid #3b82f6;white-space:pre-wrap;'>{escape_html(summary_text)}</div>
        </body></html>
        """)

    return HTMLResponse(f"<h3>❌ 該当するスレッドが見つかりません（{keyword}）</h3>", status_code=404)

@app.get("/api/slack_threads/{invoice_id}.json", response_class=JSONResponse)
async def get_slack_thread_json(invoice_id: str):
    data = extract_thread_from_zip(invoice_id)
    if "error" in data:
        return JSONResponse(status_code=404, content=data)
    return JSONResponse(content=data)

@app.post("/api/upload_zip")
async def upload_zip(file: UploadFile = File(...)):
    content = await file.read()
    try:
        with open(ZIP_FILE_PATH, "wb") as f:
            f.write(content)
    except Exception:
        logging.exception("Failed to save uploaded ZIP")
        raise HTTPException(status_code=500, detail="Failed to save ZIP")
    # clear cache
    for p in CACHE_DIR.glob("*.json"):
        try:
            p.unlink()
        except Exception:
            logging.exception("Failed to delete cache file %s", p)
    return {"status": "✅ ZIP uploaded successfully. Cache cleared."}

# ------------------------------
# ✅ Render / Basic health
# ------------------------------
@app.get("/")
def healthcheck():
    return {"status": "ok", "message": "Tousuien Hub is live 🚀"}

# ------------------------------
# 🔹 GPTs向け簡易クエリAPI
# ------------------------------
@app.get("/query")
def query_tousuien_hub(text: str):
    """GPTsから呼び出される顧客検索API（ダミー応答）"""
    try:
        result = {
            "success": True,
            "query": text,
            "response": {
                "company_code": "BKB",
                "year": 2025,
                "total_records": 2,
                "records": [
                    {
                        "invoice": "TSE-BKB-001-25",
                        "注文日": "2025-05-02",
                        "通貨": "USD",
                        "商品代＋送料": 4016.92,
                        "ステータス": "FIRST ORDER",
                        "宛名": "Reda Vranken",
                        "担当者名": "Reda Vranken",
                    },
                    {
                        "invoice": "TSE-BKB-SPL-001-25",
                        "注文日": "2025-07-12",
                        "通貨": "USD",
                        "商品代＋送料": 0.0,
                        "ステータス": "SAMPLE",
                        "宛名": "Reda Vranken",
                        "担当者名": "Reda Vranken",
                    },
                ],
            },
        }
        return JSONResponse(content=result)
    except Exception as e:
        logging.exception("query_tousuien_hub error")
        return JSONResponse(status_code=500, content={"error": str(e)})

# ------------------------------
# 🔹 Redis / Upstash ヘルスチェック
# ------------------------------
@app.get("/api/redis_health")
def redis_health():
    """
    Try multiple ways to ping Redis:
     - If REDIS_URL contains a redis/rediss URL, try redis-py ping.
     - Otherwise (or if redis-py fails), try Upstash REST via UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN.
    Make sure REDIS_URL is a raw URL like:
      rediss://default:<TOKEN>@xxxxx.upstash.io:6379
    and not the full 'redis-cli --tls -u ...' command.
    """
    try:
        # 1) Try to parse REDIS_URL for a rediss?/redis URL
        raw_env = os.getenv("REDIS_URL", "") or ""
        m = re.search(r"(rediss?://[^\s'\"]+)", raw_env)
        redis_conn_str = m.group(1) if m else (raw_env.strip() if raw_env.startswith("redis") or raw_env.startswith("rediss") else None)

        if redis_conn_str:
            try:
                import redis as _redis  # type: ignore
                client = _redis.Redis.from_url(redis_conn_str, socket_timeout=5)
                pong = client.ping()
                return {"ok": True, "method": "redis-py", "ping": bool(pong)}
            except Exception:
                logging.exception("redis-py ping failed for %s", redis_conn_str)

        # 2) Try Upstash REST API
        rest_url = os.getenv("UPSTASH_REDIS_REST_URL") or None
        rest_token = os.getenv("UPSTASH_REDIS_REST_TOKEN") or None

        # if user accidentally put rest URL into REDIS_URL (some UIs), accept that
        if not rest_url and raw_env.startswith("https://"):
            rest_url = raw_env

        if rest_url:
            try:
                import requests  # type: ignore
                headers = {}
                if rest_token:
                    headers["Authorization"] = f"Bearer {rest_token}"
                headers["Content-Type"] = "application/json"
                # Upstash REST: POST with {"command":["PING"]} to base URL
                url = rest_url.rstrip("/") + "/"
                r = requests.post(url, headers=headers, json={"command": ["PING"]}, timeout=6)
                # On success Upstash typically returns JSON with "result": "PONG"
                if r.status_code in (200, 201):
                    try:
                        j = r.json()
                        return {"ok": True, "method": "upstash-rest", "result": j}
                    except Exception:
                        return {"ok": True, "method": "upstash-rest", "status_code": r.status_code, "text": r.text}
                else:
                    logging.warning("Upstash REST returned %s: %s", r.status_code, r.text)
                    return JSONResponse(status_code=500, content={"ok": False, "error": "Upstash REST returned non-200", "status_code": r.status_code, "text": r.text})
            except Exception:
                logging.exception("Upstash REST ping failed")

        return JSONResponse(status_code=500, content={"ok": False, "error": "No usable Redis endpoint found. Check REDIS_URL or UPSTASH_REDIS_REST_URL/UPSTASH_REDIS_REST_TOKEN."})
    except Exception as e:
        logging.exception("redis_health error")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

# ------------------------------
# 🔹 アプリ起動（ローカル検証用）
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
