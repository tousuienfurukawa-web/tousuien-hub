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

        # 簡易処理: 各チャンネルJSONから TSE- を含むスレッドを抽出
        for root, _, files in os.walk("/app/data/slack_raw"):
            for file in files:
                if not file.endswith(".json"):
                    continue
                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                    data = json.load(f)
                for msg in data:
                    text = msg.get("text", "")
                    if "TSE-" in text:
                        inv = text.split("TSE-")[1].split()[0]
                        inv_code = "TSE-" + inv
                        out_path = os.path.join(DEST, f"{inv_code}.json")
                        with open(out_path, "w", encoding="utf-8") as out:
                            json.dump({"messages": [msg]}, out, ensure_ascii=False, indent=2)
        print("✅ Slack threads extracted successfully.")
    except Exception as e:
        print("⚠️ Extraction failed:", e)
else:
    print("⚠️ No slack_export_latest.zip found.")
