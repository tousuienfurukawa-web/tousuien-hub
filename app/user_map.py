# -*- coding: utf-8 -*-
import os
import json
import zipfile
from pathlib import Path

# SlackエクスポートZIPファイルの場所
ZIP_FILE_PATH = Path("slack_export_latest.zip")

# ================================================================
# 手動定義マッピング（users.json に無いOR 日本語補完して上書き）
# ================================================================
USER_MAP = {
    "U8N3KSXL57": "木村",
    "U88NRYABY0": "阪前川",
    "U8331F25TF1": "岡 裕太",
    "U8331K4NQWB": "林",
    "U8331GKWQRP": "松井",
    "U83L05G5GK3": "金子",
    "U88LP06SU": "西本",
    "U8331FZTHEK": "片寄",
    "U066P2UQH1": "林 進喜",

    # 追記分
    "U08NVD403GV": "山本",
    "U08U8MMTH43": "布施 美穂",
    "U041RJKV5JA": "平川",
    "U05KGS6HN9H": "足立",
    "U0606SPN4BW": "古川 敏",
    "U082RF7UF1V": "三好",
    "U09DVFN4NM6": "今岡",
    "U09DF1SDTQR": "原 理恵",
    "U09DVFQM0AC": "吾郷 友佳子",
    "U08V56G9U92": "多久和",
}

# ================================================================
# users.json から自動マッピングを追加
# ================================================================
def load_user_map_from_zip(zip_path: Path) -> dict:
    """SlackエクスポートZIP内の users.json から表示名を取得"""
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
                        if uid and name and uid not in user_map:
                            user_map[uid] = name
    except Exception as e:
        print(f"Error loading user map: {e}")

    return user_map

# ---------------------------------------------------------------
# 🔹 resolve_user_name: user_idを実名に変換するユーティリティ
# ---------------------------------------------------------------
def resolve_user_name(user_id: str) -> str:
    if not user_id:
        return "（不明）"
    return USER_MAP.get(user_id, user_id)

