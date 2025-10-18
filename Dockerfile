FROM python:3.12-slim

# 作業ディレクトリを作成
WORKDIR /app

# 依存関係をコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリコードをコピー
COPY app ./app

# SlackデータZIPをコピー（存在する場合のみ）
# まず全体を一時ディレクトリにコピーしてからZIPだけ抽出
COPY . /tmp/build/
RUN if ls /tmp/build/slack_export*.zip 1> /dev/null 2>&1; then \
        cp /tmp/build/slack_export*.zip /app/; \
    elif ls /tmp/build/*.zip 1> /dev/null 2>&1; then \
        cp /tmp/build/*.zip /app/; \
    fi && \
    rm -rf /tmp/build

# デバッグ：ファイルが正しくコピーされたか確認
RUN ls -la /app && echo "=== Files in /app directory ===" && \
    if ls /app/*.zip 1> /dev/null 2>&1; then \
        echo "✅ ZIP file found:" && ls -lh /app/*.zip; \
    else \
        echo "⚠️ No ZIP file found"; \
    fi

# ポート設定
EXPOSE 10000

# FastAPI起動
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]
