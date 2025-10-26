# scripts/handle_order_command.py
import pandas as pd
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--invoice", type=str, required=True)
    args = parser.parse_args()
    
    df = pd.read_csv("dist/受注登録.csv.gz", compression="gzip", dtype=str)
    row = df[df["invoice"] == args.invoice]
    if row.empty:
        print(f"❌ 該当受注番号が見つかりません: {args.invoice}")
        return

    print(f"🧾 受注情報（{args.invoice}）:")
    print(row.to_string(index=False))

if __name__ == "__main__":
    main()
