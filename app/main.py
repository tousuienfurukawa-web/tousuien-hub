from fastapi import FastAPI, UploadFile, File
import zipfile
import os
import json
import io

app = FastAPI(title="Tousuien Hub API (Render Edition)")

# === ZIPファイルを直接POSTで受け取る ===
@app.post("/slack/import-zip")
async def import_zip(file: UploadFile = File(...)):
    """SlackエクスポートZIPを直接アップロードして保存・展開"""
    try:
        filename = "海外 Slack export 最新.zip"
        with open(filename, "wb") as f:
            content = await file.read()
            f.write(content)
        if not zipfile.is_zipfile(filename):
            return {"error": "Invalid ZIP file"}
        return {"status": "success", "message": f"ZIPを保存しました: {filename}"}
    except Exception as e:
        return {"error": str(e)}


# === ZIPからスレッド抽出 ===
@app.get("/slack/thread/{invoice}")
async def get_slack_thread(invoice: str):
    """ZIP内からインボイス番号を含むスレッドを抽出"""
    zip_path = "海外 Slack export 最新.zip"
    if not os.path.exists(zip_path):
        return {"error": "ZIP file not found"}
    if not zipfile.is_zipfile(zip_path):
        return {"error": "File is not a zip file"}

    result = {"invoice": invoice, "messages": []}
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [f for f in zf.namelist() if f.endswith(".json")]
        for name in names:
            data = json.loads(zf.read(name))
            for msg in data:
                if "text" in msg and invoice in msg["text"]:
                    user = msg.get("user_profile", {}).get("real_name", msg.get("user", "unknown"))
                    text = msg["text"].replace("\n", " ")
                    result["messages"].append(f"{user}: {text}")

    if not result["messages"]:
        return {"status": "not_found", "invoice": invoice}
    return result


@app.get("/")
async def root():
    return {"message": "Tousuien Hub API on Render is running"}
