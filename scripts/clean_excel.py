# scripts/clean_excel.py
import sys
from pathlib import Path
import pandas as pd

def clean_workbook(src: Path, out: Path):
    xls = pd.ExcelFile(src, engine="openpyxl")
    with pd.ExcelWriter(out, engine="xlsxwriter", options={'strings_to_urls': False}) as writer:
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet, engine="openpyxl", dtype=object)
            # 完全空行/空列を削除
            df = df.dropna(axis=0, how='all').dropna(axis=1, how='all')
            # 数値の丸め（必要なら調整）
            for col in df.select_dtypes(include=['float']).columns:
                df[col] = df[col].round(4)
            safe_sheet = sheet[:31]
            df.to_excel(writer, sheet_name=safe_sheet, index=False)
    print(f"values workbook written: {out}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/clean_excel.py <src.xlsx> <out_values.xlsx>")
        sys.exit(1)
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    clean_workbook(src, out)
