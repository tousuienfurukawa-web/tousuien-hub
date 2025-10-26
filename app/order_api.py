# -*- coding: utf-8 -*-
"""
app/order_api.py
/order/{invoice} エンドポイント（JSON / HTML）
- ORDERS_CSV_URL 環境変数があればそこから CSV を取得
- そうでなければリポジトリ内の dist/受注登録.csv を読み込む
- デプロイ保護用に環境変数 VERCEL_AUTOMATION_BYPASS_SECRET がセットされていれば
  リクエストヘッダ `X-Bypass-Token` の値を検証します。
"""

import os
import csv
import io
import time
import logging
import urllib.request
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse

logger = logging.getLogger("tousuien_hub.order_api")
router = APIRouter()

# 設定
ORDERS_CSV_URL = os.getenv("ORDERS_CSV_URL")  # 外部に置いた CSV を参照したいとき
LOCAL_CSV_PATH = Path(__file__).resolve().parent.parent / "dist" / "受注登録.csv"
# フォールバック: repo 内に data/ に置くパターンも試す
LOCAL_CSV_PATH_ALT = Path(__file__).resolve().parent.parent / "data" / "受注登録.csv"

BYPASS_SECRET = os.getenv("VERCEL_AUTOMATION_BYPASS_SECRET") or os.getenv("BYPASS_TOKEN")

# 簡易キャッシュ
_cache = {
    "orders": {},        # invoice -> row dict
    "loaded_at": 0,
    "csv_source": None
}
CACHE_TTL = 60  # 秒。必要なら長くする


def _fetch_csv_text_from_url(url: str, timeout: int = 10) -> str:
    logger.info("Fetching CSV from URL: %s", url)
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        raw = resp.read()
        # try utf-8, fallback to shift_jis
        try:
            return raw.decode("utf-8")
        except Exception:
            try:
                return raw.decode("cp932")
            except Exception:
                return raw.decode(errors="ignore")


def _load_orders(force: bool = False) -> Dict[str, Dict[str, str]]:
    """CSV を読み込んで invoice->row の dict を返す。キャッシュする。"""
    now = time.time()
    if not force and _cache["orders"] and now - _cache["loaded_at"] < CACHE_TTL:
        return _cache["orders"]

    csv_text = None
    source = None
    if ORDERS_CSV_URL:
        try:
            csv_text = _fetch_csv_text_from_url(ORDERS_CSV_URL)
            source = f"url:{ORDERS_CSV_URL}"
        except Exception as e:
            logger.warning("Failed to fetch ORDERS_CSV_URL: %s (%s)", ORDERS_CSV_URL, e)

    if csv_text is None:
        # try local path
        if LOCAL_CSV_PATH.exists():
            logger.info("Loading CSV from local: %s", LOCAL_CSV_PATH)
            csv_text = LOCAL_CSV_PATH.read_text(encoding="utf-8", errors="ignore")
            source = f"local:{LOCAL_CSV_PATH}"
        elif LOCAL_CSV_PATH_ALT.exists():
            logger.info("Loading CSV from local alt: %s", LOCAL_CSV_PATH_ALT)
            csv_text = LOCAL_CSV_PATH_ALT.read_text(encoding="utf-8", errors="ignore")
            source = f"local:{LOCAL_CSV_PATH_ALT}"

    if csv_text is None:
        logger.error("No CSV source found. ORDERS_CSV_URL=%s, LOCAL=%s", ORDERS_CSV_URL, LOCAL_CSV_PATH)
        _cache["orders"] = {}
        _cache["loaded_at"] = now
        _cache["csv_source"] = None
        return _cache["orders"]

    # parse CSV
    f = io.StringIO(csv_text)
    reader = csv.DictReader(f)
    orders = {}
    for row in reader:
        # invoice カラム名の候補を探す
        invoice_keys = [k for k in row.keys() if k and "invoice" in k.lower() or "受注管理番号" in k or k.lower() == "invoice"]
        invoice_val = None
        if invoice_keys:
            invoice_val = row.get(invoice_keys[0])
        else:
            # try common japanese name
            invoice_val = row.get("invoice") or row.get("受注管理番号") or row.get("受注番号")

        if invoice_val:
            key = str(invoice_val).strip()
            if key:
                orders[key] = row

    _cache["orders"] = orders
    _cache["loaded_at"] = now
    _cache["csv_source"] = source
    logger.info("Loaded %d orders from %s", len(orders), source)
    return orders


