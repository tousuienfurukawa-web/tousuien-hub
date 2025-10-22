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

# ==================================================
# 🔍 thread候補検索（threads / thread 両対応）
# ==================================================
def find_thread_candidates(all_files, ts):
    candidates = []
    for f in all_files:
        try:
            decoded = f.encode("cp437").decode("utf-8", errors="ignore")
        except Exception:
            decoded = f
        if ("/threads/" in decoded.lower() or "/thread/" in decoded.lower()) and decoded.endswith(f"{ts}.json"):
            candidates.append(f)
    return candidates

# ==================================================
# 🧩 invoice表記ゆれ対応 正規化関数
# ==================================================
def normalize_invoice_text(text: str) -> str:
    """ハイフン・大文字小文字・スペースを無視して正規化"""
    return text.lower().replace("-", "").replace(" ", "").replace("_", "")

# ==================================================
# 🕐 タイムスタンプをJST日時に変換
# ==================================================
def format_timestamp(ts):
    try:
        dt = datetime.fromtimestamp(float(ts))
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return ts

# ==================================================
# 💬 Slackスレッド抽出（完全展開版）
# ==================================================
def extract_thread_from_zip(invoice_id):
    if not ZIP_FILE_PATH.exists():
        return {"error": "ZIP file not found"}

    normalized_invoice = normalize_invoice_text(invoice_id)
    with zipfile.ZipFile(ZIP_FILE_PATH, "r") as z:
        all_files = z.namelist()
        ts_map = {}
        matches = []

        # 全メッセージをtsでマップ化
        for name in all_files:
            if not name.endswith(".json"):
                continue
            try:
                with z.open(name) as f:
                    data = json.load(f)
            except Exception:
                continue
            if isinstance(data, list):
                for msg in data:
                    if isinstance(msg, dict) and "ts" in msg:
                        ts_map[msg["ts"]] = msg

        # invoice_idを含むメッセージを検索
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

                text_norm = normalize_invoice_text(text)

                # 柔軟マッチ条件
                if (
                    normalized_invoice not in text_norm
                    and f"tse{normalized_invoice}" not in text_norm
                    and f"ts{normalized_invoice}" not in text_norm
                ):
                    continue

                ts = msg.get("ts", "")
                all_replies = []

                # repliesフィールドから返信を取得
                for ref in msg.get("replies", []):
                    rts = ref.get("ts")
                    if rts and rts in ts_map:
                        reply = ts_map[rts]
                        if reply.get("ts") != ts:  # 親メッセージを除外
                            all_replies.append(reply)

                # threadフォルダから直接取得
                if ts:
                    for tpath in find_thread_candidates(all_files, ts):
                        try:
                            with z.open(tpath) as tf:
                                thread_msgs = json.load(tf)
                                if isinstance(thread_msgs, list):
                                    for r in thread_msgs:
                                        if isinstance(r, dict) and r.get("ts") != ts:
                                            if not any(r.get("ts") == rep.get("ts") for rep in all_replies):
                                                all_replies.append(r)
                        except Exception:
                            continue

                # タイムスタンプでソート
                all_replies.sort(key=lambda x: float(x.get("ts", 0)))

                entry = {
                    "file": name,
                    "user": msg.get("user", "不明"),
                    "text": text,
                    "ts": ts,
                    "replies": all_replies
                }
                matches.append(entry)

        return {"invoice": invoice_id, "messages": matches, "count": len(matches)}

# ==================================================
# 🧠 GPT風要約（実データベース）
# ==================================================
def generate_gpt_summary(messages):
    all_texts = []
    for m in messages:
        all_texts.append(m.get("text", ""))
        for r in m.get("replies", []):
            all_texts.append(r.get("text", ""))
    
    joined_text = "\n".join(all_texts)

    # 現状分析
    status_parts = []
    if "出荷" in joined_text or "発送" in joined_text:
        status_parts.append("出荷対応が進行中")
    if "DHL" in joined_text or "UPS" in joined_text:
        status_parts.append("配送業者との調整済み")
    if "入金" in joined_text or "支払い" in joined_text or "USD" in joined_text:
        status_parts.append("入金確認の記録あり")
    if "PL" in joined_text or "PackingList" in joined_text:
        status_parts.append("パッキングリスト作成済み")
    if "Invoice" in joined_text:
        status_parts.append("インボイス発行済み")
    
    current_status = "、".join(status_parts) if status_parts else "受注関連のやり取りが確認されました"

    # 次のアクション
    actions = []
    if "DHL" in joined_text or "UPS" in joined_text:
        actions.append("📦 発送書類の最終確認")
    if "入金" in joined_text or "USD" in joined_text:
        actions.append("💰 入金額とインボイスの照合")
    if "出荷" in joined_text:
        actions.append("🚚 出荷スケジュールの確認")
    if not actions:
        actions = ["📋 案件の進捗状況を確認", "📞 顧客への連絡確認"]

    # 注意点
    notes = []
    if "修正" in joined_text or "訂正" in joined_text:
        notes.append("書類の修正履歴があります")
    if "急" in joined_text or "至急" in joined_text:
        notes.append("急ぎの対応が必要な可能性があります")
    
    return {
        "status": current_status,
        "actions": actions,
        "notes": notes
    }

