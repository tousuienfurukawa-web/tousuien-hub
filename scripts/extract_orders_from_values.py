import pandas as pd
import os

# 入力ファイルパスと出力先ディレクトリ
INPUT_FILE = "Customer_Management_values.xlsx"
OUTPUT_DIR = "dist"
OUTPUT_FILE = "受注登録.csv.gz"

# 出力先ディレクトリを作成（存在しない場合）
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Excelファイルの読み込み（"受注登録" シート想定）
try:
    df = pd.read_excel(INPUT_FILE, sheet_name="受注登録", dtype=str)
except Exception as e:
    raise RuntimeError(f"Excelファイルの読み込み中にエラーが発生しました: {e}")

# データ整形（不要であれば削除可）
df = df.dropna(how="all")  # 完全に空の行を削除
df.columns = df.columns.str.strip()  # 列名の前後の空白除去

# 保存（gzip圧縮）
output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
df.to_csv(output_path, index=False, compression="gzip", encoding="utf-8-sig")

print(f"✅ 保存完了: {output_path}（{len(df)} 行）")
