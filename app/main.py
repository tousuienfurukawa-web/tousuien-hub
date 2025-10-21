# -*- coding: utf-8 -*-
import os
import zipfile
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse

# ======================================================
# 🚀 FastAPI アプリケーション設定
# ======================================================
app = FastAPI()

# ZIPファイルのパス
ZIP_FILE_PATH = Path("slack_export_latest.zip")


# ======================================================
# 🧾 全SlackエクスポートZIP（旧形式・新形式）検索
# ======================================================
@app.get("/slack/thread/{invoice_id}")
async def get_slack_thread(invoice_id: str):
    """SlackエクスポートZIPの全ファイル（旧新形式対応）から受注番号スレッド検索しJSONで返す"""
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}

    try:
        with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
            matches = []
            all_files = z.namelist()

            for name in all_files:
                # ZIP内ファイル名をUTF-8に変換
                try:
                    decoded_name = name.encode("cp437").decode("utf-8", errors="ignore")
                except Exception:
                    decoded_name = name

                if not decoded_name.endswith(".json"):
                    continue

                # JSONファイルを開いて読み込む
                try:
                    with z.open(name) as f:
                        data = json.load(f)
                except Exception:
                    continue

                # メッセージ本文に受注番号を含むかチェック
                for msg in data:
                    text = msg.get("text", "")
                    if invoice_id not in text:
                        continue

                    entry = {
                        "file": decoded_name,
                        "channel": decoded_name.split("/")[0] if "/" in decoded_name else "(root)",
                        "user": msg.get("user", ""),
                        "text": text,
                        "ts": msg.get("ts", ""),
                        "replies": []
                    }

                    ts = msg.get("ts")
                    if ts:
                        # 新形式 threads/ フォルダ内
                        thread_path_new = f"{entry['channel']}/threads/{ts}.json"
                        # 旧形式 ルート直下
                        thread_path_old = f"{ts}.json"

                        for tpath in [thread_path_new, thread_path_old]:
                            if tpath in all_files:
                                try:
                                    with z.open(tpath) as tf:
                                        replies = json.load(tf)
                                        for r in replies:
                                            entry["replies"].append({
                                                "user": r.get("user", ""),
                                                "text": r.get("text", "")
                                            })
                                except Exception:
                                    pass

                    matches.append(entry)

            if not matches:
                return {"status": "not found", "invoice": invoice_id}

            return {
                "invoice": invoice_id,
                "count": len(matches),
                "messages": matches
            }

    except Exception as e:
        return {"error": str(e)}


# ======================================================
# 📦 ZIPダウンロード確認用
# ======================================================
@app.get("/slack_export_latest.zip")
async def get_slack_export():
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}
    return FileResponse(
        path=str(ZIP_FILE_PATH),
        media_type="application/zip",
        filename="slack_export_latest.zip"
    )


# ======================================================
# 🚀 起動時ログ
# ======================================================
@app.on_event("startup")
async def startup_event():
    print("🚀 アプリ起動中...")
    if ZIP_FILE_PATH.exists():
        print(f"✅ ZIP found: {ZIP_FILE_PATH}")
    else:
        print("⚠️ ZIP file not found at startup")
