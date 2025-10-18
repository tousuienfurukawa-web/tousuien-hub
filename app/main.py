from fastapi import FastAPI
import zipfile, json, re, os

app = FastAPI(title="Tousuien Hub API")

@app.get("/")
async def root():
    return {"message": "Tousuien Hub API on Render is running"}

# SlackエクスポートZIPをリポジトリ直下に置く（例： "海外 Slack export Feb 17 2022 - Oct 16 2025.zip"）
ZIP_PATH = "海外 Slack export Feb 17 2022 - Oct 16 2025.zip"

@app.get("/slack/thread/{invoice}")
async def get_slack_thread(invoice: str):
    """SlackエクスポートZIP内から、指定インボイス番号のスレッド全体を抽出"""
    if not os.path.exists(ZIP_PATH):
        return {"error": f"ZIP file not found: {ZIP_PATH}"}

    results = []
    pattern = re.compile(re.escape(invoice))

    try:
        with zipfile.ZipFile(ZIP_PATH, "r") as zf:
            json_files = [f for f in zf.namelist() if f.endswith(".json") and "/" in f]
            for name in json_files:
                data = json.loads(zf.read(name))
                for msg in data:
                    text = msg.get("text", "")
                    if pattern.search(text):
                        thread_ts = msg.get("thread_ts", msg.get("ts"))
                        # 同一スレッドの全メッセージをまとめる
                        thread_msgs = [
                            m for m in data if m.get("thread_ts") == thread_ts or m.get("ts") == thread_ts
                        ]
                        results.append({
                            "file": name,
                            "thread_ts": thread_ts,
                            "messages": [
                                {
                                    "user": m.get("user"),
                                    "text": m.get("text"),
                                    "ts": m.get("ts")
                                }
                                for m in sorted(thread_msgs, key=lambda x: x.get("ts", ""))
                            ],
                        })
        if not results:
            return {"status": "not_found", "invoice": invoice}
        return {"invoice": invoice, "threads": results}

    except zipfile.BadZipFile:
        return {"error": "File is not a valid ZIP"}
    except Exception as e:
        return {"error": str(e)}
