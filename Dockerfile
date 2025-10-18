# ===== Dockerfile (Tousuien Hub 用) =====
FROM python:3.12-slim

# 作業ディレクトリ設定
WORKDIR /app

# 依存関係をコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# FastAPIサーバー起動
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]
