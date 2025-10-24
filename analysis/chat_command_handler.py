# analysis/chat_command_handler.py
import re
from analysis.generate_sales_report import analyze_company


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
        return "⚠️ 企業コードが見つかりません（例: ILJ, MCG, RNI）"

    company_code = code_match.group(1)
    target_year = int(year_match.group(1)) if year_match else None

    print(f"🎯 実行対象: {company_code}, 年={target_year or '全期間'}")

    monthly, detail = analyze_company(company_code)
    if detail is None:
        return f"⚠️ 企業コード「{company_code}」のデータが見つかりません。"

    # 年で絞り込み
    if target_year:
        import pandas as pd
        detail["注文日"] = pd.to_datetime(detail["注文日"], errors="coerce")
        detail = detail[detail["注文日"].dt.year == target_year]

    # テーブル文字列化（上位10件のみ）
    preview = detail.head(10).to_string(index=False)

    result_text = (
        f"📊 **{company_code} の {target_year or '全期間'} の注文一覧（上位10件）**\n\n"
        f"```\n{preview}\n```"
    )

    return result_text


if __name__ == "__main__":
    # 動作テスト
    print(handle_chat_command("RNIの2025注文一覧"))
    print(handle_chat_command("ILJの注文履歴"))
