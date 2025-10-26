# scripts/extract_orders_from_values.py
import pandas as pd
from pathlib import Path
import json
from datetime import datetime


def _read_sheet(excel_path: Path, sheet_name: str) -> pd.DataFrame:
    """共通の設定で Excel シートを読み込む"""
    # まず生データを読み込み
    df = pd.read_excel(
        excel_path,
        sheet_name=sheet_name,
        dtype=str,
        keep_default_na=False,
    )
    
    print(f"  📊 生データ: {len(df)}行 x {len(df.columns)}列")
    
    # ヘッダー行を探す（"invoice" 列を含む行）
    header_row = None
    for idx in range(min(10, len(df))):  # 最初の10行を探索
        row_values = df.iloc[idx].astype(str).str.lower()
        if any("invoice" in str(val) for val in row_values):
            header_row = idx
            print(f"  ✅ ヘッダー行を発見: {idx + 1}行目")
            break
    
    if header_row is not None and header_row > 0:
        # ヘッダー行以降を再読み込み
        df = pd.read_excel(
            excel_path,
            sheet_name=sheet_name,
            dtype=str,
            keep_default_na=False,
            header=header_row,
        )
        print(f"  📊 再読み込み後: {len(df)}行 x {len(df.columns)}列")
    
    # 空文字や空白のみのセルを NaN として扱う
    df = df.replace(r"^\s*$", pd.NA, regex=True)
    
    # 全ての値が欠損の行・列を削除
    df = df.dropna(how="all")
    df = df.dropna(axis=1, how="all")
    
    # 欠損値を空文字に戻す
    df = df.fillna("")
    
    # 列名をクリーンアップ
    df.columns = df.columns.str.strip()
    
    print(f"  ✅ クリーンアップ後: {len(df)}行 x {len(df.columns)}列")
    
    return df


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
    
    df = _read_sheet(excel_path, sheet_name)
    
    # invoice列の処理
    if "invoice" in df.columns:
        # 文字列に変換して前後の空白を削除
        df["invoice"] = df["invoice"].astype(str).str.strip()
        
        # 空文字列の行を削除
        df = df[df["invoice"] != ""]
        
        print(f"  ✅ 受注番号（最初の10件）:")
        for inv in df["invoice"].head(10):
            print(f"    - {inv}")
        
        if len(df) > 10:
            print(f"    ... (残り {len(df) - 10}件)")
        
        # TSE-IST-003-25 の確認
        if "TSE-IST-003-25" in df["invoice"].values:
            print(f"  ✅✅✅ TSE-IST-003-25 が見つかりました！")
        else:
            print(f"  ⚠️ TSE-IST-003-25 が見つかりません")
    else:
        print(f"  ❌ invoice 列が見つかりません")
        print(f"  📋 利用可能な列: {list(df.columns)}")
    
    # 出力
    output_path = output_dir / "受注登録.csv"
    df.to_csv(output_path, index=False, encoding="utf-8")
    print(f"✅ 出力完了: {output_path} ({len(df)}行)")
    
    return df


def extract_companies(excel_path: Path, output_dir: Path):
    """会社情報登録シートを抽出"""
    xl = pd.ExcelFile(excel_path)
    
    company_sheets = [s for s in xl.sheet_names if "会社" in s or "company" in s.lower()]
    
    if not company_sheets:
        print(f"⚠️ 会社シートが見つかりません")
        return None
    
    sheet_name = company_sheets[0]
    print(f"📄 会社シート: '{sheet_name}'")
    
    df = _read_sheet(excel_path, sheet_name)
    
    output_path = output_dir / "会社情報登録.csv"
    df.to_csv(output_path, index=False, encoding="utf-8")
    print(f"✅ 出力完了: {output_path} ({len(df)}行)")
    
    return df


def generate_manifest(output_dir: Path, orders_df, companies_df):
    """manifest.jsonを生成"""
    manifest = {
        "sheets": {},
        "generated_at": datetime.utcnow().isoformat() + "Z"
    }
    
    if orders_df is not None:
        manifest["sheets"]["受注登録"] = {
            "csv": "受注登録.csv",
            "rows": len(orders_df),
            "cols": len(orders_df.columns)
        }
    
    if companies_df is not None:
        manifest["sheets"]["会社情報登録"] = {
            "csv": "会社情報登録.csv",
            "rows": len(companies_df),
            "cols": len(companies_df.columns)
        }
    
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    print(f"✅ manifest.json 生成完了")


def main():
    try:
        excel_path = find_excel_file()
        output_dir = Path("dist")
        output_dir.mkdir(exist_ok=True)
        
        print("\n" + "="*60)
        print("📥 Excel → CSV 抽出開始")
        print("="*60 + "\n")
        
        orders_df = extract_orders(excel_path, output_dir)
        companies_df = extract_companies(excel_path, output_dir)
        generate_manifest(output_dir, orders_df, companies_df)
        
        print("\n" + "="*60)
        print("✅ すべての処理が完了しました")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
