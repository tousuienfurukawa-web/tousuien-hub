# app/__init__.py
import zipfile
import os
import json
import logging
import errno
from pathlib import Path
from typing import Optional

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

# ---------------------------
# Helper: create dirs with fallback to /tmp
# ---------------------------
def make_dir_with_fallback(path_str: str, fallback_name: str) -> Path:
    """
    Try to create the given path. If creation fails due to read-only fs or permission,
    fall back to /tmp/<fallback_name>. Return the Path actually used.
    """
    p = Path(path_str)
    try:
        p.mkdir(parents=True, exist_ok=True)
        return p
    except OSError as e:
        if getattr(e, "errno", None) in (errno.EROFS, errno.EACCES, errno.EPERM):
            tmp = Path("/tmp") / fallback_name
            try:
                tmp.mkdir(parents=True, exist_ok=True)
                logging.warning("Filesystem read-only or no permission. Using fallback: %s", tmp)
                return tmp
            except Exception:
                logging.exception("Failed to create fallback dir %s", tmp)
                # return tmp path object even if creation failed (best-effort)
                return tmp
        else:
            logging.exception("Failed to create dir %s", p)
            raise

def safe_write_json(path: Path, obj) -> Optional[Path]:
    """
    Try to write JSON to path. If fails due to write error, fallback to /tmp.
    Returns the Path actually written, or None on fatal failure.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return path
    except OSError as e:
        logging.warning("Failed to write to %s (%s), falling back to /tmp", path, e)
        tmp = Path("/tmp") / path.name
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
            return tmp
        except Exception:
            logging.exception("Failed to write fallback JSON %s", tmp)
            return None

# ---------------------------
# Paths (config via env allowed)
# ---------------------------
BASE_DIR = Path(__file__).resolve().parent
SRC = Path(os.environ.get("ZIP_PATH", str(BASE_DIR / "slack_export_latest.zip")))
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data")))
DEST = Path(os.environ.get("DEST", str(DATA_DIR / "slack_threads")))
RAW_DIR = Path(os.environ.get("RAW_DIR", str(DATA_DIR / "slack_raw")))

# Apply safe creation (may fall back to /tmp)
DATA_DIR = make_dir_with_fallback(str(DATA_DIR), "app_data")
DEST = make_dir_with_fallback(str(DEST), "slack_threads")
RAW_DIR = make_dir_with_fallback(str(RAW_DIR), "slack_raw")

# ---------------------------
# ZIP safe extract (handle cp437 -> utf-8 filenames)
# ---------------------------
def safe_extract(zip_ref: zipfile.ZipFile, dest: Path):
    """Extract zip entries, fixing cp437->utf-8 filename issues, writing into dest."""
    for zip_info in zip_ref.infolist():
        try:
            # Try re-decoding filename to handle japanese encodings in some zips
            try:
                fixed_name = zip_info.filename.encode("cp437").decode("utf-8")
            except Exception:
                fixed_name = zip_info.filename
            # ensure we don't write outside dest
            target_path = dest.joinpath(fixed_name)
            target_dir = target_path.parent
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                # If creation fails, try to use /tmp as a fallback directory for this file
                tmp_dir = Path("/tmp") / "slack_raw_fallback" / target_dir.name
                tmp_dir.mkdir(parents=True, exist_ok=True)
                target_path = tmp_dir / target_path.name
                logging.warning("Falling back writing extracted file to %s", target_path)

            with zip_ref.open(zip_info) as source:
                with open(target_path, "wb") as target:
                    target.write(source.read())
        except Exception as e:
            logging.exception("Failed to extract %s: %s", zip_info.filename, e)

# ---------------------------
# normalize_data helper
# ---------------------------
def normalize_data(data):
    """Slack JSON data normalization: always return list of messages."""
    if isinstance(data, dict):
        return [data]
    elif isinstance(data, list):
        return data
    else:
        return []

# ---------------------------
# Extraction & processing (only if ZIP exists)
# This step is best-effort and safe against read-only FS.
# ---------------------------
if SRC.exists():
    try:
        # Open zip and extract files into RAW_DIR (fallbacks handled inside)
        try:
            with zipfile.ZipFile(SRC, "r") as zip_ref:
                safe_extract(zip_ref, RAW_DIR)
        except zipfile.BadZipFile:
            logging.exception("Bad ZIP file: %s", SRC)
            raise

        found = 0
        skipped = 0

        # Walk RAW_DIR and process json files
        for root, _, files in os.walk(str(RAW_DIR)):
            for file in files:
                if not file.endswith(".json"):
                    continue
                path = Path(root) / file
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    logging.warning("JSON load failed for %s: %s", path, e)
                    skipped += 1
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

                        # Extract invoice code from text safely
                        try:
                            parts = text.split("TSE-")[1].split()[0].split("\n")[0]
                            inv_code = "TSE-" + parts
                        except Exception:
                            skipped += 1
                            continue

                        dest_path = DEST / f"{inv_code}.json"

                        # If exists, merge; else create
                        if dest_path.exists():
                            try:
                                with open(dest_path, "r", encoding="utf-8") as ex:
                                    old = json.load(ex)
                            except Exception:
                                old = {"messages": []}
                            old.setdefault("messages", []).append(msg)
                            # try safe write
                            written = safe_write_json(dest_path, old)
                            if written is None:
                                logging.warning("Failed to persist merged data for %s", dest_path)
                        else:
                            written = safe_write_json(dest_path, {"messages": [msg]})
                            if written is None:
                                logging.warning("Failed to persist new data for %s", dest_path)

                        found += 1
                    except Exception:
                        skipped += 1
                        continue

        logging.info("Extracted %d messages from Slack export into %s", found, DEST)
        logging.info("Skipped %d invalid entries", skipped)
    except Exception as e:
        logging.exception("Extraction failed unexpectedly: %s", e)
else:
    logging.info("No Slack export found at %s", SRC)
