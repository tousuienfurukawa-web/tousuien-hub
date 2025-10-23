# -*- coding: utf-8 -*-
import os
from openai import OpenAI

# ------------------------------------------------------------
# 🔹 GPT-5（またはGPT-4）を使ってSlackスレッドを要約するモジュール
# ------------------------------------------------------------
def generate_slack_summary(invoice_id: str, messages: list) -> dict:
    """
    Slackスレッド（全メッセージ）をGPTで要約する。
    :param invoice_id: 受注番号（例: TSE-ABC-001-25）
    :param messages: スレッド内のメッセージリスト [{user:..., text:...}, ...]
    :return: dict { "summary": "...要約テキスト..." }
    """
    try:
        # ✅ OpenAIクライアント初期化（新形式）
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # ✅ メッセージ本文をまとめる
        joined_text = "\n".join(
            [f"{m.get('user', 'unknown')}: {m.get('text', '')}" for m in messages if m.get("text")]
        )

        if not joined_text.strip():
            return {"summary": "⚠️ 要約対象メッセージが見つかりません。"}

        # ✅ GPTへのプロンプト
        response = client.chat.completions.create(
            model="gpt-4-turbo",  # or "gpt-5" に変更可能
            messages=[
                {
                    "role": "system",
                    "content": (
                        "あなたはSlack業務スレッドを要約するアシスタントです。"
                        "担当者や日付、作業内容、依頼事項、進捗、入金・発送情報などを"
                        "ビジネス報告書風に整理してください。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"以下は受注番号 {invoice_id} に関するSlackスレッド全文です。\n"
                        "内容を簡潔に箇条書き＋状況説明付きで要約してください。\n\n"
                        f"{joined_text}"
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=900,
        )

        summary_text = response.choices[0].message.content.strip()
        return {"summary": summary_text}

    except Exception as e:
        return {"summary": f"⚠️ GPT summary generation failed: {str(e)}"}
