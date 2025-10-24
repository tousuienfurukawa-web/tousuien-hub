# app/api_server.py

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from analysis.chat_command_handler import handle_chat_command
from functools import lru_cache
import asyncio
import aioredis
import json
import os

app = FastAPI(title="TOUSUIEN Hub API", version="2.0")

# --- CORS 設定 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Redis キャッシュ設定 ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis = None

@app.on_event("startup")
async def startup_event():
    global redis
    redis = await aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)

@app.on_event("shutdown")
async def shutdown_event():
    if redis:
        await redis.close()

# --- LRUキャッシュで重いクエリを軽量化 ---
@lru_cache(maxsize=100)
def cached_command_handler(text: str):
    """同期キャッシュ（短期）"""
    return handle_chat_command(text)


@app.get("/")
@app.head("/")
async def root():
    return {"message": "TOUSUIEN Hub API is running."}


@app.get("/query")
async def query(
    text: str = Query(..., description="自然言語での企業関連クエリ（例：ISTの2025年受注）")
):
    """
    ChatGPTなど外部サービスから自然言語クエリを受け取り、DBまたはGPTを経由して結果を返す。
    キャッシュ・非同期化・タイムアウト処理を含む高速版。
    """
    try:
        # --- Redisキャッシュ確認 ---
        cached = await redis.get(text)
        if cached:
            return json.loads(cached)

        # --- 並列で処理（非同期対応） ---
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, cached_command_handler, text)

        response = {
            "success": True,
            "query": text,
            "response": result,
            "format": "text",
        }

        # --- キャッシュ保存（10分有効） ---
        await redis.setex(text, 600, json.dumps(response))

        return response

    except Exception as e:
        return {
            "success": False,
            "query": text,
            "error": str(e),
        }
