import pandas as pd
import os

# 入力ファイルと出力ファイルのパス
INPUT_XLSX = "Customer_Management_values.xlsx"
OUTPUT_CSV = "dist/受注登録.csv.gz"

# 出力ディレクトリ作成
os.makedirs("dist", exist_ok=True)

def main():
    # Excelファイルから全シート読み込み
    xls = pd.ExcelFile(INPUT_XLSX)

    # "受注登録" タブの読み込み（存在チェック含む）
    if "受注登録" not in xls.sheet_names:
        raise ValueError("Excelファイルに '受注登録' シートが存在しません。")

    df = xls.parse("受注登録", dtype=str)

    # 欠損値の補完
    df.fillna("", inplace=True)

    # 保存
    df.to_csv(OUTPUT_CSV, index=False, compression="gzip")
    print(f"✅ 受注登録.csv.gz を作成しました: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
