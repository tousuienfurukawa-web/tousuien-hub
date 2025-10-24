# app/api_server.py

from fastapi import FastAPI, Query
from analysis.chat_command_handler import handle_chat_command

app = FastAPI()

@app.get("/")
@app.head("/")
def root():
    return {"message": "TOUSUIEN Hub API is running."}

@app.get("/query")
def query(text: str = Query(..., description="自然言語での企業照会コマンド")):
    """
    ChatGPTや外部サービスからの自然言語クエリを受け取り、処理結果を返す。
    """
    try:
        result = handle_chat_command(text)
        
        # ChatGPT用に構造化されたレスポンスを返す
        return {
            "success": True,
            "query": text,
            "response": result,
            "format": "text"  # ChatGPTに「テキストとして表示してください」と伝える
        }
    except Exception as e:
        return {
            "success": False,
            "query": text,
            "error": str(e)
        }
