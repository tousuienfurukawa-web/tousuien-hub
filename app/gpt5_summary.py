# -*- coding: utf-8 -*-
"""
TOUSUIEN Data Sync – GPT-5対応Slack要約生成モジュール
"""
import os
import json
from datetime import datetime

try:
    import openai
    # OpenAI APIキー設定（Render環境変数に設定済み前提）
    openai.api_key = os.getenv("OPENAI_API_KEY")
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("[WARN] openai module not installed")

# ------------------------------------------------------------
# 🔹 モデル設定：GPT-5を明示的に指定
# ------------------------------------------------------------
MODEL = os.getenv("OPENAI_MODEL", "gpt-4")  # gpt-5が利用可能になるまではgpt-4を使用

# ------------------------------------------------------------
# 🔹 Slackスレッド要約生成
# ------------------------------------------------------------
def generate_slack_summary(invoice_id: str, thread_messages: list) -> dict:
    """
    Slackスレッド全体をGPTで要約。
    thread_messages: 各メッセージ辞書のリスト（user, text, tsなど）
    """
    if not OPENAI_AVAILABLE:
        return {
            "invoice_id": invoice_id,
            "summary": "⚠️ OpenAI APIが利用できません。環境変数とモジュールを確認してください。",
            "model": "none",
            "generated_at": datetime.utcnow().isoformat()
        }

    joined_text = "\n".join(
        f"{m.get('user','不明')} ({m.get('ts','')})：{m.get('text','')}"
        for m in thread_messages
        if m.get("text")
    )

    prompt = f"""
あなたはTOUSUIENの営業記録管理システムのアシスタントです。
以下はSlackスレッド「{invoice_id}」の全メッセージです。
発言内容を時系列に把握し、営業・受注・サンプル発送などの進捗を整理してください。

出力フォーマット：
---
【要約】
（300文字以内で全体の流れを自然な日本語でまとめる）

【現状ステータス】
（出荷完了／サンプル発送中／返信待ち など簡潔に）

【次のアクション】
（社内対応または顧客対応の具体的提案を2点まで）
---

スレッド内容：
{joined_text}
"""

    try:
        response = openai.ChatCompletion.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "あなたは日本語で正確かつ簡潔に報告する営業アシスタントです。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,            # 安定重視
            max_tokens=1000,
            presence_penalty=0,
            frequency_penalty=0
        )
        content = response["choices"][0]["message"]["content"]
        model_used = response["model"]
        print(f"[INFO] Slack summary generated via {model_used}")

        return {
            "invoice_id": invoice_id,
            "summary": content.strip(),
            "model": model_used,
            "generated_at": datetime.utcnow().isoformat()
        }

    except Exception as e:
        print(f"[ERROR] GPT summary generation failed: {e}")
        return {
            "invoice_id": invoice_id,
            "error": str(e),
            "model": MODEL,
            "summary": "⚠️ GPT要約生成中にエラーが発生しました。"
        }

# ------------------------------------------------------------
# 🔹 CLIテスト実行用
# ------------------------------------------------------------
if __name__ == "__main__":
    dummy_thread = [
        {"user": "古川", "text": "TSE-IST-003-25 の注文が入りました。", "ts": "2025-03-03"},
        {"user": "林", "text": "確認しました。請求書を送ります。", "ts": "2025-03-03"},
        {"user": "松井", "text": "発送準備を進めます。", "ts": "2025-03-04"}
    ]
    result = generate_slack_summary("TSE-IST-003-25", dummy_thread)
    print(json.dumps(result, ensure_ascii=False, indent=2))
