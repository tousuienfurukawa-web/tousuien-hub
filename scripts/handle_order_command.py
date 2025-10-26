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

def main():
    parser = argparse.ArgumentParser(description="受注番号から受注情報を検索")
    parser.add_argument("--invoice", "-i", type=str, required=True, help="受注番号 (例: TSE-IST-003-25)")
    args = parser.parse_args()

    try:
        df = _load_orders()
        print(f"✅ {len(df)}件の受注データを読み込みました")
        print(f"🔍 検索中: {args.invoice}\n")
        
        # 受注番号で検索
        row = df[df["invoice"] == args.invoice]
        
        if row.empty:
            print(f"❌ 該当受注番号が見つかりません: {args.invoice}")
            print(f"\n📋 登録されている受注番号一覧:")
            for inv in df["invoice"].unique():
                print(f"  - {inv}")
            return
        
        print(f"🧾 受注情報（{args.invoice}）:")
        print(row.to_string(index=False))
        
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        raise

if __name__ == "__main__":
    main()
