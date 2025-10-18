"""Tousuien Hub API main application (Render安定版・ChatGPT完全対応)"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import zipfile
import json
import os
import re
from datetime import datetime

# =========================================================
# FastAPI 初期化
# =========================================================
app = FastAPI(
    title="Tousuien Hub API on Render",
    version="0.4.0",
    servers=[{"url": "https://tousuien-hub.onrender.com"}],
)

# =========================================================
# ZIPファイル探索
# =========================================================
def find_zip_file():
    for path in [
        "slack_export_latest.zip",
        "./slack_export_latest.zip",
        "/app/slack_export_latest.zip",
        "../slack_export_latest.zip",
    ]:
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
    "U062E1T8UF0": "足立",
    "U066P20UQH1": "林遥香",  # ID重複補正
}

# =========================================================
# テキスト整形
# =========================================================
def clean_slack_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\*([^\*]+)\*', r'\1', text)
    text = re.sub(r'<@[A-Z0-9]+>', '', text)
    text = re.sub(r'<!subteam\^[A-Z0-9]+\|@[a-z\-]+>', '', text)
    text = re.sub(r'<#[A-Z0-9]+\|[a-z\-]+>', '', text)
    text = re.sub(r':[a-zA-Z0-9_\-\+]+:', '', text)
    text = re.sub(r'<(https?://[^>]+)>', r'\1', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def format_timestamp(ts: str) -> str:
    try:
        dt = datetime.fromtimestamp(float(ts))
        return dt.strftime("%Y年%m月%d日 %H:%M")
    except Exception:
        return ""

# =========================================================
# ルートエンドポイント
# =========================================================
@app.get("/")
async def root():
    return {
        "message": "Tousuien Hub API is running on Render",
        "zip_status": "Found" if ZIP_PATH else "Not Found",
        "zip_location": ZIP_PATH or "N/A",
    }

# =========================================================
# Slackスレッド取得エンドポイント（ChatGPT完全対応版）
# =========================================================
@app.get("/slack/thread/{invoice}")
async def get_slack_thread(invoice: str, format: str = Query("json")):
    if not ZIP_PATH:
        raise HTTPException(status_code=404, detail="ZIP file not found")

    results = []
    thread_ts = None

    # -----------------------------------------------------
    # 1️⃣ ZIP内を探索して対象スレッドを検出
    # -----------------------------------------------------
    try:
        with zipfile.ZipFile(ZIP_PATH, "r") as zf:
            for name in zf.namelist():
                if not name.endswith(".json"):
                    continue
                with zf.open(name) as f:
                    try:
                        data = json.load(f)
                    except:
                        continue
                    # 親メッセージを特定
                    for msg in data:
                        if invoice in msg.get("text", ""):
                            thread_ts = msg.get("thread_ts") or msg.get("ts")
                            results.append((name, msg))
                    # 同じスレッドの返信を追加
                    if thread_ts:
                        for msg in data:
                            if msg.get("thread_ts") == thread_ts and msg.get("ts") != thread_ts:
                                results.append((name, msg))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # -----------------------------------------------------
    # 2️⃣ 結果が空の場合
    # -----------------------------------------------------
    if not results:
        return {
            "invoice": invoice,
            "threads": [],
            "formatted_text": f"❌ スレッドが見つかりません: {invoice}",
        }

    # -----------------------------------------------------
    # 3️⃣ 整形処理
    # -----------------------------------------------------
    results.sort(key=lambda x: float(x[1].get("ts", 0)))
    threads = []
    formatted_text = f"📄 スレッド：{invoice}\n{'='*60}\n\n"

    for name, msg in results:
        user_id = msg.get("user", "")
        user_name = USER_MAPPING.get(user_id, user_id)
        text = clean_slack_text(msg.get("text", ""))
        timestamp = format_timestamp(msg.get("ts", ""))
        reactions = msg.get("reactions", [])

        # リアクション整理
        react_summary = [
            {"emoji": r.get("name"), "count": r.get("count")}
            for r in reactions if "name" in r
        ]
        react_text = (
            "　💬 リアクション: " + " | ".join(
                [f"{r['emoji']}×{r['count']}" for r in react_summary]
            ) if react_summary else ""
        )

        prefix = "🟢" if user_name in USER_MAPPING.values() else "👤"
        formatted_text += f"{prefix} {user_name}（{timestamp}）\n{text}\n{react_text}\n{'-'*60}\n"

        threads.append({
            "file": name,
            "user": user_name,
            "text": text,
            "timestamp": timestamp,
            "reactions": react_summary,
        })

    # -----------------------------------------------------
    # 4️⃣ ChatGPTが常に受け取れる形式（dict）で返す
    # ---------
