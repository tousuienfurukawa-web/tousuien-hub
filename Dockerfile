FROM python:3.12-slim

# 作業ディレクトリを作成
WORKDIR /app

# 依存関係をコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリコードをコピー
COPY app ./app

# SlackデータZIPをコピー（ワイルドカードで柔軟に対応）
COPY slack_export*.zip ./ 2>/dev/null || true
COPY *.zip ./ 2>/dev/null || true

# デバッグ：ファイルが正しくコピーされたか確認
RUN ls -la /app && echo "Files in /app directory"

# ポート設定
EXPOSE 10000

# FastAPI起動
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]
