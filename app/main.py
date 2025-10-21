# 💬 スレッド取得（旧・新Slack構造対応）
@app.get("/slack/thread/{invoice_id}")
async def get_slack_thread(invoice_id: str):
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}

    try:
        with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
            all_files = z.namelist()
            matches = []

            for name in all_files:
                if not name.endswith(".json"):
                    continue
                try:
                    with z.open(name) as f:
                        data = json.load(f)
                except Exception:
                    continue

                if not isinstance(data, list):
                    continue

                for msg in data:
                    if not isinstance(msg, dict):
                        continue
                    text = msg.get("text", "")
                    if invoice_id not in text:
                        continue

                    entry = {
                        "file": name,
                        "channel": name.split("/")[0] if "/" in name else "(root)",
                        "user": msg.get("user", ""),
                        "text": text,
                        "ts": msg.get("ts", ""),
                        "replies": []
                    }

                    ts = msg.get("ts")
                    if not ts:
                        continue

                    # threads ディレクトリ内スレッドを探索（旧・新両対応）
                    possible_paths = [
                        f"{entry['channel']}/threads/{ts}.json",  # 新Slack構造
                        f"threads/{ts}.json",                     # 旧Slack構造
                        f"{ts}.json"                              # 最古構造
                    ]

                    for tpath in possible_paths:
                        if tpath in all_files:
                            try:
                                with z.open(tpath) as tf:
                                    replies = json.load(tf)
                                    if isinstance(replies, list):
                                        for r in replies:
                                            if not isinstance(r, dict):
                                                continue
                                            entry["replies"].append({
                                                "user": r.get("user", ""),
                                                "text": r.get("text", ""),
                                                "ts": r.get("ts", "")
                                            })
                            except Exception as e:
                                print(f"⚠️ スレッド読込失敗: {tpath} ({e})")
                    matches.append(entry)

            if not matches:
                return {"status": "not found", "invoice": invoice_id}
            return {"invoice": invoice_id, "count": len(matches), "messages": matches}
    except Exception as e:
        return {"error": str(e)}
