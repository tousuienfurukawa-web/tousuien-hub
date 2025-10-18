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
    "U0606SPN4BW": "古川",
    "U0606SPN4BW": "古川敏",
"U08U8MMTH43": "林",
"U066P2OUQH1": "林遥香",
"U0331FZTHEK": "片寄",
    "U06P2OUQH1": "林遥香",
    "U0606SPN4BW": "古川敏",
    # スクリーンショットで確認したID
    "U066P20UQH1": "林遥香",
# 必要に応じて追加
}

@@ -40,6 +40,9 @@
if not text:
return ""

    # Markdownの太字 *text* を削除
    text = re.sub(r'\*([^\*]+)\*', r'\1', text)
    
# ユーザーメンション <@U123456> を削除
text = re.sub(r'<@[A-Z0-9]+>', '', text)

@@ -179,42 +182,49 @@
# ファイル名をデコード（文字化け対策）
file_name = thread['file']
try:
            # UTF-8でデコードを試みる
            file_name = file_name.encode('cp437').decode('utf-8')
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
