# -*- coding: utf-8 -*-
"""
app/order_api.py

CSV(dist/受注登録.csv) を読み、受注番号で検索する軽量な FastAPI ルーター。
使い方:
  1) このファイルを app/order_api.py として保存
  2) app/main.py の「app = FastAPI(...)」の直後などで以下を追加:
       from .order_api import router as order_router
       app.include_router(order_router)
  3) デプロイ後、/api/order/{invoice} にアクセスすると JSON を返します。

補足:
- CSV は repo ルートの dist/受注登録.csv を優先して使います。
- 環境変数 ORDER_CSV_PATH を指定すると、そのパスを優先します。
- CSV のエンコーディングは utf-8-sig を想定しています（BOM に対応）。
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path
from typing import List, Dict, Any
import csv
import os
import logging

logger = logging.getLogger("tousuien_hub.order_api")
router = APIRouter()


def _locate_csv() -> Path:
    """
    Locate dist/受注登録.csv in repo or use ORDER_CSV_PATH env var.
    Returns Path (may not exist — caller should check .exists()).
    """
    # 1) explicit override via env
    env_path = os.environ.get("ORDER_CSV_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            logger.info("Using ORDER_CSV_PATH: %s", p)
            return p
        else:
            logger.warning("ORDER_CSV_PATH set but file not found: %s", p)

    # 2) repo-root/dist/受注登録.csv
    repo_root = Path(__file__).resolve().parent.parent
    candidate = repo_root / "dist" / "受注登録.csv"
    if candidate.exists():
        logger.info("Found orders CSV at: %s", candidate)
        return candidate

    # 3) fallback: any .csv under repo_root/dist
    dist_dir = repo_root / "dist"
    if dist_dir.exists():
        for p in dist_dir.glob("*.csv"):
            logger.info("Using first CSV found in dist/: %s", p)
            return p

    # 4) fallback /tmp
    fallback = Path("/tmp/dist/受注登録.csv")
    if fallback.exists():
        logger.info("Using fallback CSV at %s", fallback)
        return fallback

    # 5) return expected path even if missing (caller will handle)
    return candidate


def _read_csv(path: Path) -> List[Dict[str, str]]:
    """
    Read CSV as list[dict]. Use utf-8-sig to handle BOM if present.
    """
    rows: List[Dict[str, str]] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            # normalize None -> ""
            rows.append({(k if k is not None else ""): (v if v is not None else "") for k, v in r.items()})
    return rows


@router.get("/api/order/{invoice}", response_class=JSONResponse)
def get_order(invoice: str):
    """
    Return JSON containing matching records for the given invoice.
    Strategy:
      1) Exact match against any cell value.
      2) Exact match against common invoice header names if present (invoice, Invoice, 受注管理番号 など).
      3) If no hit, try case-insensitive substring match.
    """
    csv_path = _locate_csv()
    if not csv_path.exists():
        logger.warning("Order CSV not found at expected location: %s", csv_path)
        raise HTTPException(status_code=404, detail=f"Order CSV not found. Expected at {csv_path}")

    try:
        rows = _read_csv(csv_path)
    except Exception as e:
        logger.exception("Failed to read orders CSV: %s", e)
        raise HTTPException(status_code=500, detail="Failed to read orders CSV")

    invoice = invoice.strip()
    matches: List[Dict[str, Any]] = []

    # 1) Exact equality match (any cell equals invoice)
    for r in rows:
        found = False
        for v in r.values():
            if isinstance(v, str) and v.strip() == invoice:
                matches.append(r)
                found = True
                break
        if found:
            continue

        # 2) try common invoice-like header exact matches
        for key in ("invoice", "Invoice", "受注番号", "受注 No", "受注管理番号", "WIP 受注管理番号"):
            if key in r and r.get(key) and isinstance(r.get(key), str) and r.get(key).strip() == invoice:
                matches.append(r)
                found = True
                break
        if found:
            continue

    # 3) If nothing found, try case-insensitive substring search across values
    if not matches:
        invoice_lower = invoice.lower()
        for r in rows:
            for v in r.values():
                if isinstance(v, str) and invoice_lower in v.lower():
                    matches.append(r)
                    break

    if not matches:
        raise HTTPException(status_code=404, detail=f"{invoice} not found in {csv_path}")

    # Return records (as-is). The client (or Custom GPT) can format as needed.
    return {
        "invoice": invoice,
        "count": len(matches),
        "records": matches,
        "source_csv": str(csv_path),
    }
