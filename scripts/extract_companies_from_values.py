import argparse
import gzip
import os
from pathlib import Path
from typing import Iterable

import pandas as pd

DEFAULT_CANDIDATES: tuple[Path, ...] = (
    Path("Customer_Management_values.xlsx"),
    Path("data/Customer_Management_values.xlsx"),
    Path("Customer_Management_latest.xlsx"),
    Path("data/Customer_Management_latest.xlsx"),
)

OUTPUT_FILE = Path("dist/会社情報登録.csv.gz")


def resolve_input_path(explicit: Path | None, candidates: Iterable[Path]) -> Path | None:
    if explicit is not None:
        explicit = explicit.expanduser().resolve()
        if explicit.exists():
            return explicit
        print(f"❌ 指定した入力ファイルが見つかりません: {explicit}")
        return None

    for candidate in candidates:
        if candidate.exists():
            return candidate

    searched = ", ".join(str(path) for path in candidates)
    print("❌ 入力ファイルが見つかりません。以下の候補を確認してください:\n   " + searched)
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="'会社情報登録' シートを抽出して CSV（gzip）保存します。")
    parser.add_argument("--input", "-i", type=Path, help="入力 Excel ファイルのパス")
    parser.add_argument("--sheet", "-s", default="会社情報登録", help="抽出するシート名（default: 会社情報登録）")
    parser.add_argument("--output", "-o", type=Path, default=OUTPUT_FILE, help="出力ファイルパス")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = resolve_input_path(args.input, DEFAULT_CANDIDATES)
    if input_path is None:
        return

    try:
        xl = pd.ExcelFile(input_path)
    except FileNotFoundError:
        print(f"❌ 入力ファイルが見つかりません: {input_path}")
        return

    if args.sheet not in xl.sheet_names:
        print(f"❌ '{args.sheet}' シートが見つかりません。")
        return

    df = xl.parse(args.sheet, dtype=str).fillna("")
    os.makedirs(args.output.parent, exist_ok=True)

    with gzip.open(args.output, "wt", encoding="utf-8") as f:
        df.to_csv(f, index=False)

    print(f"✅ {args.output.name} を保存しました: {args.output}（入力: {input_path}）")


if __name__ == "__main__":
    main()
