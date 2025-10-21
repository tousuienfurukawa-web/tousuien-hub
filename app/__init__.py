import os
from flask import Flask

# Blueprintをインポート
from app.routes.slack_thread import bp as slack_bp

def create_app():
    """
    Flaskアプリ全体の初期化関数。
    Renderでもローカルでも動作する設定。
    """
    app = Flask(__name__)

    # Blueprint登録（SlackスレッドAPIなど）
    app.register_blueprint(slack_bp)

    # 動作確認用のトップページ（オプション）
    @app.route("/")
    def index():
        return {
            "status": "ok",
            "service": "tousuien-hub",
            "message": "Flask app is running 🎉"
        }

    return app


# 直接実行されたときだけサーバーを起動
if __name__ == "__main__":
    app = create_app()

    # Renderでは環境変数 PORT を使用（なければ10000）
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
