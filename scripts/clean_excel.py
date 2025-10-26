# scripts/clean_excel.py
"""
Create a "values-only" Excel workbook from a source workbook.

This utility:
 - reads every sheet from the source workbook,
 - drops completely empty rows and columns,
 - rounds float columns (optional precision),
 - writes the cleaned data to a new workbook without carrying over
   Excel-specific formatting, images, or formulas.

Usage:
    python scripts/clean_excel.py <src.xlsx> <out_values.xlsx>
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


def clean_workbook(src: Path, out: Path, float_round: int | None = 4) -> None:
    """
    Read all sheets from `src` and write a 'values-only' workbook to `out`.
    `float_round` controls rounding of float columns (None = no rounding).
    """
    src = Path(src)
    out = Path(out)

    if not src.exists():
        raise FileNotFoundError(f"Source workbook not found: {src}")

    xls = pd.ExcelFile(src, engine="openpyxl")
    # Attempt to pass xlsxwriter options via engine_kwargs; provide fallback for older pandas.
    try:
        writer_ctx = pd.ExcelWriter(
            out,
            engine="xlsxwriter",
            engine_kwargs={"options": {"strings_to_urls": False}},
        )
    except TypeError:
        # Fallback for older pandas versions that don't accept engine_kwargs
        writer_ctx = pd.ExcelWriter(out, engine="xlsxwriter")

    with writer_ctx as writer:
        for sheet in xls.sheet_names:
            # Read with openpyxl to ensure compatibility with modern .xlsx features.
            try:
                df = pd.read_excel(xls, sheet_name=sheet, engine="openpyxl", dtype=object)
            except Exception as e:
                print(f"⚠️  Failed to read sheet '{sheet}': {e}", file=sys.stderr)
                # Skip this sheet on error and continue with others
                continue

            # Drop completely empty rows/columns
            df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")

            # Optional: round float columns to reduce size / noise
            if float_round is not None:
                for col in df.select_dtypes(include=["float"]).columns:
                    df[col] = df[col].round(float_round)

            # Excel sheet names max length is 31
            safe_sheet = sheet[:31]
            try:
                df.to_excel(writer, sheet_name=safe_sheet, index=False)
            except Exception as e:
                # If writing fails for a sheet, report and continue
                print(f"⚠️  Failed to write sheet '{sheet}' to output: {e}", file=sys.stderr)
                continue

    print(f"values workbook written: {out}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("src", type=Path, help="Source Excel workbook (xlsx/xlsm).")
    p.add_argument("out", type=Path, help="Output values-only workbook path.")
    p.add_argument(
        "--float-round",
        type=int,
        default=4,
        help="Number of decimal places to round float columns to (default: 4). "
        "Set to 0 or None to disable rounding.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    float_round = args.float_round if args.float_round is not None else 4
    # Allow disabling rounding with --float-round  None is not directly passable by CLI, but user can set 0 to
    # effectively round to integer. Keep default 4 for size/precision balance.
    try:
        clean_workbook(args.src, args.out, float_round=float_round)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
