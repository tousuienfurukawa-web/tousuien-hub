# app/__init__.py
import zipfile
import os
import json
import logging
from pathlib import Path

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Base dir inside package
BASE_DIR = Path(__file__).resolve().parent

# Slack export zip inside app folder (if uploaded)
SRC = BASE_DIR / "slack_export_latest.zip"

# prefer app writable dir, fallback to /tmp if not writable
def ensure_writable_dir(path: Path):
    try:
        path.mkdir(parents=True, exist_ok=True)
        # try to create a temp file to ensure actually writable
        test = path / ".writable_test"
        test.write_text("ok")
        test.unlink()
        return path
    except Exception:
        tmp = Path(os.getenv("TMPDIR", "/tmp")) / path.name
        os.makedirs(tmp, exist_ok=True)
        logger.warning("Filesystem read-only or no permission. Using fallback: %s", tmp)
        return Path(tmp)

DATA_DIR = BASE_DIR / "data"
DATA_DIR = ensure_writable_dir(DATA_DIR)

DEST = DATA_DIR / "slack_threads"
RAW_DIR = DATA_DIR / "slack_raw"

DEST = ensure_writable_dir(DEST)
RAW_DIR = ensure_writable_dir(RAW_DIR)

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
                    logger.warning("⚠️ JSON読み込み失敗: %s (%s)", file, e)
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

        logger.info("✅ Extracted %d messages from Slack export into %s", found, DEST)
        logger.info("⚙️ Skipped %d invalid entries", skipped)
    except Exception as e:
        logger.exception("⚠️ Extraction failed unexpectedly: %s", e)
else:
    logger.info("⚠️ No Slack export found at %s", SRC)
