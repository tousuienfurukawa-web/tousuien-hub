# Pythonイメージを使用
FROM python:3.12-slim

# 作業ディレクトリを作成
WORKDIR /app

# 依存関係をコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリコードをコピー
COPY app ./app

# SlackデータZIPを明示的にコピー
COPY "海外 Slack export Feb 17 2022 - Oct 16 2025.zip" "./"

# ポート設定
EXPOSE 10000

# FastAPI起動
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]
