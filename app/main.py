"""Tousuien Hub API main application (Render版・Slackスレッド完全対応)"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse, JSONResponse
import zipfile
import json
import os
import re
from datetime import datetime

# =========================================================
# FastAPI 初期化（Render接続対応）
# =========================================================
app = FastAPI(
    title="Tousuien Hub API on Render",
    version="0.2.0",
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
    "U066P20UQH1": "林遥香",  # 誤ID補正
    "U062E1T8UF0": "足立",
}

# =========================================================
# テキスト整形関数
# =========================================================
def clean_slack_text(text):
    if not text:
        return ""
    text = re.sub(r'\*([^\*]+)\*', r'\1', text)  # 太字削除
    text = re.sub(r'<@[A-Z0-9]+>', '', text)  # ユーザーメンション削除
    text = re.sub(r'<!subteam\^[A-Z0-9]+\|@[a-z\-]+>', '', text)  # サブチーム削除
    text = re.sub(r'<#[A-Z0-9]+\|[a-z\-]+>', '', text)  # チャンネル削除
    text = re.sub(r':[a-zA-Z0-9_\-\+]+:', '', text)  # 絵文字削除
    text = re.sub(r'<(https?://[^>]+)>', r'\1', text)  # URL整形
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
    return {
        "message": "Tousuien Hub API is running on Render",
        "zip_status": "Found" if ZIP_PATH else "Not Found",
        "zip_location": ZIP_PATH or "N/A",
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

# =========================================================
# 改良版：Slackスレッド全日対応 + リアクション抽出
# =========================================================
@app.get("/slack/thread/{invoice}")
async def get_slack_thread(invoice: str, format: str = Query("json")):
    if not ZIP_PATH:
        raise HTTPException(status_code=404, detail="ZIP file not found")

    threads = {}
    target_thread_ts = None

    try:
        with zipfile.ZipFile(ZIP_PATH, "r") as zf:
            # 親メッセージを特定
            for name in zf.namelist():
                if not name.endswith(".json"):
                    continue
                with zf.open(name) as f:
                    try:
                        data = json.load(f)
                    except:
                        continue
                    for msg in data:
                        text = msg.get("text", "")
                        if invoice in text:
                            target_thread_ts = msg.get("thread_ts") or msg.get("ts")
                            threads.setdefault(target_thread_ts, []).append((name, msg))

            # 同一thread_tsの返信を全ファイル横断で収集
            if target_thread_ts:
                for name in zf.namelist():
                    if not name.endswith(".json"):
                        continue
                    with zf.open(name) as f:
                        try:
                            data = json.load(f)
                        except:
                            continue
                        for msg in data:
                            if msg.get("thread_ts") == target_thread_ts and msg.get("ts") != target_thread_ts:
                                threads[target_thread_ts].append((name, msg))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not threads:
        return {"error": f"No messages found for invoice {invoice}"}

    # =========================================================
    # 整形出力（日本語フォーマット）
    # =========================================================
    text_output = f"📄 スレッド：{invoice}\n{'='*60}\n\n"

    for thread_ts, entries in threads.items():
        sorted_entries = sorted(entries, key=lambda x: float(x[1].get("ts", 0)))

        for file_name, msg in sorted_entries:
            user_id = msg.get("user", "不明")
            user_name = USER_MAPPING.get(user_id, user_id)
            text = clean_slack_text(msg.get("text", ""))
            timestamp = format_timestamp(msg.get("ts", ""))
            reactions = msg.get("reactions", [])

            # 絵文字リアクション整形
            if reactions:
                react_str = " | ".join(
                    [f"{r['name']}×{r['count']}" for r in reactions if 'name' in r]
                )
            else:
                react_str = ""

            if not text and not reactions:
                continue

            prefix = f"🟢 {user_name}" if user_id in USER_MAPPING else f"👤 {user_name}"
            text_output += f"{prefix}（{timestamp}）\n{text}\n"
            if react_str:
                text_output += f"　💬 リアクション: {react_str}\n"
            text_output += "-" * 60 + "\n"

    # JSON or PlainText 出力
    if format == "json":
        return {"invoice": invoice, "thread_ts": target_thread_ts, "messages": [m[1] for m in entries]}
    else:
        return PlainTextResponse(text_output, media_type="text/plain; charset=utf-8")

# =========================================================
# ChatGPT用 OpenAPI出力
# =========================================================
@app.get("/openapi.json", include_in_schema=False)
async def custom_openapi():
    openapi_schema = app.openapi()
    openapi_schema["servers"] = [{"url": "https://tousuien-hub.onrender.com"}]
    return JSONResponse(openapi_schema)
