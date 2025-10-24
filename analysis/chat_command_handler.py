# analysis/chat_command_handler.py
import re
from analysis.generate_sales_report import analyze_company
import pandas as pd


def handle_chat_command(command: str):
    """
    ユーザー入力を解析し、適切な処理を実行する。
    例:
        "RNIの2025注文一覧" → analyze_company("RNI") + 年度フィルタ
    """

    # 正規表現で企業コードと年を抽出
    code_match = re.search(r"([A-Z]{3})", command)
    year_match = re.search(r"(20\d{2})", command)

    if not code_match:
        return {"error": "⚠️ 企業コードが見つかりません（例: ILJ, MCG, RNI）"}

    company_code = code_match.group(1)
    target_year = int(year_match.group(1)) if year_match else None

    print(f"🎯 実行対象: {company_code}, 年={target_year or '全期間'}")

    # 売上データ分析を実行
    monthly, detail = analyze_company(company_code)
    if detail is None or len(detail) == 0:
        return {"error": f"⚠️ 企業コード「{company_code}」のデータが見つかりません。"}

    # 年で絞り込み（任意）
    if target_year:
        detail["注文日"] = pd.to_datetime(detail["注文日"], errors="coerce")
        detail = detail[detail["注文日"].dt.year == target_year]

    # 上位10件のみ（dict形式でAPIレスポンス化）
    preview = detail.head(10).to_dict(orient="records")

    # レスポンスJSON構造
    return {
        "company_code": company_code,
        "year": target_year or "全期間",
        "total_records": len(detail),
        "records": preview
    }


if __name__ == "__main__":
    # 動作テスト
    print(handle_chat_command("RNIの2025注文一覧"))
    print(handle_chat_command("ILJの注文履歴"))
