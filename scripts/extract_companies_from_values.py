# scripts/extract_orders_from_values.py
import pandas as pd
from pathlib import Path
import json
from datetime import datetime, timezone


def _find_header_row(excel_path: Path, sheet_name: str) -> int:
    """ヘッダー行（invoice列を含む行）を探す"""
    # 最初の20行を読み込んでヘッダー行を探す
    df_preview = pd.read_excel(
        excel_path,
        sheet_name=sheet_name,
        nrows=20,
        header=None,
        dtype=str,
    )
    
    for idx in range(len(df_preview)):
        row_values = df_preview.iloc[idx].astype(str).str.lower().str.strip()
        if any("invoice" in str(val) for val in row_values):
            print(f"  ✅ ヘッダー行を発見: {idx + 1}行目（Excelの行番号）")
            return idx
    
    print(f"  ⚠️ ヘッダー行が見つかりませんでした。デフォルト（1行目）を使用します")
    return 0


def find_excel_file():
    """Excelファイルを探す"""
    candidates = [
        Path("data/Customer_Management_latest.xlsx"),
        Path("data/Customer_Management_values.xlsx"),
        Path("Customer_Management_latest.xlsx"),
        Path("Customer_Management_values.xlsx"),
    ]
    
    for path in candidates:
        if path.exists():
            print(f"✅ Excelファイル発見: {path}")
            return path
    
    raise FileNotFoundError("❌ Customer_Management ファイルが見つかりません")


def extract_orders(excel_path: Path, output_dir: Path):
    """受注登録シートを抽出"""
    xl = pd.ExcelFile(excel_path)
    
    # シート名を柔軟に検索
    order_sheets = [s for s in xl.sheet_names if "受注" in s or "order" in s.lower()]
    
    if not order_sheets:
        print(f"⚠️ 受注シートが見つかりません。利用可能なシート: {xl.sheet_names}")
        return None
    
    sheet_name = order_sheets[0]
    print(f"📄 受注シート: '{sheet_name}'")
    
    # ヘッダー行を自動検出
    header_row = _find_header_row(excel_path, sheet_name)
    
    # データを読み込み
    df = pd.read_excel(
        excel_path,
        sheet_name=sheet_name,
        header=header_row,
        dtype=str,
        keep_default_na=False,
    )
    
    print(f"  📊 読み込み: {len(df)}行 x {len(df.columns)}列")
    
    # 列名をクリーンアップ
    df.columns = df.columns.astype(str).str.strip()
    
    # 空文字や空白のみを NaN として扱う
    df = df.replace(r"^\s*$", pd.NA, regex=True)
    
    # 全てが NaN の行を削除
    df = df.dropna(how="all")
    
    # NaN を空文字に戻す
    df = df.fillna("")
    
    # 列名のプレビュー
    columns = list(df.columns)
    preview_columns = 10
    if len(columns) > preview_columns:
        print(f"  📋 列名: {columns[:preview_columns]} ... 他{len(columns) - preview_columns}列")
    else:
        print(f"  📋 列名: {columns}")
    
    # invoice列の処理
    if "invoice" in df.columns:
        # 文字列に変換して前後の空白を削除
        df["invoice"] = df["invoice"].astype(str).str.strip()
        
        # 空文字列の行を除外
        df = df[df["invoice"] != ""]
        
        invoices = df["invoice"].tolist()
        total = len(invoices)
        preview_count = 10
        
        print(f"  ✅ 受注番号: {total}件")
        print(f"     先頭{min(preview_count, total)}件: {invoices[:preview_count]}")
        
        # TSE-IST-003-25 の確認
        t
