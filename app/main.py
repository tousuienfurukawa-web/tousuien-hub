# -*- coding: utf-8 -*-
import os
import json
import zipfile
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()
ZIP_FILE_PATH = Path("slack_export_latest.zip")

# ==================================================
# 💬 Slackスレッド取得（threadsフォルダ・旧新対応）
# ==================================================
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
                    # チャンネルディレクトリ名を取得 (例: "general")
                    channel_dir = name.split("/")[0] if "/" in name else "(root)"
                    if channel_dir == "(root)":
                        continue  # ルートのjsonファイルは通常チャンネルデータではない

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
                    if not text:
                        continue

                    # ▼ ゆらぎ対応
                    normalized_invoice = (
                        invoice_id.strip()
                        .lower()
                        .replace("tse-", "")
                        .replace("ts-", "")
                        .replace("t-", "")
                        .replace(" ", "")
                    )
                    text_norm = text.lower().replace(" ", "")
                    if (
                        normalized_invoice not in text_norm
                        and invoice_id.lower() not in text_norm
                        and f"tse-{normalized_invoice}" not in text_norm
                    ):
                        continue

                    entry = {
                        "file": name,
                        "channel": channel_dir,
                        "user": msg.get("user", ""),
                        "text": text,
                        "ts": msg.get("ts", ""),
                        "replies": []
                    }

                    ts = msg.get("ts")
                    if not ts:
                        matches.append(entry)
                        continue

                    # --- スレッド検索ロジック ---
                    expected_thread_path = f"{channel_dir}/threads/{ts}.json"

                    # ファイル名の文字化けにも対応（cp437→utf-8）
                    thread_candidates = []
                    for f in all_files:
                        try:
                            decoded = f.encode("cp437").decode("utf-8", errors="ignore")
                        except Exception:
                            decoded = f
                        if (
                            "thread" in decoded.lower()
                            and decoded.split("/")[-1].startswith(ts)
                        ):
                            thread_candidates.append(f)

                    for tpath in thread_candidates:
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


# ==================================================
# 🧾 SlackスレッドHTML出力（Slack風＋replies表示）
# ==================================================
@app.get("/slack/thread_html/{invoice_id}", response_class=HTMLResponse)
async def get_slack_thread_html(invoice_id: str):
    if not ZIP_FILE_PATH.exists():
        return "<h3>⚠️ ZIP file not found</h3>"

    with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
        all_files = z.namelist()
        matches = []

        for name in all_files:
            if not name.endswith(".json"):
                continue
            try:
                channel_dir = name.split("/")[0] if "/" in name else "(root)"
                if channel_dir == "(root)":
                    continue
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
                if not text:
                    continue

                normalized_invoice = (
                    invoice_id.strip()
                    .lower()
                    .replace("tse-", "")
                    .replace("ts-", "")
                    .replace("t-", "")
                    .replace(" ", "")
                )
                text_norm = text.lower().replace(" ", "")
                if (
                    normalized_invoice not in text_norm
                    and invoice_id.lower() not in text_norm
                    and f"tse-{normalized_invoice}" not in text_norm
                ):
                    continue

                entry = {
                    "file": name,
                    "channel": channel_dir,
                    "user": msg.get("user", ""),
                    "text": text.replace("\n", "<br>"),
                    "ts": msg.get("ts", ""),
                    "replies": []
                }

                ts = msg.get("ts")
                if not ts:
                    matches.append(entry)
                    continue

                thread_candidates = []
                for f in all_files:
                    try:
                        decoded = f.encode("cp437").decode("utf-8", errors="ignore")
                    except Exception:
                        decoded = f
                    if "thread" in decoded.lower() and decoded.split("/")[-1].startswith(ts):
                        thread_candidates.append(f)

                for tpath in thread_candidates:
                    try:
                        with z.open(tpath) as tf:
                            replies = json.load(tf)
                            if isinstance(replies, list):
                                for r in replies:
                                    if not isinstance(r, dict):
                                        continue
                                    entry["replies"].append({
                                        "user": r.get("user", ""),
                                        "text": r.get("text", "").replace("\n", "<br>")
                                    })
                    except Exception:
                        continue

                matches.append(entry)

        if not matches:
            return f"<h3>❌ 該当スレッドが見つかりません（{invoice_id}）</h3>"

        html = f"<h2>🧾 受注番号：{invoice_id}</h2>"
        html += """
        <style>
        body{font-family:Segoe UI, sans-serif;background:#f8f8fc;padding:30px;}
        .msg{background:#fff;border-radius:8px;margin:12px 0;padding:14px 18px;box-shadow:0 1px 4px rgba(0,0,0,0.08);}
        .user{color:#0073e6;font-weight:bold;}
        .reply{margin-left:25px;background:#f9f9ff;}
        .file{font-size:0.8em;color:#888;}
        </style>
        """

        for m in matches:
            html += f"<div class='msg'><div class='user'>👤 {m['user']}</div><div>{m['text']}</div><div class='file'>{m['file']}</div>"
            if m['replies']:
                html += "<div style='margin-top:8px;'><b>💬 スレッド返信:</b>"
                for r in m['replies']:
                    html += f"<div class='msg reply'><div class='user'>↪ {r['user']}</div><div>{r['text']}</div></div>"
                html += "</div>"
            html += "</div>"

        return html


# ==================================================
# 🚀 ローカル or Render起動時のメイン
# ==================================================
if __name__ == "__main__":
    import uvicorn
    if not ZIP_FILE_PATH.exists():
        print(f"--- ⚠️ エラー ⚠️ ---")
        print(f"Slackエクスポートファイル ({ZIP_FILE_PATH}) が見つかりません。")
        print(f"このスクリプトと同じディレクトリに配置してください。")
    else:
        print(f"✅ {ZIP_FILE_PATH} を読み込みます。")
        print("🚀 サーバーを起動します...")
        uvicorn.run(app, host="0.0.0.0", port=10000)
