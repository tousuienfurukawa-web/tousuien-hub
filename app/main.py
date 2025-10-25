# -*- coding: utf-8 -*-
"""
app/main.py
Safe, deploy-friendly FastAPI application for Slack thread inspection + GPT summary.
- 安全な gpt5_summary のインポート（存在しない場合は代替を使う）
- 読み取り専用ファイルシステムへのフォールバック (/tmp)
- フォールバックしても動くように例外処理を強化
- Vercel 等のサーバレス環境で「handler/app が無い」エラーが出ないよう app を公開
"""

import logging
import os
import re
import json
import zipfile
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional, List, Dict, Any

# ロガー
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tousuien_hub")

# ---------------------------
# 環境に応じたパス決定（書き込み不可を考慮）
# ---------------------------
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_ZIP = BASE_DIR / "slack_export_latest.zip"
DEFAULT_CACHE = BASE_DIR / "cache_slack_threads"

def _writable_path(path: Path) -> Path:
    """path が書き込み可能ならそのまま、そうでなければ /tmp にフォールバックする"""
    try:
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)
        test = parent / ".perm_test"
        with open(test, "w") as f:
            f.write("ok")
        test.unlink()
        return path
    except Exception:
        fallback = Path("/tmp") / path.name
        logger.warning("Filesystem read-only or no permission. Using fallback: %s", str(fallback))
        return fallback

ZIP_FILE_PATH = _writable_path(DEFAULT_ZIP)
CACHE_DIR = _writable_path(DEFAULT_CACHE)
# CACHE_DIR はディレクトリなので Path(...)/.. 指定にする
if CACHE_DIR.suffix:  # if ends with filename, turn into dir
    CACHE_DIR = CACHE_DIR.parent / CACHE_DIR.stem
try:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:
    # 最終フォールバック
    CACHE_DIR = Path("/tmp/cache_slack_threads")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    logger.warning("Could not create CACHE_DIR at default; using %s", CACHE_DIR)

# ---------------------------
# 安全なインポート: gpt5_summary.generate_slack_summary
# ---------------------------
generate_slack_summary = None
try:
    # 優先: 相対インポート（パッケージ内）
    from .gpt5_summary import generate_slack_summary  # type: ignore
    logger.info("Imported gpt5_summary via relative import")
except Exception as e_rel:
    try:
        # 代替: 絶対インポート
        from gpt5_summary import generate_slack_summary  # type: ignore
        logger.info("Imported gpt5_summary via absolute import")
    except Exception as e_abs:
        logger.exception("gpt5_summary could not be imported; functionality will be disabled.")
        generate_slack_summary = None

# もし generate_slack_summary がない場合のフォールバック実装
def _dummy_generate_slack_summary(invoice_id: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """gpt5_summary が無い場合のダミー。UI 崩壊防止用。"""
    text_snippet = ""
    if messages and isinstance(messages, list):
        # ちょっとした抜粋を返す
        joined = "\n".join((m.get("text") or "") for m in messages[:3])
        text_snippet = joined[:800]
    return {"summary": f"⚠️ GPT 要約機能が利用できません。件名: {invoice_id}\n\n抜粋:\n{text_snippet}"}

if generate_slack_summary is None:
    generate_slack_summary = _dummy_generate_slack_summary

# ---------------------------
# ユーティリティ関数
# ---------------------------
def normalize_invoice_text(text: str) -> str:
    if text is None:
        return ""
    return text.lower().replace("-", "").replace(" ", "").replace("_", "")

def format_timestamp(ts) -> str:
    try:
        dt = datetime.fromtimestamp(float(ts))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts or "")

def escape_html(text: Optional[str]) -> str:
    return (text or "").replace("<", "&lt;").replace(">", "&gt;")

def resolve_user_name(user_id: Optional[str]) -> str:
    """
    簡易ユーザ解決:
    - None => 'Unknown'
    - 文字列 => そのまま
    - dict => dict.get('name') or 'Unknown'
    実運用では Slack エクスポートの users.json をパースしてマッピングできますが、
    環境によってないケースがあるため安全に実装します。
    """
    if not user_id:
        return "Unknown"
    if isinstance(user_id, dict):
        return user_id.get("name") or user_id.get("real_name") or "Unknown"
    return str(user_id)

