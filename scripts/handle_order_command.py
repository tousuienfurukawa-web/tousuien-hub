# scripts/handle_order_command.py
import pandas as pd
import argparse
from pathlib import Path

def _load_orders() -> pd.DataFrame:
    """dist フォルダ内の受注登録データを動的に読み込み"""
    dist = Path("dist")
    preferred = [dist / "受注登録.csv.gz", dist / "受注登録.csv"]
    for path in preferred:
        if path.exists():
            compression = "gzip" if path.suffix == ".gz" else None
            return pd.read_csv(path, compression=compression, dtype=str)

    raise FileNotFoundError("❌ 受注登録データが見つかりません（dist/受注登録.csv(.gz)）")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--invoice", type=str, required=True)
    args = parser.parse_args()
    
    df = _load_orders()
    row = df[df["invoice"] == args.invoice]
    
    if row.empty:
        print(f"❌ 該当受注番号が見つかりません: {args.invoice}")
        return

    print(f"🧾 受注情報（{args.invoice}）:")
    print(row.to_string(index=False))

if __name__ == "__main__":
    main()
