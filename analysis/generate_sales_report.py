# analysis/generate_sales_report.py
import pandas as pd
from pathlib import Path

# ====== 設定 ======
DATA_PATH = Path("data/Customer Management_latest.xlsx")
SHEET_NAME = "受注登録"
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)

# ------------------------------------------------------------
# 🌍 ① 全体の月次売上レポート生成
# ------------------------------------------------------------
def generate_sales_report(show_summary=True):
    """受注登録タブから通貨別・顧客別売上レポートを生成"""
    df = pd.read_excel(DATA_PATH, sheet_name=SHEET_NAME)

    # 必要列の確認
    required_cols = ["宛名", "通貨", "商品代＋送料", "注文日", "オーダー\nステータス"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"⚠️ 列 '{col}' が存在しません。Excelを確認してください。")

    # データ整形
    df["注文日"] = pd.to_datetime(df["注文日"], errors="coerce")
    df["年月"] = df["注文日"].dt.to_period("M")
    df = df[df["オーダー\nステータス"] != "CANCELED"]
    df["売上金額"] = pd.to_numeric(df["商品代＋送料"], errors="coerce").fillna(0)

    # 集計
    summary = (
        df.groupby(["通貨", "年月", "宛名"])["売上金額"]
        .sum()
        .reset_index()
        .sort_values(["通貨", "年月", "売上金額"], ascending=[True, False, False])
    )

    monthly_summary = (
        df.groupby(["通貨", "年月"])["売上金額"]
        .sum()
        .reset_index()
        .sort_values(["通貨", "年月"], ascending=[True, False])
    )

    # 出力
    output_file = REPORTS_DIR / "sales_report_summary.xlsx"
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="顧客別売上", index=False)
        monthly_summary.to_excel(writer, sheet_name="月次売上", index=False)

    print(f"✅ 通貨別・顧客別売上レポートを生成しました：{output_file}")

    if show_summary:
        print("\n===== 月次サマリー（上位10件） =====")
        print(monthly_summary.head(10).to_string(index=False))

    return monthly_summary.head(10)


# ------------------------------------------------------------
# 🏢 ② 企業コードごとの分析関数（ILJ / MCGなど）
# ------------------------------------------------------------
def analyze_company(company_code: str):
    """特定企業コードの受注履歴・月次推移を返す"""
    df = pd.read_excel(DATA_PATH, sheet_name=SHEET_NAME)

    # 対象企業抽出
    df = df[df["企業コード"] == company_code]
    if df.empty:
        print(f"⚠️ 指定した企業コード '{company_code}' のデータが見つかりません。")
        return None, None

    # 整形
    df["注文日"] = pd.to_datetime(df["注文日"], errors="coerce")
    df["年月"] = df["注文日"].dt.to_period("M")
    df["商品代＋送料"] = pd.to_numeric(df["商品代＋送料"], errors="coerce").fillna(0)

    # 月次集計
    monthly_summary = (
        df.groupby(["年月", "通貨"])["商品代＋送料"]
        .sum()
        .reset_index()
        .rename(columns={"商品代＋送料": "売上金額"})
        .sort_values(["年月", "通貨"])
    )

    # 詳細リスト（invoice別）
    details = (
        df.loc[:, ["invoice", "注文日", "通貨", "商品代＋送料",
                   "オーダー\nステータス", "宛名", "担当者名"]]
        .sort_values("注文日")
        .reset_index(drop=True)
    )

    print(f"✅ 企業コード {company_code} のデータを抽出しました。")
    print(f"・受注件数：{len(details)}")
    print(f"・取引通貨：{', '.join(sorted(df['通貨'].dropna().unique()))}")

    return monthly_summary, details


# ------------------------------------------------------------
# 🚀 ③ 実行部分（ChatGPT / CLI / GitHub Actions対応）
# ------------------------------------------------------------
if __name__ == "__main__":
    # 🔹 通常実行：全体レポートを作成
    generate_sales_report(show_summary=True)

    # 🔹 個別分析（例：ILJやMCG）
    # monthly, detail = analyze_company("ILJ")
    # print(monthly)
    # print(detail.head())
