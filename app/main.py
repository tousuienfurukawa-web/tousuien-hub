from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse, JSONResponse
import zipfile
import json
import os
import re
from datetime import datetime

app = FastAPI(title="Tousuien Hub API on Render")

# ZIPファイルのパスを複数候補で探索
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

# ユーザーIDから名前へのマッピング（拡張版）
USER_MAPPING = {
    "U0606SPN4BW": "古川敏",
    "U08U8MMTH43": "林",
    "U066P2OUQH1": "林遥香",
    "U0331FZTHEK": "片寄",
    # スクリーンショットで確認したID
    "U066P20UQH1": "林遥香",
    # 必要に応じて追加
}

def clean_slack_text(text):
    """Slackの特殊記法をクリーンアップ"""
    if not text:
        return ""
    
    # Markdownの太字 *text* を削除
    text = re.sub(r'\*([^\*]+)\*', r'\1', text)
    
    # ユーザーメンション <@U123456> を削除
    text = re.sub(r'<@[A-Z0-9]+>', '', text)
    
    # チームメンション <!subteam^...> を削除
    text = re.sub(r'<!subteam\^[A-Z0-9]+\|@[a-z\-]+>', '', text)
    
    # チャンネルメンション <#C123456|channel> を削除
    text = re.sub(r'<#[A-Z0-9]+\|[a-z\-]+>', '', text)
    
    # 絵文字コード :emoji: を削除
    text = re.sub(r':[a-z_\-]+:', '', text)
    
    # URL <http://...> から <>を削除
    text = re.sub(r'<(https?://[^>]+)>', r'\1', text)
    
    # 複数のタブ・スペースを1つに
    text = re.sub(r'\t+', ' ', text)
    text = re.sub(r' +', ' ', text)
    
    # 複数の改行を整理
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    text = '\n'.join(lines)
    
    return text.strip()

def format_timestamp(ts):
    """タイムスタンプを日本語日時に変換"""
    try:
        dt = datetime.fromtimestamp(float(ts))
        return dt.strftime('%Y年%m月%d日 %H:%M')
    except:
        return ""

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
                                thread_ts = msg.get("thread_ts") or msg.get("ts")
                                
                                # 同じスレッドの全メッセージを収集
                                # 親メッセージ + 返信メッセージ
                                thread_messages = []
                                
                                # まず親メッセージを追加
                                parent_msg = None
                                for m in data:
                                    if m.get("ts") == thread_ts:
                                        parent_msg = m
                                        thread_messages.append(m)
                                        break
                                
                                # 次に返信メッセージを追加
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
        # ファイル名をデコード（文字化け対策）
        file_name = thread['file']
        try:
            # Shift-JIS/CP932でデコードを試みる（日本語Windows対応）
            file_name_bytes = file_name.encode('latin-1')
            try:
                file_name = file_name_bytes.decode('utf-8')
            except:
                try:
                    file_name = file_name_bytes.decode('shift-jis')
                except:
                    file_name = file_name_bytes.decode('cp932', errors='ignore')
        except:
            pass
        
        text_output += f"📁 ファイル: {file_name}\n\n"
        
        # メッセージをタイムスタンプ順にソート
        sorted_messages = sorted(thread["messages"], key=lambda x: float(x.get("ts", 0)))
        
        for i, m in enumerate(sorted_messages):
            user_id = m.get("user", "不明")
            user_name = USER_MAPPING.get(user_id, user_id)
            text = m.get("text", "")
            timestamp = format_timestamp(m.get("ts", ""))
            
            # テキストをクリーンアップ
            text = clean_slack_text(text)
            
            # 空のメッセージはスキップ
            if not text:
                continue
            
            # TOUSUIEN側（社内）の発言を🟢で色付け
            if user_id in USER_MAPPING:
                prefix = f"🟢 {user_name}"
            else:
                prefix = f"👤 {user_name}"
            
            # タイムスタンプを追加
            if timestamp:
                prefix += f" ({timestamp})"
            
            # 親メッセージと返信を区別
            indent = "" if i == 0 else "  ↳ "
            
            text_output += f"{indent}{prefix}:\n{text}\n\n{'-'*60}\n\n"
    
    return PlainTextResponse(text_output, media_type="text/plain; charset=utf-8")