# ==================================================
# 🧾 HTML出力（改善版レイアウト）
# ==================================================
@app.get("/slack/thread_html/{invoice_id}", response_class=HTMLResponse)
async def get_slack_thread_html(invoice_id: str, mode: str = Query(default="report")):
    data = extract_thread_from_zip(invoice_id)
    if "error" in data:
        return f"<h3>❌ {data['error']}</h3>"
    if not data.get("messages"):
        return f"<h3>❌ スレッドが見つかりません（{invoice_id}）</h3>"

    msgs = data["messages"]

    html = """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans JP", sans-serif;
            background: #f5f5f5;
            color: #1a1a1a;
            padding: 20px;
            line-height: 1.6;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 24px;
        }
        .header h1 {
            font-size: 24px;
            margin-bottom: 8px;
        }
        .header .meta {
            opacity: 0.9;
            font-size: 14px;
        }
        .section {
            padding: 24px;
            border-bottom: 1px solid #e5e5e5;
        }
        .section:last-child {
            border-bottom: none;
        }
        .section h2 {
            font-size: 18px;
            margin-bottom: 16px;
            color: #667eea;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .message {
            background: #f9fafb;
            border-left: 3px solid #667eea;
            padding: 12px 16px;
            margin-bottom: 12px;
            border-radius: 4px;
        }
        .message-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            font-size: 13px;
        }
        .message-user {
            font-weight: 600;
            color: #667eea;
        }
        .message-time {
            color: #666;
        }
        .message-text {
            color: #333;
            white-space: pre-wrap;
        }
        .reply {
            background: white;
            border-left: 3px solid #94a3b8;
            padding: 10px 14px;
            margin: 8px 0 8px 24px;
            border-radius: 4px;
        }
        .status-box {
            background: #f0f9ff;
            border-left: 4px solid #0ea5e9;
            padding: 16px;
            border-radius: 4px;
            margin-bottom: 16px;
        }
        .action-list {
            list-style: none;
        }
        .action-list li {
            padding: 8px 0;
            padding-left: 24px;
            position: relative;
        }
        .action-list li:before {
            content: "▸";
            position: absolute;
            left: 8px;
            color: #667eea;
        }
        .note {
            background: #fff7ed;
            border-left: 4px solid #fb923c;
            padding: 12px;
            border-radius: 4px;
            margin-top: 12px;
            font-size: 14px;
        }
        </style>
    </head>
    <body>
    <div class="container">
    """

    # ヘッダー
    first_msg = msgs[0] if msgs else {}
    html += f"""
    <div class="header">
        <h1>📋 {invoice_id}</h1>
        <div class="meta">
            投稿者: {first_msg.get('user', '不明')} | 
            最終更新: {format_timestamp(msgs[-1].get('ts', '')) if msgs else '不明'}
        </div>
    </div>
    """

    # GPT要約
    gpt_info = generate_gpt_summary(msgs)
    html += f"""
    <div class="section">
        <h2>🧠 GPT要約</h2>
        <div class="status-box">
            <strong>現状:</strong> {gpt_info['status']}
        </div>
        <h3 style="font-size: 16px; margin-bottom: 12px;">次のアクション</h3>
        <ul class="action-list">
            {''.join(f'<li>{action}</li>' for action in gpt_info['actions'])}
        </ul>
    """
    if gpt_info['notes']:
        html += f"""
        <div class="note">
            <strong>⚠️ 注意点:</strong><br>
            {'<br>'.join(gpt_info['notes'])}
        </div>
        """
    html += "</div>"

    # スレッド内コメント一覧
    html += """
    <div class="section">
        <h2>💬 スレッド内コメント一覧</h2>
    """

    for msg in msgs:
        html += f"""
        <div class="message">
            <div class="message-header">
                <span class="message-user">{msg.get('user', '不明')}</span>
                <span class="message-time">{format_timestamp(msg.get('ts', ''))}</span>
            </div>
            <div class="message-text">{msg.get('text', '').replace('<', '&lt;').replace('>', '&gt;')}</div>
        """
        
        # 返信を表示
        for reply in msg.get('replies', []):
            html += f"""
            <div class="reply">
                <div class="message-header">
                    <span class="message-user">{reply.get('user', '不明')}</span>
                    <span class="message-time">{format_timestamp(reply.get('ts', ''))}</span>
                </div>
                <div class="message-text">{reply.get('text', '').replace('<', '&lt;').replace('>', '&gt;')}</div>
            </div>
            """
        
        html += "</div>"

    html += """
    </div>
    """

    # フッター
    html += f"""
    <div class="section" style="text-align: right; color: #666; font-size: 13px;">
        出典: Slackスレッド整形データ（<code>{invoice_id}</code>）
    </div>
    </div>
    </body>
    </html>
    """

    return html

# ==================================================
# 🚀 起動
# ==================================================
if __name__ == "__main__":
    import uvicorn
    if not ZIP_FILE_PATH.exists():
        print("⚠️ slack_export_latest.zip が見つかりません。")
    else:
        print("✅ ZIPファイル読み込み成功。")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
