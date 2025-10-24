import zipfile
import os
import json
from pathlib import Path

# ✅ ベースディレクトリを動的に決定（Render / ローカル共通）
BASE_DIR = Path(__file__).resolve().parent
SRC = BASE_DIR / "slack_export_latest.zip"
DATA_DIR = BASE_DIR / "data"
DEST = DATA_DIR / "slack_threads"
RAW_DIR = DATA_DIR / "slack_raw"

# ✅ 書き込み可能な場所にディレクトリ作成
os.makedirs(DEST, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)

def safe_extract(zip_ref, dest):
    """日本語ファイル名の文字化けを修正しながら展開"""
    for zip_info in zip_ref.infolist():
        try:
            fixed_name = zip_info.filename.encode("cp437").decode("utf-8")
        except Exception:
            fixed_name = zip_info.filename
        target_path = os.path.join(dest, fixed_name)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with zip_ref.open(zip_info) as source, open(target_path, "wb") as target:
            target.write(source.read())

def normalize_data(data):
    """Slack JSONデータを常にリスト化"""
    if isinstance(data, dict):
        return [data]
    elif isinstance(data, list):
        return data
    else:
        return []

# ✅ SlackエクスポートZIPが存在する場合のみ処理
if SRC.exists():
    try:
        with zipfile.ZipFile(SRC, "r") as zip_ref:
            safe_extract(zip_ref, RAW_DIR)

        found = 0
        skipped = 0

        for root, _, files in os.walk(RAW_DIR):
            for file in files:
                if not file.endswith(".json"):
                    continue
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    print(f"⚠️ JSON読み込み失敗: {file} ({e})")
                    continue

                for msg in normalize_data(data):
                    try:
                        if not isinstance(msg, dict):
                            skipped += 1
                            continue
                        text = msg.get("text")
                        if not isinstance(text, str) or "TSE-" not in text:
                            skipped += 1
                            continue

                        parts = text.split("TSE-")[1].split()[0].split("\n")[0]
                        inv_code = "TSE-" + parts
                        dest_path = os.path.join(DEST, f"{inv_code}.json")

                        if os.path.exists(dest_path):
                            with open(dest_path, "r", encoding="utf-8") as ex:
                                old = json.load(ex)
                            old.setdefault("messages", []).append(msg)
                            with open(dest_path, "w", encoding="utf-8") as out:
                                json.dump(old, out, ensure_ascii=False, indent=2)
                        else:
                            with open(dest_path, "w", encoding="utf-8") as out:
                                json.dump({"messages": [msg]}, out, ensure_ascii=False, indent=2)

                        found += 1
                    except Exception:
                        skipped += 1
                        continue

        print(f"✅ Extracted {found} messages from Slack export into {DEST}")
        print(f"⚙️ Skipped {skipped} invalid entries")
    except Exception as e:
        print("⚠️ Extraction failed unexpectedly:", e)
else:
    print(f"⚠️ No Slack export found at {SRC}")
