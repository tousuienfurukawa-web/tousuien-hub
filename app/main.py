@app.get("/slack/thread/{invoice_id}")
async def get_slack_thread(invoice_id: str):
    """SlackエクスポートZIP内から受注番号スレッドを検索してJSONで返す（全フォルダ対応＋スレッド返信付き）"""
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}

    try:
        with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
            matches = []
            for name in z.namelist():
                # --- 日本語フォルダ名の文字化け対策 ---
                decoded_name = name.encode("cp437").decode("utf-8", errors="ignore")

                # JSONファイルのみ対象
                if not decoded_name.endswith(".json"):
                    continue

                with z.open(name) as f:
                    try:
                        data = json.load(f)
                        for msg in data:
                            if invoice_id in msg.get("text", ""):
                                # 親メッセージを追加
                                entry = {
                                    "channel": decoded_name.split("/")[0],
                                    "user": msg.get("user", ""),
                                    "text": msg.get("text", ""),
                                    "ts": msg.get("ts", ""),
                                    "replies": []
                                }

                                # --- threads フォルダもチェックして返信を追加 ---
                                ts = msg.get("ts")
                                if ts:
                                    thread_path = f"{entry['channel']}/threads/{ts}.json"
                                    if thread_path in z.namelist():
                                        with z.open(thread_path) as tf:
                                            try:
                                                replies = json.load(tf)
                                                for r in replies:
                                                    entry["replies"].append({
                                                        "user": r.get("user", ""),
                                                        "text": r.get("text", "")
                                                    })
                                            except Exception:
                                                pass

                                matches.append(entry)
                    except Exception:
                        continue

            if not matches:
                return {"status": "not found", "invoice": invoice_id}

            return {
                "invoice": invoice_id,
                "count": len(matches),
                "messages": matches
            }

    except Exception as e:
        return {"error": str(e)}
