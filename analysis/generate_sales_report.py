# analysis/generate_sales_report.py

import pandas as pd
from pathlib import Path

# ====== 設定 ======
DATA_PATH = Path("data/Customer Management_latest.xlsx")
SHEET_NAME = "受注登録"  # Excelの受注登録タブの正式名称に合わせて変更
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)

def generate_sales_report():
    """受注登録タブから売上レポートを生成"""
    df = pd.read_excel(DATA_PATH, sheet_name=SHEET_NAME)

    # 必要列のチェック（足りない場合はエラー表示）
    required_cols = ["受注日", "顧客名", "商品名", "数量", "単価"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"⚠️ 列 '{col}' が存在しません。Excelタブを確認してください。")

    # 売上金額計算
    df["金額"] = df["数量"] * df["単価"]

    # 月次・顧客別売上集計
    df["年月"] = pd.to_datetime(df["受注日"]).dt.to_period("M")
    report = df.groupby(["年月", "顧客名"])["金額"].sum().reset_index()
    report = report.sort_values(["年月", "金額"], ascending=[False, False])

    # 出力
    output_file = REPORTS_DIR / "monthly_sales_report.xlsx"
    report.to_excel(output_file, index=False)
    print(f"✅ 売上レポートを生成しました：{output_file}")

    return output_file


if __name__ == "__main__":
    generate_sales_report()
