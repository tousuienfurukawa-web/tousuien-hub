# scripts/debug_excel_detailed.py
import pandas as pd
from pathlib import Path
import sys

def main():
    """Excelファイルの詳細な内容を確認"""
    
    candidates = [
        Path("data/Customer_Management_latest.xlsx"),
        Path("data/Customer_Management_values.xlsx"),
    ]
    
    excel_path = None
    for path in candidates:
        if path.exists():
            excel_path = path
            break
    
    if not excel_path:
        print("❌ Excelファイルが見つかりません")
        return 1
    
    print(f"📂 対象ファイル: {excel_path}\n")
    
    xl = pd.ExcelFile(excel_path)
    print(f"📋 シート一覧: {xl.sheet_names}\n")
    
    # 受注関連シートを探す
    order_sheets = [s for s in xl.sheet_names if "受注" in s or "order" in s.lower()]
    
    if not order_sheets:
        print("⚠️ 受注シートが見つかりません")
        return 1
    
    for sheet_name in order_sheets:
        print("=" * 60)
        print(f"📄 シート名: {sheet_name}")
        print("=" * 60)
        
        # 複数の読み込み方法を試す
        methods = [
            ("デフォルト", {}),
            ("dtype=str", {"dtype": str}),
            ("keep_default_na=False", {"dtype": str, "keep_default_na": False}),
        ]
        
        for method_name, kwargs in methods:
            print(f"\n🔍 読み込み方法: {method_name}")
            try:
                df = pd.read_excel(excel_path, sheet_name=sheet_name, **kwargs)
                
                # 空行削除前
                print(f"  削除前: {len(df)}行 x {len(df.columns)}列")
                
                # 空行削除
                if "keep_default_na" not in kwargs:
                    df = df.replace(r"^\s*$", pd.NA, regex=True)
                df_cleaned = df.dropna(how="all").dropna(axis=1, how="all")
                
                print(f"  削除後: {len(df_cleaned)}行 x {len(df_cleaned.columns)}列")
                print(f"  列名: {list(df_cleaned.columns)}")
                
                # invoice列があるか確認
                invoice_cols = [c for c in df_cleaned.columns if "invoice" in str(c).lower() or "受注" in str(c)]
                
                if invoice_cols:
                    col = invoice_cols[0]
                    print(f"\n  ✅ 受注番号列: '{col}'")
                    
                    # 文字列に変換して前後の空白を削除
                    invoices = df_cleaned[col].astype(str).str.strip().tolist()
                    
                    print(f"  📋 受注番号一覧（{len(invoices)}件）:")
                    for idx, inv in enumerate(invoices[:20], 1):  # 最初の20件のみ表示
                        print(f"    {idx}. '{inv}'")
                    
                    if len(invoices) > 20:
                        print(f"    ... (残り {len(invoices) - 20}件)")
                    
                    # TSE-IST-003-25 を検索
                    target = "TSE-IST-003-25"
                    if target in invoices:
                        print(f"\n  ✅✅✅ {target} が見つかりました！")
                        idx = invoices.index(target)
                        print(f"  行番号: {idx + 1}")
                        print(f"  データ:\n{df_cleaned.iloc[idx]}")
                    else:
                        print(f"\n  ❌ {target} が見つかりません")
                        # 類似の受注番号を検索
                        similar = [inv for inv in invoices if "TSE-IST-003" in inv]
                        if similar:
                            print(f"  🔍 類似番号: {similar}")
                
                else:
                    print(f"\n  ⚠️ 受注番号列が見つかりません")
                    print(f"  先頭3行:\n{df_cleaned.head(3)}")
                
            except Exception as e:
                print(f"  ❌ エラー: {e}")
        
        print("\n")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
