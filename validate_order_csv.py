# validate_order_csv.py
# Usage: python validate_order_csv.py dist/受注登録.csv
# Outputs a concise PR-ready summary to stdout and exits non-zero on fatal errors.

import sys
import re
import csv
from decimal import Decimal

if len(sys.argv) < 2:
    print("Usage: python validate_order_csv.py <csv_path>")
    sys.exit(2)

csv_path = sys.argv[1]

# 必須列（シートのヘッダと完全一致することを想定）
req_cols = ["invoice", "企業コード", "商品総額", "通貨", "輸送方法", "入金確認日①"]

def is_number(s):
    if s is None:
        return False
    s2 = str(s).strip()
    if s2 == "":
        return False
    # カンマや通貨表記を除去して数値判定
    s2 = s2.replace(",", "").replace("USD", "").replace("JPY", "").strip()
    try:
        Decimal(s2)
        return True
    except:
        return False

# CSV 読み込み（quoted fields with newlines に対応）
try:
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = list(reader)
except FileNotFoundError:
    print(f"ERROR: File not found: {csv_path}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: Failed to read CSV: {e}")
    sys.exit(1)

if not rows:
    print("ERROR: CSV is empty")
    sys.exit(1)

header = rows[0]
hdr_map = {h.strip(): i for i, h in enumerate(header)}

total = max(0, len(rows) - 1)
print(f"総行数（ヘッダ除く）: {total}")

# 必須列チェック
missing_cols = [c for c in req_cols if c not in hdr_map]
if missing_cols:
    print("必須列が欠けています:", missing_cols)
else:
    print("必須列は存在します。")

# invoice フォーマットチェック（先頭が TSE- であることを期待）
inv_idx = hdr_map.get("invoice")
bad_inv = []
if inv_idx is not None:
    for rnum, row in enumerate(rows[1:], start=2):
        inv = row[inv_idx].strip() if len(row) > inv_idx else ""
        if inv != "" and not re.match(r'^TSE-', inv):
            bad_inv.append((rnum, inv))
print(f"Invoice 先頭 'TSE-' でない件数: {len(bad_inv)}")
if bad_inv:
    print("例（先頭最大5件）:")
    for r, i in bad_inv[:5]:
        print(f"  行 {r}: {i}")

# 商品総額の数値チェック
amt_idx = hdr_map.get("商品総額")
bad_amt = []
if amt_idx is not None:
    for rnum, row in enumerate(rows[1:], start=2):
        amt = row[amt_idx].strip() if len(row) > amt_idx else ""
        if amt != "" and not is_number(amt):
            bad_amt.append((rnum, amt))
print(f"商品総額が数値でない件数: {len(bad_amt)}")
if bad_amt:
    print("例（上位5件）:")
    for r, a in bad_amt[:5]:
        print(f"  行 {r}: {a}")

# Excel の式エラー検出 (#NAME? など)
name_error_re = re.compile(r'#NAME\?|#REF|#VALUE|#DIV/0!', re.IGNORECASE)
err_rows = set()
for rnum, row in enumerate(rows[1:], start=2):
    for cell in row:
        if isinstance(cell, str) and name_error_re.search(cell):
            err_rows.add(rnum)
            break
print(f"#NAME? / 式エラーを含む行数: {len(err_rows)} (例行: {sorted(list(err_rows))[:5]})")

# 輸送方法の想定チェック（必要があれば allowed を拡張）
ship_idx = hdr_map.get("輸送方法")
allowed = {"DHL", "UPS", "FedEx", "EMS", "DPD"}
bad_ship = []
if ship_idx is not None:
    for rnum, row in enumerate(rows[1:], start=2):
        s = row[ship_idx].strip() if len(row) > ship_idx else ""
        if s and s not in allowed:
            bad_ship.append((rnum, s))
print(f"想定外の輸送方法件数: {len(bad_ship)} (例: {bad_ship[:5]})")

# PR 用サマリ出力
print("\n=== PR用サマリ（コピペ可） ===")
print(f"- データ行数: {total} 行")
if missing_cols:
    print(f"- 必須列の欠損: {missing_cols}")
else:
    print("- 必須列の欠損: なし")
print(f"- Invoice 先頭 TSE- でない件数: {len(bad_inv)}")
print(f"- 商品総額が数値でない件数: {len(bad_amt)}")
print(f"- #NAME?/式エラーを含む行数: {len(err_rows)}")
print(f"- 想定外の輸送方法件数: {len(bad_ship)}")

# 致命的エラー判定（必須列欠落またはデータ行ゼロで失敗）
if missing_cols or total == 0:
    sys.exit(1)

sys.exit(0)
