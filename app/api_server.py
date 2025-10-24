# app/api_server.py
from fastapi import FastAPI, Query
from analysis.chat_command_handler import handle_chat_command

app = FastAPI()

@app.get("/")
def root():
    return {"message": "TOUSUIEN Hub API is running."}

@app.get("/query")
def query_company(text: str = Query(..., description="自然言語での企業照会コマンド")):
    """
    ChatGPTから呼び出すAPI。
    例: /query?text=RNIの2025注文一覧
    """
    try:
        result = handle_chat_command(text)
        return {"response": result}
    except Exception as e:
        return {"error": str(e)}