def _parse_products_from_row(row: Dict[str, str]) -> List[Dict[str, Any]]:
    """CSV の row から複数商品の情報を抽出する（商品名1, 商品コード1 ... のパターンを想定）"""
    products = []
    # try up to 12 items
    for i in range(1, 13):
        name_key = f"商品名{i}"
        code_key = f"商品コード{i}"
        qty_key = f"pc{i}"
        gppc_key = f"g/pc{i}"
        if name_key in row or code_key in row:
            name = row.get(name_key) or row.get(f"ProductName{i}") or row.get(f"商品名{i}")
            code = row.get(code_key) or row.get(f"ProductCode{i}")
            qty = row.get(qty_key) or row.get(f"数量{i}") or row.get("pc1") if i == 1 else row.get(qty_key)
            gppc = row.get(gppc_key)
            if any([name, code, qty, gppc]):
                products.append({
                    "index": i,
                    "code": code,
                    "name": name,
                    "quantity": qty,
                    "g_per_unit": gppc,
                    "raw": {k: row.get(k) for k in row.keys() if k.endswith(str(i))}
                })
    return products


def _ensure_auth(request: Request):
    """If BYPASS_SECRET is set, require header X-Bypass-Token == secret"""
    if not BYPASS_SECRET:
        return
    header = request.headers.get("x-bypass-token")
    if not header:
        logger.warning("Missing bypass token header")
        raise HTTPException(status_code=401, detail="Missing X-Bypass-Token header")
    if header != BYPASS_SECRET:
        logger.warning("Invalid bypass token: %s", header)
        raise HTTPException(status_code=401, detail="Invalid bypass token")


@router.get("/api/order/{invoice}", response_class=JSONResponse)
async def get_order_json(invoice: str, request: Request, refresh: Optional[int] = Query(0, description="1 to force reload CSV")):
    """
    Returns JSON with order details for the given invoice.
    - refresh=1 : force CSV reload
    - Authentication: if VERCEL_AUTOMATION_BYPASS_SECRET is set, send header X-Bypass-Token
    """
    try:
        _ensure_auth(request)
        orders = _load_orders(force=bool(refresh))
        if not orders:
            raise HTTPException(status_code=500, detail="Orders data not available. Ensure ORDERS_CSV_URL or dist/受注登録.csv exists.")

        row = orders.get(invoice)
        if not row:
            # try uppercase/lower normalize
            row = orders.get(invoice.upper()) or orders.get(invoice.lower())
        if not row:
            raise HTTPException(status_code=404, detail=f"Invoice {invoice} not found")

        products = _parse_products_from_row(row)
        result = {
            "invoice": invoice,
            "source": _cache.get("csv_source"),
            "row": row,
            "products": products
        }
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_order_json failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/order/{invoice}.html", response_class=HTMLResponse)
async def get_order_html(invoice: str, request: Request, refresh: Optional[int] = Query(0)):
    """HTML 版。ブラウザで見やすくする。"""
    _ensure_auth(request)
    orders = _load_orders(force=bool(refresh))
    if not orders:
        return HTMLResponse("<h3>Orders CSV not available</h3>", status_code=500)
    row = orders.get(invoice) or orders.get(invoice.upper()) or orders.get(invoice.lower())
    if not row:
        return HTMLResponse(f"<h3>Invoice {invoice} not found</h3>", status_code=404)

    products = _parse_products_from_row(row)

    html = [
        "<html><head><meta charset='utf-8'><title>Order: {}</title></head><body>".format(invoice),
        f"<h1>受注情報: {invoice}</h1>",
        "<h2>基本情報</h2><table border='1' cellpadding='6'>"
    ]
    for k, v in row.items():
        html.append("<tr><th style='text-align:left'>{}</th><td>{}</td></tr>".format(k, v or ""))
    html.append("</table>")

    html.append("<h2>商品一覧</h2>")
    html.append("<table border='1' cellpadding='6'><tr><th>#</th><th>商品コード</th><th>商品名</th><th>数量</th><th>その他</th></tr>")
    for p in products:
        html.append("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td><pre>{}</pre></td></tr>".format(
            p.get("index"), p.get("code") or "", p.get("name") or "", p.get("quantity") or "", p.get("raw")
        ))
    html.append("</table>")

    html.append("</body></html>")
    return HTMLResponse("\n".join(html))
