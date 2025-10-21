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
        # SlackエクスポートZIPのファイル名はcp437でエンコードされていることが多い
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

                for msg in normalize_data(data):
                    # メッセージがdictでない場合はスキップ（例：文字列やリスト）
                    if not isinstance(msg, dict):
                        continue
                    text = msg.get("text")
                    if not isinstance(text, str):
                        continue
                    if "TSE-" not in text:
                        continue

                    # TSE-形式のInvoice番号を抽出
                    try:
                        parts = text.split("TSE-")[1].split()[0].split("\n")[0]
                        inv_code = "TSE-" + parts
                    except Exception:
                        continue

                    dest_path = os.path.join(DEST, f"{inv_code}.json")

                    try:
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
                    except Exception as e:
                        print(f"⚠️ 書き込み失敗: {inv_code} ({e})")

        print(f"✅ Extracted {found} messages from Slack export into {DEST}")
    except Exception as e:
        print("⚠️ Extraction failed unexpectedly:", e)
else:
    print("⚠️ No slack_export_latest.zip found.")