# ---------------------------
# 検索 / 抽出ロジック
# ---------------------------
def find_invoice_candidates(keyword: str) -> List[str]:
    normalized_kw = normalize_invoice_text(keyword)
    candidates: List[str] = []
    if not ZIP_FILE_PATH.exists():
        logger.info("ZIP file not found at %s", ZIP_FILE_PATH)
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
                    logger.debug("JSON load error in %s: %s", name, e)
                    continue

                if not isinstance(data, list):
                    continue

                for msg in data:
                    text = ""
                    if isinstance(msg, dict):
                        text = msg.get("text", "")
                    elif isinstance(msg, str):
                        text = msg
                    if not text:
                        continue

                    if normalized_kw in normalize_invoice_text(text):
                        m = re.search(r"TSE-[A-Z0-9]+-\d{3}-\d{2}", text)
                        if m:
                            invoice = m.group(0)
                            if invoice not in candidates:
                                candidates.append(invoice)
                                logger.debug("Found invoice candidate: %s in %s", invoice, name)
    except Exception as e:
        logger.exception("Error while scanning zip for candidates: %s", e)

    logger.info("Candidates found for %s: %s", keyword, candidates)
    return candidates

def extract_thread_from_zip(invoice_id: str) -> Dict[str, Any]:
    invoice_id = str(invoice_id)
    normalized_invoice = normalize_invoice_text(invoice_id)
    cache_path = CACHE_DIR / f"{invoice_id}.json"

    # キャッシュがあれば返す（高速化）
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # キャッシュ壊れたら無視して再抽出
            logger.warning("Cache read failed for %s; will re-extract", cache_path)

    if not ZIP_FILE_PATH.exists():
        return {"error": f"ZIP file not found at {ZIP_FILE_PATH}"}

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

                    for other_msg in data:
                        if not isinstance(other_msg, dict):
                            continue
                        other_thread_ts = other_msg.get("thread_ts", other_msg.get("ts"))
                        if other_thread_ts == thread_ts and other_msg.get("ts") != ts:
                            thread_messages.append(other_msg)

                    # resolve user name for each message
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
    except Exception as e:
        logger.exception("Error extracting from ZIP: %s", e)
        return {"error": str(e)}

    data = {"invoice": invoice_id, "messages": matches}
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.warning("Could not write cache to %s; continuing without cache", cache_path)

    return data

# ---------------------------
# HTML 生成
# ---------------------------
def build_raw_html(invoice_id: str, msgs: List[Dict[str, Any]]) -> str:
    html_msgs = ""
    for t in msgs:
        html_msgs += f"<h2>💬 スレッド開始: {escape_html(t.get('text') or '')}</h2>"
        for m in t.get("all_messages", []):
            user = m.get("user", "Unknown")
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
    return f"<div><h1>📋 {escape_html(invoice_id)}</h1>{html_msgs}</div>"

def build_report_html(invoice_id: str, msgs: List[Dict[str, Any]], gpt_info: Dict[str, Any]) -> str:
    total_threads = len(msgs)
    total_messages = sum(len(m.get("all_messages", [])) for m in msgs)
    participants = sorted({m.get("user") for t in msgs for m in t.get("all_messages", [])})
    latest_ts = max((float(m.get("ts", 0) or 0) for t in msgs for m in t.get("all_messages", []) if m.get("ts")), default=0)
    last_updated = format_timestamp(latest_ts)
    status_text = escape_html(gpt_info.get("status") if isinstance(gpt_info, dict) else str(gpt_info))
    return f"""
      <div class="card">
        <h2>🧠 要約ビュー: {escape_html(invoice_id)}</h2>
        <p style="color:#475569;">最終更新: {last_updated}</p>
        <div class="summary">{status_text}</div>
        <div class="stat"><strong>スレッド数:</strong> {total_threads}</div>
        <div class="stat"><strong>総メッセージ数:</strong> {total_messages}</div>
        <div class="stat"><strong>関係者:</strong> {", ".join(participants[:10])}</div>
      </div>
    """

# ---------------------------
# FastAPI アプリ定義
# ---------------------------
app = FastAPI(
    title="Tousuien Hub",
    description="Slack thread viewer and GPT summary helper",
)

# 互換のため handler も公開（Vercel などが handler を期待することがあるため）
handler = app  # safe alias

# ------------------------------------------------------------
# エンドポイント
# ------------------------------------------------------------
@app.get("/", response_class=JSONResponse)
def healthcheck():
    return {"status": "ok", "message": "Tousuien Hub is live 🚀"}

