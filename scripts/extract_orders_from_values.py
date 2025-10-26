# scripts/extract_orders_from_values.py
import pandas as pd
from pathlib import Path
import json
from datetime import datetime

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
    print(f"📄 受注シート: {sheet_name}")
    
    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    print(f"📊 読み込み: {len(df)}行 x {len(df.columns)}列")
    print(f"📋 列名: {list(df.columns)}")
    
    # 空行を削除
    df = df.dropna(how="all")
    
    # invoiceカラムがあるか確認
    if "invoice" in df.columns:
        print(f"✅ 受注番号: {df['invoice'].tolist()}")
    
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
    print(f"📄 会社シート: {sheet_name}")
    
    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    df = df.dropna(how="all")
    
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
        
        print("\n" + "="*50)
        print("📥 Excel → CSV 抽出開始")
        print("="*50 + "\n")
        
        orders_df = extract_orders(excel_path, output_dir)
        companies_df = extract_companies(excel_path, output_dir)
        generate_manifest(output_dir, orders_df, companies_df)
        
        print("\n" + "="*50)
        print("✅ すべての処理が完了しました")
        print("="*50)
        
    except Exception as e:
        print(f"\n❌ エラー: {e}")
        raise

if __name__ == "__main__":
    main()
