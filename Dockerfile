# ===========================================================
# Dockerfile for tousuien-hub (Render)
# ===========================================================

# ベースとなるPythonイメージを指定
FROM python:3.10-slim

# 作業ディレクトリ作成
WORKDIR /app

# 依存関係インストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリ全体をコピー
COPY . .

# FlaskでRenderが使うポート指定
ENV PORT=10000

# 起動コマンド（Flaskアプリ）
CMD ["python", "app/run_autopush.py"]