@app.get("/slack/thread_html/{keyword}", response_class=HTMLResponse)
async def get_slack_thread_html(keyword: str):
    try:
        candidates = find_invoice_candidates(keyword)
        if len(candidates) == 1:
            invoice_id = candidates[0]
            data = extract_thread_from_zip(invoice_id)
            if "error" in data:
                return HTMLResponse(f"<h3>❌ {escape_html(data['error'])}</h3>", status_code=500)
            if not data.get("messages"):
                return HTMLResponse(f"<h3>❌ スレッドが見つかりません（{escape_html(invoice_id)}）</h3>", status_code=404)

            msgs = data["messages"]
            raw_html_section = build_raw_html(invoice_id, msgs)
            all_thread_messages = [m for t in msgs for m in t.get("all_messages", [])]
            try:
                gpt_result = generate_slack_summary(invoice_id, all_thread_messages) or {}
            except Exception as e:
                logger.exception("generate_slack_summary failed: %s", e)
                gpt_result = {"summary": "⚠️ 要約生成中にエラーが発生しました。"}
            gpt_info = {"status": gpt_result.get("summary", "⚠️ 要約生成中にエラーが発生しました")}
            summary_html_section = build_report_html(invoice_id, msgs, gpt_info)

            return HTMLResponse(f"""
            <html><head><meta charset='utf-8'><title>{escape_html(invoice_id)}</title></head>
            <body><div class='container'>
            <h2>💬 全文表示（Raw）</h2>{raw_html_section}
            <h2>🧠 GPT-5要約</h2>{summary_html_section}
            </div></body></html>
            """)
        elif len(candidates) > 1:
            # 複数候補がある場合は一覧を出しつつ簡易要約を表示
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
            except Exception as e:
                logger.exception("generate_slack_summary multiple failed: %s", e)
                summary_text = "⚠️ 要約生成に失敗しました。"

            html_list = "<ul>" + "".join(f"<li><a href='/slack/thread_html/{inv}'>{inv}</a></li>" for inv in candidates) + "</ul>"

            return HTMLResponse(f"""
            <html><head><meta charset='utf-8'><title>{escape_html(keyword.upper())} 概要</title></head>
            <body>
            <h1>🏢 {escape_html(keyword.upper())} 関連スレッド一覧</h1>
            {html_list}
            <h2>🧠 企業概要・近況要約</h2>
            <div style='background:#eff6ff;padding:16px;border-left:5px solid #3b82f6;white-space:pre-wrap;'>{escape_html(summary_text)}</div>
            </body></html>
            """)
        else:
            return HTMLResponse(f"<h3>❌ 該当するスレッドが見つかりません（{escape_html(keyword)}）</h3>", status_code=404)
    except Exception as e:
        logger.exception("Error in get_slack_thread_html: %s", e)
        return HTMLResponse(f"<h3>❌ サーバーエラーが発生しました: {escape_html(str(e))}</h3>", status_code=500)

@app.get("/api/slack_threads/{invoice_id}.json", response_class=JSONResponse)
async def get_slack_thread_json(invoice_id: str):
    try:
        data = extract_thread_from_zip(invoice_id)
        if "error" in data:
            return JSONResponse(status_code=500, content=data)
        return JSONResponse(content=data)
    except Exception as e:
        logger.exception("Error in get_slack_thread_json: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/upload_zip")
async def upload_zip(file: UploadFile = File(...)):
    try:
        content = await file.read()
        try:
            # 安全に書き込み可能な場所へ保存（ZIP_FILE_PATH は既にフォールバック済）
            with open(ZIP_FILE_PATH, "wb") as f:
                f.write(content)
        except Exception:
            # 最終フォールバック: /tmp
            fallback = Path("/tmp/slack_export_latest.zip")
            with open(fallback, "wb") as f:
                f.write(content)
            logger.warning("Could not write to %s; wrote to fallback %s", ZIP_FILE_PATH, fallback)
            # Update global path to fallback so subsequent calls use it
            global ZIP_FILE_PATH
            ZIP_FILE_PATH = fallback

        # キャッシュ削除
        for p in list(CACHE_DIR.glob("*.json")):
            try:
                p.unlink()
            except Exception:
                logger.debug("Could not unlink cache file %s", p)

        return {"status": "✅ ZIP uploaded successfully. Cache cleared."}
    except Exception as e:
        logger.exception("upload_zip failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/query")
def query_tousuien_hub(text: str):
    """GPTsから呼び出される顧客検索API（ダミー）"""
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
        logger.exception("query_tousuien_hub failed: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})

# ---------------------------
# 起動用（ローカル実行）
# ---------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
