from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse, JSONResponse
import zipfile, json, os

app = FastAPI(title="Tousuien Hub API on Render")

ZIP_PATH = "海外 Slack export 最新.zip"

@app.get("/")
async def root():
    return {"message": "Tousuien Hub API on Render is running"}


@app.get("/slack/thread/{invoice}")
async def get_slack_thread(invoice: str, format: str = Query("json")):
    if not os.path.exists(ZIP_PATH):
        raise HTTPException(status_code=404, detail="ZIP file not found")

    threads = []
    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        for name in zf.namelist():
            if not name.endswith(".json"):
                continue
            try:
                with zf.open(name) as f:
                    data = json.load(f)
                    for msg in data:
                        if invoice in msg.get("text", ""):
                            thread_ts = msg.get("ts")
                            msgs = [m for m in data if m.get("thread_ts") == thread_ts or m.get("ts") == thread_ts]
                            threads.append({"file": name, "thread_ts": thread_ts, "messages": msgs})
            except Exception:
                continue

    if not threads:
        return {"error": f"No messages found for invoice {invoice}"}

    # JSON出力モード
    if format == "json":
        return {"invoice": invoice, "threads": threads}

    # 日本語整形モード
    text_output = f"📄 スレッド：{invoice}\n\n"
    for thread in threads:
        for m in sorted(thread["messages"], key=lambda x: x["ts"]):
            user = m.get("user", "")
            text = m.get("text", "")
            text = text.replace("<!subteam", "").replace(">", "")
            text = text.replace("\t", "").replace("\n", "\n")
            # TOUSUIEN側（社内）の発言を🟢で色付け
            if user in ["U0606SPN4BW", "U08U8MMTH43", "U0331FZTHEK"]:
                prefix = "🟢TOUSUIEN："
            else:
                prefix = "👤"
            text_output += f"{prefix}{text}\n\n"
    return PlainTextResponse(text_output)
