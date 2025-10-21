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
                decoded_name = None
                try:
                    decoded_name = name.encode("cp437").decode("utf-8", errors="ignore")
                except Exception as e:
                    print(f"⚠️ ファイル名変換エラー: {name} - {e}")
                    decoded_name = name  # fallback

                if not decoded_name or not decoded_name.endswith(".json"):
                    continue

                # ファイルを開いてJSON読み込み
                try:
                    with z.open(name) as f:
                        data = json.load(f)
                except Exception as e:
                    print(f"⚠️ JSON読み込み失敗: {decoded_name} - {e}")
                    continue

                # メッセージ内テキスト検索
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
                        # 新形式のthreadsフォルダ内スレッドファイルパス
                        thread_path_new = f"{entry['channel']}/threads/{ts}.json"
                        # 旧形式のルート直下にスレッドファイル存在の可能性
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
                                except Exception as e:
                                    print(f"⚠️ スレッドJSON読み込み失敗: {tpath} - {e}")

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
