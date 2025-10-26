# scripts/debug_excel.py
import pandas as pd
from pathlib import Path

def debug_excel():
    excel_files = [
        Path("data/Customer_Management_latest.xlsx"),
        Path("data/Customer_Management_values.xlsx"),
        Path("Customer_Management_latest.xlsx"),
        Path("Customer_Management_values.xlsx"),
    ]
    
    for excel_path in excel_files:
        if not excel_path.exists():
            continue
            
        print(f"\n📂 ファイル: {excel_path}")
        xl = pd.ExcelFile(excel_path)
        print(f"📋 シート一覧: {xl.sheet_names}")
        
        for sheet in xl.sheet_names:
            df = pd.read_excel(excel_path, sheet_name=sheet)
            print(f"\n  📄 シート「{sheet}」: {len(df)}行 x {len(df.columns)}列")
            print(f"  列名: {list(df.columns)}")
            
            if "invoice" in df.columns or "受注番号" in df.columns:
                invoice_col = "invoice" if "invoice" in df.columns else "受注番号"
                print(f"  受注番号: {df[invoice_col].tolist()}")

if __name__ == "__main__":
    debug_excel()
