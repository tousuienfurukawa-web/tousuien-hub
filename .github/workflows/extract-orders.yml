import pandas as pd
import os
import gzip

INPUT_FILE = "Customer_Management_values.xlsx"
OUTPUT_FILE = "dist/受注登録.csv.gz"

def main():
    # Excelファイルを読み込み
    try:
        xl = pd.ExcelFile(INPUT_FILE)
    except FileNotFoundError:
        print(f"❌ 入力ファイルが見つかりません: {INPUT_FILE}")
        return

    # 「受注登録」シートを読み込み
    if "受注登録" not in xl.sheet_names:
        print("❌ '受注登録' シートが見つかりません。")
        return

    df = xl.parse("受注登録", dtype=str).fillna("")

    # dist フォルダがなければ作成
    os.makedirs("dist", exist_ok=True)

    # 圧縮して保存
    with gzip.open(OUTPUT_FILE, 'wt', encoding='utf-8') as f:
        df.to_csv(f, index=False)
    
    print(f"✅ 受注登録.csv.gz を保存しました: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
