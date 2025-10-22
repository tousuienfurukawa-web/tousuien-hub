# -*- coding: utf-8 -*-
import os
import json
import zipfile
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

app = FastAPI()
ZIP_FILE_PATH = Path("slack_export_latest.zip")

# ------------------------------------------------------------
# 🔹 SlackユーザーID → 表示名マッピング（実データ反映）
# ------------------------------------------------------------
USER_MAP = {
    "U08N3SKSL75": "木村",
    "U08RVRNBY00": "長谷川",
    "U0331FZS7JT": "岡 祐太",
    "U0331FWGQRM": "松井",
    "U033G4KN4TD": "福井",
    "U03BLQ65GK0": "会長",
    "U08FZUNPSQ3": "神谷",
    "U0331FZTHEK": "片寄",
    "U066P20UQH1": "林 遥香",
}

def resolve_user_name(user_id: str) -> str:
    """Slack IDを人間の名前に変換（未登録ならそのまま）"""
    if not user_id:
        return "不明"
    return USER_MAP.get(user_id, user_id)

# ------------------------------------------------------------
# 🔹 基本ユーティリティ
# ------------------------------------------------------------
def normalize_invoice_text(text: str) -> str:
    return text.lower().replace("-", "").replace(" ", "").replace("_", "")

def format_timestamp(ts):
    try:
        dt = datetime.fromtimestamp(float(ts))
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return ts

def escape_html(text: str) -> str:
    return (text or "").replace("<", "&lt;").replace(">", "&gt;")

def find_thread_files(all_files, ts):
    candidates = []
    for f in all_files:
        try:
            decoded = f.encode("cp437").decode("utf-8", errors="ignore")
        except:
            decoded = f
        if ("/threads/" in decoded.lower() or "/thread/" in decoded.lower()):
            if ts in decoded:
                candidates.append(f)
    return candidates

# ------------------------------------------------------------
# 🔹 Slack ZIP抽出ロジック
# ------------------------------------------------------------
def extract_thread_from_zip(invoice_id):
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}

    normalized_invoice = normalize_invoice_text(invoice_id)
    with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
        all_files = z.namelist()

        debug_info = {
            "total_files": len(all_files),
            "json_files": len([f for f in all_files if f.endswith(".json")]),
            "thread_folders": len([f for f in all_files if "/thread" in f.lower()])
        }

        matches = []
        for name in all_files:
            if not name.endswith(".json"):
                continue
            try:
                with z.open(name) as f:
                    data = json.load(f)
            except:
                continue

            if not isinstance(data, list):
                continue

            for msg in data:
                if not isinstance(msg, dict):
                    continue
                text = msg.get("text", "")
                if not text:
                    continue
                text_norm = normalize_invoice_text(text)
                if normalized_invoice not in text_norm:
                    continue

                ts = msg.get("ts", "")
                thread_ts = msg.get("thread_ts", ts)
                thread_messages = [msg]

                for other_msg in data:
                    if not isinstance(other_msg, dict):
                        continue
                    other_thread_ts = other_msg.get("thread_ts", other_msg.get("ts", ""))
                    if other_thread_ts == thread_ts and other_msg.get("ts") != ts:
                        thread_messages.append(other_msg)

                thread_files = find_thread_files(all_files, ts)
                for tf in thread_files:
                    try:
                        with z.open(tf) as thread_file:
                            thread_data = json.load(thread_file)
                            if isinstance(thread_data, list):
                                for tmsg in thread_data:
                                    if isinstance(tmsg, dict) and not any(m.get("ts") == tmsg.get("ts") for m in thread_messages):
                                        thread_messages.append(tmsg)
                    except:
                        continue

                thread_messages.sort(key=lambda x: float(x.get("ts", 0)))
                matches.append({
                    "file": name,
                    "user": resolve_user_name(msg.get("user")),
                    "text": text,
                    "ts": ts,
                    "thread_ts": thread_ts,
                    "reply_count": msg.get("reply_count", 0),
                    "all_messages": thread_messages,
                    "thread_files_found": len(thread_files)
                })

        return {
            "invoice": invoice_id,
            "messages": matches,
            "count": len(matches),
            "debug": debug_info
        }

# ------------------------------------------------------------
# 🔹 ハルシネーション防止版 GPT要約
# ------------------------------------------------------------
def generate_gpt_summary(messages):
    """
    Slackスレッド内容から、明確な完了・確認表現のみを抽出。
    曖昧なAI推測は行わず、事実ベースで要約。
    """
    all_texts = []
    for m in messages:
        all_texts.append(m.get("text", ""))
        for msg in m.get("all_messages", []):
            all_texts.append(msg.get("text", ""))

    joined_text = "\n".join(all_texts)

    status_parts = []
    if any(x in joined_text for x in ["出荷完了", "発送完了", "出荷しました", "発送しました"]):
        status_parts.append("✅ 出荷完了済み")
    elif any(x in joined_text for x in ["出荷予定", "発送予定"]):
        status_parts.append("📦 出荷予定あり")

    if any(x in joined_text for x in ["入金確認", "支払い完了", "Payment received"]):
        status_parts.append("💰 入金確認済み")

    if any(x in joined_text for x in ["パッキングリスト修正完了", "Packing List updated"]):
        status_parts.append("📄 パッキングリスト修正完了")

    if any(x in joined_text for x in ["Invoice修正完了", "インボイス修正完了", "Invoice updated"]):
        status_parts.append("🧾 インボイス修正完了")

    if not status_parts:
        status_parts = ["⚠️ 明確な進捗報告がSlack上に見つかりません"]

    actions = []
    if "出荷予定" in joined_text or "発送予定" in joined_text:
        actions.append("🚚 出荷予定日の確定・共有")
    if "請求" in joined_text or "支払い" in joined_text:
        actions.append("💰 請求・入金処理の確認")
    if "修正" in joined_text or "確認お願いします" in joined_text:
        actions.append("📝 修正・承認依頼内容の確認")
    if not actions:
        actions = ["📋 スレッド内容を確認してください（AIによる推測なし）"]

    notes = []
    if len(all_texts) < 5:
        notes.append("⚠️ メッセージ数が少なく、要約の信頼性が低い可能性があります。")

    return {
        "status": " / ".join(status_parts),
        "actions": actions,
        "notes": notes
    }

# ------------------------------------------------------------
# 🔹 HTML出力（レポートモード）
# ------------------------------------------------------------
def build_report_html(invoice_id, msgs, gpt_info):
    total_threads = len(msgs)
    total_messages = sum(len(m.get("all_messages", [])) for m in msgs)
    participants = sorted({resolve_user_name(m.get("user")) for t in msgs for m in t.get("all_messages", [])})
    latest_ts = max((float(m.get("ts", 0)) for t in msgs for m in t.get("all_messages", []) if m.get("ts")), default=0)
    last_updated = format_timestamp(latest_ts)

    html = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
      <meta charset="UTF-8">
      <style>
        body {{font-family:"Noto Sans JP",sans-serif;background:#f8fafc;color:#0f172a;padding:24px;line-height:1.6;}}
        .card {{max-width:760px;margin:0 auto;background:white;border-radius:12px;padding:28px;box-shadow:0 10px 30px rgba(0,0,0,0.05);}}
        h1 {{font-size:24px;margin-bottom:8px;}}
        .summary {{background:#eff6ff;border-left:5px solid #3b82f6;padding:16px;border-radius:8px;margin-bottom:24px;}}
        .stat {{background:#f1f5f9;border-radius:8px;padding:12px;margin:8px 0;}}
        .footer {{text-align:right;color:#64748b;font-size:12px;margin-top:
