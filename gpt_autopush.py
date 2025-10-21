# gpt_autopush.py （サーバー側で実行）
from github import Github
import openai
import os

# --- 環境変数から認証 ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = "user/tousuien-hub"
FILE_PATH = "src/routes/slack/thread.ts"

# --- GPTでコード生成（擬似例） ---
code = openai.ChatCompletion.create(
    model="gpt-5-turbo",
    messages=[{"role": "user", "content": "slack thread補完ロジックを書いて"}]
).choices[0].message["content"]

# --- GitHubにpush ---
g = Github(GITHUB_TOKEN)
repo = g.get_repo(REPO_NAME)
contents = repo.get_contents(FILE_PATH, ref="main")
repo.update_file(
    path=FILE_PATH,
    message="Auto-update from GPT",
    content=code,
    sha=contents.sha,
    branch="main"
)
print("✅ GitHub updated — Render will deploy automatically.")
