from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse, JSONResponse
import zipfile
import json
import os
from pathlib import Path

app = FastAPI(title="Tousuien Hub API on Render")

# ZIPファイルのパスを複数候補で探索
def find_zip_file():
    candidates = [
        "slack_export_latest.zip",
        "./slack_export_latest.zip",
        "/app/slack_export_latest.zip",
        "../slack_export_latest.zip",
        "海外 Slack export 最新.zip",
    ]
    
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

ZIP_PATH = find_zip_file()

# ユーザーIDから名前へのマッピング
USER_MAPPING = {
    "U0606SPN4BW": "古川",
    "U08U8MMTH43": "林",
    "U0331FZTHEK": "片寄",
    # 必要に応じて追加
}

@app.get("/")
async def root():
    zip_status = "Found" if ZIP_PATH else "Not Found"
    zip_location = ZIP_PATH if ZIP_PATH else "N/A"
    return {
        "message": "Tousuien Hub API on Render is running",
        "zip_status": zip_status,
        "zip_location": zip_location
    }

@app.get("/debug/files")
async def debug_files():
    """デバッグ用：利用可能なファイル一覧を表示"""
    current_dir = os.listdir(".")
    parent_dir = os.listdir("..") if os.path.exists("..") else []
    return {
        "current_directory": os.getcwd(),
        "files_in_current": current_dir,
        "files_in_parent": parent_dir,
        "zip_path_detected": ZIP_PATH
    }

@app.get("/slack/thread/{invoice}")
async def get_slack_thread(invoice: str, format: str = Query("json")):
    if not ZIP_PATH:
        raise HTTPException(
            status_code=404, 
            detail="ZIP file not found. Please check /debug/files endpoint"
        )
    
    if not os.path.exists(ZIP_PATH):
        raise HTTPException(
            status_code=404,
            detail=f"ZIP file path '{ZIP_PATH}' exists but file is not accessible"
        )

    threads = []
    
    try:
        with zipfile.ZipFile(ZIP_PATH, "r") as zf:
            for name in zf.namelist():
                if not name.endswith(".json"):
                    continue
                
                try:
                    with zf.open(name) as f:
                        data = json.load(f)
                        
                        # インボイス番号を含むメッセージを検索
                        for msg in data:
                            text = msg.get("text", "")
                            if invoice in text:
                                thread_ts = msg.get("ts")
                                
                                # 同じスレッドのメッセージを収集
                                thread_messages = [
                                    m for m in data 
                                    if m.get("thread_ts") == thread_ts or m.get("ts") == thread_ts
                                ]
                                
                                threads.append({
                                    "file": name,
                                    "thread_ts": thread_ts,
                                    "messages": thread_messages
                                })
                                break  # 1ファイル内で最初に見つかったスレッドのみ
                
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    continue
    
    except zipfile.BadZipFile:
        raise HTTPException(status_code=500, detail="Invalid ZIP file format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading ZIP: {str(e)}")

    if not threads:
        return JSONResponse(
            status_code=404,
            content={"error": f"No messages found for invoice {invoice}"}
        )

    # JSON出力モード
    if format == "json":
        return {"invoice": invoice, "threads": threads}

    # 日本語整形モード
    text_output = f"📄 スレッド：{invoice}\n{'='*60}\n\n"
    
    for thread in threads:
        text_output += f"📁 ファイル: {thread['file']}\n\n"
        
        # メッセージをタイムスタンプ順にソート
        sorted_messages = sorted(thread["messages"], key=lambda x: float(x.get("ts", 0)))
        
        for m in sorted_messages:
            user_id = m.get("user", "不明")
            user_name = USER_MAPPING.get(user_id, user_id)
            text = m.get("text", "")
            
            # Slackの特殊記法をクリーンアップ
            text = text.replace("<!subteam^", "@")
            text = text.replace(">", "")
            text = text.replace("|", " ")
            text = text.replace("\t", " ")
            
            # 複数の改行を整理
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            text = "\n".join(lines)
            
            # TOUSUIEN側（社内）の発言を🟢で色付け
            if user_id in USER_MAPPING:
                prefix = f"🟢 {user_name}"
            else:
                prefix = f"👤 {user_name}"
            
            text_output += f"{prefix}:\n{text}\n\n{'-'*60}\n\n"
    
    return PlainTextResponse(text_output, media_type="text/plain; charset=utf-8")
