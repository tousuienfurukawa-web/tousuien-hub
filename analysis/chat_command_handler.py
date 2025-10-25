# handler.py
"""
Vercel 等が handler を期待する場合の簡易アダプタ。
FastAPI の app を handler としてエクスポートします。
"""

import logging

# まずは app をインポート（パッケージ構成によって import パスを変えてください）
app = None
try:
    # 推奨: app は app/main.py の中で定義済み（app = FastAPI()）
    from app.main import app as app  # package 形式の場合
    logging.info("Imported app from app.main")
except Exception:
    try:
        # fallback: ルートに main.py がある場合
        from main import app as app
        logging.info("Imported app from main")
    except Exception:
        logging.exception("Could not import FastAPI 'app' from app.main or main")

# Vercel 等が期待する名前でエクスポート
handler = app
