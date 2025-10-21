# -*- coding: utf-8 -*-
import os
import json
import zipfile
import time
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ==================================================
# 🚀 FastAPI アプリ定義（最初に置く！）
# ==================================================
app = FastAPI()

# ==================================================
# 💾 グローバル設定
# ==================================================
ZIP_FILE_PATH = Path("slack_export_latest.zip")
slack_token = os.getenv("SLACK_BOT_TOKEN")
client = WebClient(token=slack_token) if slack_token else None

# ==================================================
# ✅ ヘルスチェック（トップページ）
# ==================================================
@app.get("/")
async def root():
    return {
        "status": "ok",
        "zip_found": ZIP_FILE_PATH.exists(),
        "slack_api_enabled": client is not None
    }

# ==================================================
# 💬 スレッド取得（旧・新Slack構造対応＋ゆらぎ検索対応）
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

                    # ▼▼▼ Codex式 ゆらぎ対応検索 ▼▼▼
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
                    # ▲▲▲

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

                    # threadsディレクトリを旧・新両対応で探索
                    possible_paths = [
                        f"{entry['channel']}/threads/{ts}.json",  # 新形式
                        f"threads/{ts}.json",                     # 旧形式
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

# ==================================================
# 🧾 SlackスレッドHTML表示（Slack風カードレイアウト）
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

                # ゆらぎ対応
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
                    "channel": name.split("/")[0] if "/" in name else "(root)",
                    "user": msg.get("user", ""),
                    "text": text.replace("\n", "<br>"),
                    "ts": msg.get("ts", ""),
                    "replies": []
                }

                ts = msg.get("ts")
                if not ts:
                    continue

                possible_paths = [
                    f"{entry['channel']}/threads/{ts}.json",
                    f"threads/{ts}.json",
                    f"{ts}.json"
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
        body{font-family:Segoe UI, sans-serif;line-height:1.6;background:#f7f7fa;padding:25px;}
        .msg{background:#fff;border-radius:8px;margin:15px 0;padding:12px 18px;box-shadow:0 1px 4px rgba(0,0,0,0.08);}
        .user{color:#0073e6;font-weight:bold;margin-bottom:4px;}
        .reply{margin-left:25px;background:#f9f9ff;}
        .file{font-size:0.8em;color:#999;}
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
