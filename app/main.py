"""Tousuien Hub API main application (for Render deployment with Slack integration)"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse, JSONResponse
import zipfile
import json
import os
import re
from datetime import datetime

# =========================================================
# ✅ FastAPI 初期化（RenderサーバーURLを含む）
# =========================================================
app = FastAPI(
    title="Tousuien Hub API on Render",
    version="0.1.0",
    servers=[{"url": "https://tousuien-hub.onrender.com"}],
)

# =========================================================
# ZIPファイル探索
# =========================================================
def find_zip_file():
    candidates = [
        "slack_export_latest.zip",
        "./slack_export_latest.zip",
        "/app/slack_export_latest.zip",
        "../slack_export_latest.zip",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

ZIP_PATH = find_zip_file()

# =========================================================
# ユーザー名マッピング
# =========================================================
USER_MAPPING = {
    "U0606SPN4BW": "古川敏",
    "U08U8MMTH43": "林",
    "U066P2OUQH1": "林遥香",
    "U0331FZTHEK": "片寄",
    # 誤ID対策
    "U066P20UQH1": "林遥香",
}

# =========================================================
# テキスト整形関数
# =========================================================
def clean_slack_text(text):
    if not text:
        return ""
    text = re.sub(r'\*([^\*]+)\*', r'\1', text)
    text = re.sub(r'<@[A-Z0-9]+>', '', text)
    text = re.sub(r'<!subteam\^[A-Z0-9]+\|@[a-z\-]+>', '', text)
    text = re.sub(r'<#[A-Z0-9]+\|[a-z\-]+>', '', text)
    text = re.sub(r':[a-z_\-]+:', '', text)
    text = re.sub(r'<(https?://[^>]+)>', r'\1', text)
    text = re.sub(r'\t+', ' ', text)
    text = re.sub(r' +', ' ', text)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines).strip()

def format_timestamp(ts):
    try:
        dt = datetime.fromtimestamp(float(ts))
        return dt.strftime('%Y年%m月%d日 %H:%M')
    except:
        return ""

# =========================================================
# APIエンドポイント
# =========================================================
@app.get("/")
async def root():
    zip_status = "Found" if ZIP_PATH else "Not Found"
    zip_location = ZIP_PATH if ZIP_PATH else "N/A"
    return {
        "message": "Tousuien Hub API on Render is running",
        "zip_status": zip_status,
        "zip_location": zip_location,
    }

@app.get("/debug/files")
async def debug_files():
    current_dir = os.listdir(".")
    parent_dir = os.listdir("..") if os.path.exists("..") else []
    return {
        "current_directory": os.getcwd(),
        "files_in_current": current_dir,
        "files_in_parent": parent_dir,
        "zip_path_detected": ZIP_PATH,
    }

@app.get("/slack/thread/{invoice}")
async def get_slack_thread(invoice: str, format: str = Query("json")):
    if not ZIP_PATH:
        raise HTTPException(status_code=404, detail="ZIP file not found")

    if not os.path.exists(ZIP_PATH):
        raise HTTPException(status_code=404, detail=f"ZIP path invalid: {ZIP_PATH}")

    threads = []
    try:
        with zipfile.ZipFile(ZIP_PATH, "r") as zf:
            for name in zf.namelist():
                if not name.endswith(".json"):
                    continue
                try:
                    with zf.open(name) as f:
                        data = json.load(f)
                        for msg in data:
                            text = msg.get("text", "")
                            if invoice in text:
                                thread_ts = msg.get("thread_ts") or msg.get("ts")
                                thread_messages = []
                                for m in data:
                                    if m.get("ts") == thread_ts:
                                        thread_messages.append(m)
                                for m in data:
                                    if m.get("thread_ts") == thread_ts and m.get("ts") != thread_ts:
                                        thread_messages.append(m)
                                if thread_messages:
                                    threads.append({
                                        "file": name,
                                        "thread_ts": thread_ts,
                                        "messages": thread_messages
                                    })
                                break
                except Exception:
                    continue
    except zipfile.BadZipFile:
        raise HTTPException(status_code=500, detail="Invalid ZIP file")

    if not threads:
        return JSONResponse(
            status_code=404,
            content={"error": f"No messages found for invoice {invoice}"}
        )

    if format == "json":
        return {"invoice": invoice, "threads": threads}

    # ===============================
    # 日本語整形出力
    # ===============================
    text_output = f"📄 スレッド：{invoice}\n{'='*60}\n\n"
    for thread in threads:
        file_name = thread["file"]
        try:
            file_name_bytes = file_name.encode("latin-1")
            try:
                file_name = file_name_bytes.decode("utf-8")
            except:
                file_name = file_name_bytes.decode("cp932", errors="ignore")
        except:
            pass

        text_output += f"📁 ファイル: {file_name}\n\n"
        sorted_messages = sorted(thread["messages"], key=lambda x: float(x.get("ts", 0)))

        for i, m in enumerate(sorted_messages):
            user_id = m.get("user", "不明")
            user_name = USER_MAPPING.get(user_id, user_id)
            text = clean_slack_text(m.get("text", ""))
            timestamp = format_timestamp(m.get("ts", ""))
            if not text:
                continue
            prefix = f"🟢 {user_name}" if user_id in USER_MAPPING else f"👤 {user_name}"
            if timestamp:
                prefix += f" ({timestamp})"
            indent = "" if i == 0 else "  ↳ "
            text_output += f"{indent}{prefix}:\n{text}\n\n{'-'*60}\n\n"

    return PlainTextResponse(text_output, media_type="text/plain; charset=utf-8")

# =========================================================
# OpenAPI出力（ChatGPT Actions対応用）
# =========================================================
@app.get("/openapi.json", include_in_schema=False)
async def custom_openapi():
    openapi_schema = app.openapi()
    openapi_schema["servers"] = [{"url": "https://tousuien-hub.onrender.com"}]
    return JSONResponse(openapi_schema)
