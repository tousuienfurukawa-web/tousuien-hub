import zipfile
import os
import json

SRC = "/app/slack_export_latest.zip"
DEST = "/app/data/slack_threads"

os.makedirs(DEST, exist_ok=True)

if os.path.exists(SRC):
    try:
        with zipfile.ZipFile(SRC, "r") as zip_ref:
            zip_ref.extractall("/app/data/slack_raw")

        found = 0
        for root, _, files in os.walk("/app/data/slack_raw"):
            for file in files:
                if not file.endswith(".json"):
                    continue
                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                    data = json.load(f)

                for msg in data:
                    text = msg.get("text", "")
                    # より柔軟に「TSE-」を含む文字列すべてを検出
                    if "TSE-" in text:
                        parts = text.split("TSE-")[1].split()[0].split("\n")[0]
                        inv_code = "TSE-" + parts
                        path = os.path.join(DEST, f"{inv_code}.json")

                        # ファイルが存在しなければ新規作成、あれば追加
                        if os.path.exists(path):
                            with open(path, "r", encoding="utf-8") as ex:
                                old = json.load(ex)
                            old["messages"].append(msg)
                            with open(path, "w", encoding="utf-8") as out:
                                json.dump(old, out, ensure_ascii=False, indent=2)
                        else:
                            with open(path, "w", encoding="utf-8") as out:
                                json.dump({"messages": [msg]}, out, ensure_ascii=False, indent=2)

                        found += 1

        print(f"✅ Extracted {found} messages into {DEST}")
    except Exception as e:
        print("⚠️ Extraction failed:", e)
else:
    print("⚠️ No slack_export_latest.zip found.")
