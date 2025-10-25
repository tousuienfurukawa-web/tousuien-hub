# app/main.py
# -*- coding: utf-8 -*-
import os
import re
import json
import zipfile
import logging
import errno
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

# ------------------------------------------------------------
# ✅ ログ設定
# ------------------------------------------------------------
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

# ------------------------------------------------------------
# ✅ サーバレス環境向け：ディレクトリ作成の安全化ユーティリティ
# ------------------------------------------------------------
def make_dir_with_fallback(path_str: str, fallback_name: str) -> Path:
    """
    Try to create path_str. If filesystem is read-only or permission denied,
    fallback to /tmp/<fallback_name>. Returns Path actually used.
    """
    p = Path(path_str)
    try:
        p.mkdir(parents=True, exist_ok=True)
        return p
    except OSError as e:
        if getattr(e, "errno", None) in (errno.EROFS, errno.EACCES, errno.EPERM):
            tmp = Path("/tmp") / fallback_name
            try:
                tmp.mkdir(parents=True, exist_ok=True)
                logging.warning("Filesystem read-only or no permission. Using fallback: %s", tmp)
                return tmp
            except Exception:
                logging.exception("Failed to create fallback dir %s", tmp)
                return tmp
        else:
            logging.exception("Failed to create dir %s", p)
            raise

# Base dir of this file (read-only on serverless), prefer env vars to override
BASE_DIR = Path(os.environ.get("BASE_DIR", Path(__file__).resolve().parent))
# ZIP_DIR: prefer user specified or BASE_DIR, but fallback to /tmp as needed
ZIP_DIR = make_dir_with_fallback(os.environ.get("ZIP_DIR", str(BASE_DIR)), "slack_zip")
ZIP_FILE_PATH = ZIP_DIR / os.environ.get("ZIP_FILENAME", "slack_export_latest.zip")

# CACHE_DIR: prefer env or repo dir, but fallback to /tmp when necessary
CACHE_DIR = make_dir_with_fallback(os.environ.get("CACHE_DIR", str(BASE_DIR / "cache_slack_threads")), "cache_slack_threads")

# ------------------------------------------------------------
# ✅ ローカルモジュール（安全インポート）
# ------------------------------------------------------------
generate_slack_summary = None
try:
    # try relative import (preferred when app is a package)
    from .gpt5_summary import generate_slack_summary  # type: ignore
    logging.info("Imported gpt5_summary via relative import")
except Exception:
    try:
        # fallback: absolute import (in case package layout differs)
        from gpt5_summary import generate_slack_summary  # type: ignore
        logging.info("Imported gpt5_summary via absolute import")
    except Exception:
        # final fallback: leave generate_slack_summary as None and log exception
        logging.exception("gpt5_summary could not be imported; functionality will be disabled.")
        generate_slack_summary = None

# ------------------------------------------------------------
# ✅ App 初期化
# ------------------------------------------------------------
app = FastAPI()

# Ensure Vercel/Serverless sees an object named `handler` or `app`
# Vercel uses `app` or `handler`, but we set `handler = app` at the bottom.


# ------------------------------------------------------------
# 🔹 基本ユーティリティ
# ------------------------------------------------------------
def normalize_invoice_text(text: str) -> str:
    return (text or "").lower().replace("-", "").replace(" ", "").replace("_", "")

def format_timestamp(ts):
    try:
        dt = datetime.fromtimestamp(float(ts))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts

def escape_html(text: str) -> str:
    return (text or "").replace("<", "&lt;").replace(">", "&gt;")

# Simple fallback for resolve_user_name (if real impl is elsewhere, it will override)
def resolve_user_name(user) -> str:
    """
    Fallback resolver for user names. If a mapping exists elsewhere, it can be used instead.
    """
    if not user:
        return ""
    return str(user)

# ------------------------------------------------------------
# 🔹 キャッシュ / ファイルユーティリティ（読み書きで落ちないように）
# ------------------------------------------------------------
def get_cache_path(invoice_id: str) -> Path:
    fname = f"{invoice_id}.json"
    return CACHE_DIR / fname

