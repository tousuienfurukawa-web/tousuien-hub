# -*- coding: utf-8 -*-
import os
import json
import zipfile
from pathlib import Path

# SlackエクスポートZIPファイルの場所
ZIP_FILE_PATH = Path("slack_export_latest.zip")

# ------------------------------------------------------------
# 🔹 手動定義マッピング（users.json に無い or 日本語優先で上書き）
# ------------------------------------------------------------
USER_MAP = {
    "U08N3SKSL75": "木村",       # ← 修正済（末村 → 木村）
    "U08RVNRBY0O": "長谷川",
    "U0331FZS7JT": "岡 祐太",
    "U0331FWGQRM": "松井",
    "U033G4KN4TD": "福井",
    "U03BLQ65GK0": "会長",
    "U08FZUNPSQ3": "神谷",
    "U0331FZTHEK": "片寄",
    "U066P20UQH1": "林 遥香",
}

# ------------------------------------------------------------
# 🔹 users.json から自動マッピングを追加
# ------------------------------------------------------------
def load_user_map_from_zip(zip_path: Path) -> dict:
    """SlackエクスポートZIP内の users.json から ID→表示名 を取得"""
    if not zip_path.exists():
        return USER_MAP

    user_map = dict(USER_MAP)  # 手動定義をベースに拡張
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            if "users.json" in z.namelist():
                with z.open("users.json") as f:
                    users = json.load(f)
                    for u in users:
                        uid = u.get("id")
                        name = u.get("real_name") or u.get("name")
                        if uid and name:
                            user_map[uid] = name
    except Exception as e:
        print(f"[WARN] Failed to load users.json from ZIP: {e}")

    # 🔹 日本語手動定義を最終的に優先
    user_map.update(USER_MAP)
    return user_map


# ------------------------------------------------------------
# 🔹 公開API: ID→名前変換
# ------------------------------------------------------------
USER_MAP = load_user_map_from_zip(ZIP_FILE_PATH)

def resolve_user_name(user_id: str) -> str:
    """Slack IDを人間の名前に変換（未登録ならそのまま）"""
    if not user_id:
        return "不明"
    return USER_MAP.get(user_id, user_id)
