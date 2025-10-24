# analysis/chat_command_handler.py

import os
import json
import openai
import aioredis
import asyncio
from datetime import datetime
from functools import lru_cache

# --- OpenAI設定 ---
openai.api_key = os.getenv("OPENAI_API_KEY", "sk-xxxx")

# --- Redisキャッシュ接続（API側と共通） ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis = None

async def get_redis():
    global redis
    if redis is None:
        redis = await aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    return redis


# --- LRUキャッシュ（短時間メモリキャッシュ） ---
@lru_cache(maxsize=200)
def local_cache_key(text: str):
    """単純なローカルキャッシュキー生成"""
    return text.strip().lower()


# --- OpenAI補助関数 ---
async def query_openai(prompt: str) -> str:
    """OpenAIに非同期で問い合わせ"""
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "あなたは顧客管理データの分析AIです。返答はJSON形式のみで返してください。"
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        ),
    )
    return response.choices[0].message.content.strip()


# --- メイン関数 ---
async def handle_chat_command(text: str):
    """
    GPTやデータベースを介して自然文クエリを解析・実行し、結果を返す。
    キャッシュ優先で高速化。
    """

    redis_client = await get_redis()
    cache_key = f"chatcmd:{text.strip().lower()}"

    # --- Redisキャッシュチェック ---
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    # --- ローカルキャッシュ確認 ---
    if local_cache_key(text):
        # 簡易ローカルキャッシュ例（DBやGPTが不要な場合）
        pass

    # --- プロンプトテンプレート ---
    prompt = f"""
次の自然文を解析し、顧客管理データ（company_code, year, invoice, status, priceなど）に対応するSQLまたは要約JSONを生成してください。
入力: 「{text}」
出力フォーマット:
{{
  "company_code": "IST",
  "year": 2025,
  "total_records": 5,
  "records": [
    {{
      "invoice": "TSE-IST-001-25",
      "注文日": "2025-03-08",
      "通貨": "USD",
      "商品代＋送料": 2515.20,
      "ステータス": "REPEAT",
      "宛名": "Ian Steger",
      "担当者名": "Ian Steger"
    }}
  ]
}}
    """

    try:
        raw = await query_openai(prompt)

        # GPT応答をJSONパース
        data = json.loads(raw)

        # --- キャッシュ保存（10分間） ---
        await redis_client.setex(cache_key, 600, json.dumps(data))

        # --- 結果返却 ---
        return data

    except Exception as e:
        return {
            "error": str(e),
            "message": "handle_chat_command failed",
            "timestamp": datetime.now().isoformat(),
        }
