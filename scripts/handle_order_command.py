# scripts/handle_order_command.py
import pandas as pd
import argparse
from pathlib import Path

def _load_orders() -> pd.DataFrame:
    """受注登録データを動的に読み込み（.csv / .csv.gz 両対応）"""
    dist = Path("dist")
    
    # 優先順位: .csv → .csv.gz の順で探す
    candidates = [
        dist / "受注登録.csv",
        dist / "受注登録.csv.gz"
    ]
    
    for path in candidates:
        if path.exists():
            compression = "gzip" if path.suffix == ".gz" else None
            print(f"📂 読み込み中: {path}")
            return pd.read_csv(path, compression=compression, dtype=str)
    
    # どちらも見つからない場合
    raise FileNotFoundError(
        f"❌ 受注登録ファイルが見つかりません。\n"
        f"確認場所: {dist.absolute()}\n"
        f"期待ファイル: 受注登録.csv または 受注登録.csv.gz"
    )

def _load_companies() -> pd.DataFrame:
    """会社情報登録データを読み込み（オプション）"""
    dist = Path("dist")
    candidates = [
        dist / "会社情報登録.csv",
        dist / "会社情報登録.csv.gz"
    ]
    
    for path in candidates:
        if path.exists():
            compression = "gzip" if path.suffix == ".gz" else None
            return pd.read_csv(path, compression=compression, dtype=str)
    
    return None

def list_all_invoices(df: pd.DataFrame):
    """登録されている全受注番号を表示"""
    print("\n📋 登録済み受注番号一覧:")
    for idx, inv in enumerate(df["invoice"].unique(), 1):
        row = df[df["invoice"] == inv].iloc[0]
        status = row.get("status", "不明")
        company = row.get("company_code", "不明")
        print(f"  {idx}. {inv} (会社: {company}, ステータス: {status})")

def main():
    parser = argparse.ArgumentParser(description="受注番号から受注情報を検索")
    parser.add_argument("--invoice", "-i", type=str, help="受注番号 (例: TSE-IST-003-24)")
    parser.add_argument("--list", "-l", action="store_true", help="全受注番号を一覧表示")
    args = parser.parse_args()

    try:
        df = _load_orders()
        print(f"✅ {len(df)}件の受注データを読み込みました")
        
        # 一覧表示モード
        if args.list:
            list_all_invoices(df)
            return
        
        # 受注番号が指定されていない場合
        if not args.invoice:
            print("\n⚠️ 受注番号が指定されていません。")
            list_all_invoices(df)
            print("\n使い方: python scripts/handle_order_command.py --invoice TSE-IST-003-24")
            return
        
        print(f"🔍 検索中: {args.invoice}\n")
        
        # 受注番号で検索
        row = df[df["invoice"] == args.invoice]
        
        if row.empty:
            print(f"❌ 該当受注番号が見つかりません: {args.invoice}")
            list_all_invoices(df)
            return
        
        print(f"🧾 受注情報（{args.invoice}）:")
        print(row.to_string(index=False))
        
        # 会社情報も表示（オプション）
        if "company_code" in row.columns:
            companies = _load_companies()
            if companies is not None:
                comp_code = row.iloc[0]["company_code"]
                company = companies[companies["company_code"] == comp_code]
                if not company.empty:
                    print(f"\n🏢 会社情報（{comp_code}）:")
                    print(company.to_string(index=False))
        
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        raise

if __name__ == "__main__":
    main()
