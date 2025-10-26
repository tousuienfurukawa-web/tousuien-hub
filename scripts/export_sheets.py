# scripts/export_sheets.py
import sys
from pathlib import Path
import pandas as pd
import json

def export_sheets(values_xlsx: Path, outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    xls = pd.ExcelFile(values_xlsx, engine='openpyxl')
    manifest = {"sheets":{}, "generated_at": None}
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet, engine='openpyxl', dtype=object)
        df = df.dropna(axis=0, how='all').dropna(axis=1, how='all')
        safe_name = sheet[:50].replace(" ", "_")
        csv_path = outdir / f"{safe_name}.csv.gz"
        df.to_csv(csv_path, index=False, compression='gzip')
        pq_path = None
        try:
            pq_path = str(outdir / f"{safe_name}.parquet")
            df.to_parquet(pq_path, engine='pyarrow', compression='snappy')
        except Exception:
            pq_path = None
        manifest["sheets"][sheet] = {
            "csv": str(csv_path.name),
            "parquet": Path(pq_path).name if pq_path else None,
            "rows": int(df.shape[0]),
            "cols": int(df.shape[1])
        }
    import datetime
    manifest["generated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    with open(outdir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("exported sheets to", outdir)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/export_sheets.py <values.xlsx> <outdir>")
        sys.exit(1)
    export_sheets(Path(sys.argv[1]), Path(sys.argv[2]))
