# app/api_server.py

from fastapi import FastAPI, Query
from analysis.chat_command_handler import handle_chat_command

app = FastAPI()

@app.get("/")
@app.head("/")  # ← これを追加
def root():
    return {"message": "TOUSUIEN Hub API is running."}

@app.get("/query")
def query(text: str = Query(..., description="自然言語での企業照会コマンド")):
    """
    ChatGPTや外部サービスからの自然言語クエリを受け取り、処理結果を返す。
    """
    try:
        result = handle_chat_command(text)
        return {"response": result}
    except Exception as e:
        return {"error": str(e)}