def safe_write_json(path: Path, obj: Any):
    """
    Try to write JSON to path. If fails due to write error, fallback to /tmp.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return path
    except OSError as e:
        logging.warning("Failed to write to %s (%s). Falling back to /tmp", path, e)
        tmp = Path("/tmp") / path.name
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
            return tmp
        except Exception:
            logging.exception("Failed to write fallback cache %s", tmp)
            return None

def safe_read_json(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.debug("safe_read_json failed for %s: %s", path, e)
        # try /tmp fallback
        tmp = Path("/tmp") / path.name
        try:
            with open(tmp, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

# ------------------------------------------------------------
# 🔹 あいまい検索機能
# ------------------------------------------------------------
def find_invoice_candidates(keyword: str):
    normalized_kw = normalize_invoice_text(keyword)
    candidates = []

    if not ZIP_FILE_PATH.exists():
        logging.info("ZIP not found at %s", ZIP_FILE_PATH)
        return candidates

    try:
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

                    norm_text = normalize_invoice_text(text)
                    if normalized_kw in norm_text:
                        m = re.search(r"TSE-[A-Z0-9]+-\d{3}-\d{2}", text)
                        if m:
                            invoice = m.group(0)
                            if invoice not in candidates:
                                candidates.append(invoice)
                                logging.debug("Found invoice candidate: %s in %s", invoice, name)

    except zipfile.BadZipFile:
        logging.exception("Bad ZIP file: %s", ZIP_FILE_PATH)
    except Exception:
        logging.exception("Error while scanning ZIP %s", ZIP_FILE_PATH)

    logging.info("Candidates found for %s: %s", keyword, candidates)
    return candidates

# ------------------------------------------------------------
# 🔹 ZIPからスレッド抽出
# ------------------------------------------------------------
def extract_thread_from_zip(invoice_id: str) -> Dict[str, Any]:
    normalized_invoice = normalize_invoice_text(invoice_id)
    cache_path = get_cache_path(invoice_id)

    # Try cached first
    cached = safe_read_json(cache_path)
    if cached:
        return cached

    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}

    logging.info("Extracting from ZIP for: %s", invoice_id)
    matches = []
    try:
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

                    # Collect other messages in same thread
                    for other_msg in data:
                        if not isinstance(other_msg, dict):
                            continue
                        other_thread_ts = other_msg.get("thread_ts", other_msg.get("ts"))
                        if other_thread_ts == thread_ts and other_msg.get("ts") != ts:
                            thread_messages.append(other_msg)

                    # resolve_user_name for each message in thread
                    safe_msgs = []
                    for m in thread_messages:
                        try:
                            user_name = resolve_user_name(m.get("user"))
                        except Exception:
                            user_name = m.get("user") or ""
                        mm = dict(m)
                        mm["user"] = user_name
                        safe_msgs.append(mm)

                    matches.append({
                        "user": resolve_user_name(msg.get("user")),
                        "text": text,
                        "ts": ts,
                        "thread_ts": thread_ts,
                        "all_messages": safe_msgs,
                    })
    except Exception:
        logging.exception("Failed extracting threads from ZIP")

    data = {"invoice": invoice_id, "messages": matches}
    try:
        safe_write_json(cache_path, data)
    except Exception:
        logging.exception("Failed to cache result for %s", invoice_id)
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
        <div class="summary">{escape_html(gpt_info.get("status",""))}</div>
        <div class="stat"><strong>スレッド数:</strong> {total_threads}</div>
        <div class="stat"><strong>総メッセージ数:</strong> {total_messages}</div>
        <div class="stat"><strong>関係者:</strong> {", ".join(list(participants)[:10])}</div>
      </div>
    """

# ------------------------------------------------------------
# 🔹 Slackスレッド関連API
# ------------------------------------------------------------
@app.get("/slack/thread_html/{keyword}", response_class=HTMLResponse)
async def get_slack_thread_html(keyword: str):
    candidates = find_invoice_candidates(keyword)

    if len(candidates) == 1:
        invoice_id = candidates[0]
        data = extract_thread_from_zip(invoice_id)
        if "error" in data:
            return HTMLResponse(f"<h3>❌ {data['error']}</h3>")
        if not data.get("messages"):
            return HTMLResponse(f"<h3>❌ スレッドが見つかりません（{invoice_id}）</h3>")

        msgs = data["messages"]
        raw_html_section = build_raw_html(invoice_id, msgs)
        all_thread_messages = [m for t in msgs for m in t.get("all_messages", [])]

        # Guarded GPT summary call
        if generate_slack_summary is not None:
            try:
                gpt_result = generate_slack_summary(invoice_id, all_thread_messages)
                status_text = gpt_result.get("summary", "⚠️ 要約生成中にエラーが発生しました")
            except Exception:
                logging.exception("generate_slack_summary failed")
                status_text = "⚠️ 要約生成に失敗しました"
        else:
            status_text = "gpt5_summary not available"

        gpt_info = {"status": status_text}
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

        # Guarded GPT call
        if generate_slack_summary is not None:
            try:
                gpt_result = generate_slack_summary(f"{keyword.upper()}_SUMMARY", [{"text": joined_text}])
                summary_text = gpt_result.get("summary", "⚠️ 要約生成に失敗しました。")
            except Exception:
                logging.exception("generate_slack_summary failed")
                summary_text = "⚠️ 要約生成に失敗しました。"
        else:
            summary_text = "gpt5_summary not available"

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

@app.get("/api/slack_threads/{invoice_id}.json", response_class=JSONResponse)
async def get_slack_thread_json(invoice_id: str):
    data = extract_thread_from_zip(invoice_id)
    return JSONResponse(content=data)

@app.post("/api/upload_zip")
async def upload_zip(file: UploadFile = File(...)):
    content = await file.read()
    # Try writing to configured ZIP_FILE_PATH; fallback to /tmp
    try:
        ZIP_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(ZIP_FILE_PATH, "wb") as f:
            f.write(content)
        saved_path = ZIP_FILE_PATH
    except OSError as e:
        logging.warning("Failed to write ZIP to %s: %s. Falling back to /tmp.", ZIP_FILE_PATH, e)
        tmp = Path("/tmp") / os.environ.get("ZIP_FILENAME", "slack_export_latest.zip")
        with open(tmp, "wb") as f:
            f.write(content)
        saved_path = tmp

    # Clear cache (best-effort)
    try:
        for p in CACHE_DIR.glob("*.json"):
            try:
                p.unlink()
            except Exception:
                logging.debug("Failed to remove cache file %s", p)
    except Exception:
        logging.exception("Failed clearing cache directory")

    return {"status": "✅ ZIP uploaded successfully. Cache cleared.", "path": str(saved_path)}

# ------------------------------------------------------------
# ✅ Render / Vercel ヘルスチェック
# ------------------------------------------------------------
@app.get("/")
def healthcheck():
    return {"status": "ok", "message": "Tousuien Hub is live 🚀"}

# ------------------------------------------------------------
# 🔹 GPTs連携API：/query
# ------------------------------------------------------------
@app.get("/query")
def query_tousuien_hub(text: str):
    """GPTsから呼び出される顧客検索API"""
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
        logging.exception("query_tousuien_hub failed")
        return JSONResponse(status_code=500, content={"error": str(e)})

# ------------------------------------------------------------
# 🔹 アプリ起動（ローカルテスト向け）
# ------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# Vercel expects a variable named `app` or `handler`
handler = app
