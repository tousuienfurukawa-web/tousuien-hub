import zipfile
import os
import json

SRC = "/app/slack_export_latest.zip"
DEST = "/app/data/slack_threads"
RAW_DIR = "/app/data/slack_raw"

os.makedirs(DEST, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)

def safe_extract(zip_ref, dest):
    """日本語ファイル名の文字化けを修正しながら展開"""
    for zip_info in zip_ref.infolist():
        try:
            fixed_name = zip_info.filename.encode('cp437').decode('utf-8')
        except Exception:
            fixed_name = zip_info.filename
        target_path = os.path.join(dest, fixed_name)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with zip_ref.open(zip_info) as source, open(target_path, "wb") as target:
            target.write(source.read())

if os.path.exists(SRC):
    try:
        with zipfile.ZipFile(SRC, "r") as zip_ref:
            safe_extract(zip_ref, RAW_DIR)

        found = 0
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

                # Slackエクスポートは、リスト or 辞書のどちらもあり得る
                if isinstance(data, dict):
                    data = [data]

                for msg in data:
                    if not isinstance(msg, dict):
                        continue  # str や list を無視
                    text = msg.get("text", "")
                    if not isinstance(text, str):
                        continue

                    if "TSE-" in text:
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

        print(f"✅ Extracted {found} messages from Slack export into {DEST}")
    except Exception as e:
        print("⚠️ Extraction failed:", e)
else:
    print("⚠️ No slack_export_latest.zip found.")
