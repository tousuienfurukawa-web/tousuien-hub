#!/usr/bin/env python3
import argparse
import csv
import io
import json
import re
import sys
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import openpyxl
except ImportError:  # pragma: no cover
    openpyxl = None


@dataclass
class SlackMessage:
    ts: str
    user: Optional[str]
    text: str
    channel: str
    thread_ts: Optional[str]
    permalink: Optional[str]
    dt: Optional[datetime]


INVOICE_PATTERN_TEMPLATE = r"(?i)\b{invoice}\b"


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconcile invoice against Slack export and Excel customer sheet, output Markdown report."
    )
    parser.add_argument("--excel", required=True, help="Path to Excel file (e.g., Customer Management_latest.xlsx)")
    parser.add_argument("--slack-zip", required=True, help="Path to Slack export ZIP")
    parser.add_argument("--invoice", required=True, help="Invoice ID to reconcile (e.g., TSE-BGV-058-25)")
    parser.add_argument("--format", default="md", choices=["md", "json"], help="Output format")
    parser.add_argument("--out-file", default="", help="Path to save output file. If empty, prints to stdout")
    parser.add_argument("--excel-sheet", default=None, help="Excel sheet name to read (default: first sheet)")
    parser.add_argument("--excel-id-column", default="InvoiceID", help="Excel column name for invoice id")
    parser.add_argument("--excel-customer-column", default="Customer", help="Excel column name for customer")
    parser.add_argument("--excel-amount-column", default="Amount", help="Excel column name for amount")
    parser.add_argument("--excel-status-column", default="Status", help="Excel column name for status")
    parser.add_argument("--slack-threads-only", action="store_true", help="Restrict to thread messages containing invoice id")
    return parser.parse_args(argv)


def read_excel_records(
    excel_path: Path,
    sheet_name: Optional[str],
) -> Tuple[List[str], List[Dict[str, str]]]:
    if openpyxl is None:
        raise RuntimeError("openpyxl is required. Please install dependencies from requirements.txt")

    wb = openpyxl.load_workbook(str(excel_path), data_only=True)
    ws = wb[sheet_name] if sheet_name else wb.active

    headers: List[str] = []
    rows: List[Dict[str, str]] = []

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            headers = [str(h).strip() if h is not None else "" for h in row]
            continue
        record: Dict[str, str] = {}
        for h, v in zip(headers, row):
            if not h:
                continue
            record[h] = "" if v is None else str(v)
        # skip empty rows
        if any(v for v in record.values()):
            rows.append(record)
    return headers, rows


def normalize_text(t: str) -> str:
    # Slack export may include entities; simplify for matching
    return (t or "").replace("\u00a0", " ").strip()


def parse_slack_export_zip(zip_path: Path) -> List[SlackMessage]:
    messages: List[SlackMessage] = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        # Try to read users and channels metadata if present
        user_id_to_name: Dict[str, str] = {}
        channel_dir_names: List[str] = []

        # Build lists of JSON paths inside ZIP
        for name in zf.namelist():
            if name.endswith("users.json"):
                try:
                    with zf.open(name) as fp:
                        user_id_to_name = {u.get("id", ""): u.get("real_name", u.get("name", "")) for u in json.load(fp)}
                except Exception:
                    user_id_to_name = {}
            elif name.endswith("channels.json"):
                # Not strictly needed
                pass
            elif "/" in name and name.endswith(".json") and not name.endswith("users.json"):
                # a channel directory like "general/2025-01-01.json"
                channel_dir_names.append(name)

        for name in channel_dir_names:
            try:
                channel = name.split("/")[0]
                with zf.open(name) as fp:
                    day_msgs = json.load(fp)
                for m in day_msgs:
                    ts = m.get("ts") or ""
                    user = m.get("user") or m.get("username")
                    if user and user_id_to_name.get(user):
                        user = user_id_to_name[user]
                    text = normalize_text(m.get("text") or "")
                    thread_ts = m.get("thread_ts") or None
                    permalink = None  # Slack export may not include; kept for future
                    dt = None
                    try:
                        if ts:
                            # ts is like "1644859942.1234"
                            seconds = float(ts.split(".")[0])
                            dt = datetime.fromtimestamp(seconds)
                    except Exception:
                        dt = None
                    messages.append(
                        SlackMessage(ts=ts, user=user, text=text, channel=channel, thread_ts=thread_ts, permalink=permalink, dt=dt)
                    )
            except Exception:
                # Skip malformed files
                continue
    return messages


def find_invoice_references(messages: List[SlackMessage], invoice_id: str) -> Tuple[List[SlackMessage], Dict[str, List[SlackMessage]]]:
    pattern = re.compile(INVOICE_PATTERN_TEMPLATE.format(invoice=re.escape(invoice_id)))
    hits: List[SlackMessage] = []
    thread_groups: Dict[str, List[SlackMessage]] = defaultdict(list)

    for m in messages:
        if pattern.search(m.text or ""):
            hits.append(m)
            if m.thread_ts:
                thread_groups[m.thread_ts].append(m)
            elif m.ts:
                # If no thread, treat message ts as its own thread id for grouping
                thread_groups[m.ts].append(m)

    # Enrich groups with context: include other messages from same thread/channel day file
    # For simplicity, we only include messages already in hits; full context could be added later
    return hits, thread_groups


def build_report_md(
    invoice_id: str,
    excel_headers: List[str],
    excel_rows: List[Dict[str, str]],
    excel_keys: Tuple[str, str, str, str],
    hits: List[SlackMessage],
    thread_groups: Dict[str, List[SlackMessage]],
) -> str:
    id_col, cust_col, amt_col, status_col = excel_keys

    # Excel match(es)
    excel_matches = [r for r in excel_rows if str(r.get(id_col, "")).strip() == invoice_id]

    buf: List[str] = []
    buf.append(f"# Reconciliation Report: {invoice_id}")
    buf.append("")
    buf.append("## Excel")
    if not excel_matches:
        buf.append("- No matching rows found in Excel")
    else:
        buf.append("| InvoiceID | Customer | Amount | Status |")
        buf.append("|---|---:|---:|---|")
        for r in excel_matches:
            buf.append(
                f"| {r.get(id_col,'')} | {r.get(cust_col,'')} | {r.get(amt_col,'')} | {r.get(status_col,'')} |"
            )

    buf.append("")
    buf.append("## Slack hits")
    if not hits:
        buf.append("- No Slack messages referencing this invoice ID")
    else:
        # Show grouped by thread (best-effort)
        for thread_id, group_msgs in thread_groups.items():
            group_sorted = sorted(group_msgs, key=lambda m: (m.dt or datetime.min))
            buf.append(f"### Thread {thread_id}")
            for m in group_sorted:
                ts_str = m.dt.isoformat(sep=" ") if m.dt else m.ts
                user = m.user or "unknown"
                preview = m.text.replace("\n", " ")
                if len(preview) > 120:
                    preview = preview[:117] + "..."
                buf.append(f"- [{ts_str}] {user} in #{m.channel}: {preview}")
            buf.append("")

    buf.append("---")
    buf.append("Note: Slack export ZIP parsing is best-effort; links may be unavailable in exports.")
    return "\n".join(buf)


def build_report_json(
    invoice_id: str,
    excel_headers: List[str],
    excel_rows: List[Dict[str, str]],
    excel_keys: Tuple[str, str, str, str],
    hits: List[SlackMessage],
    thread_groups: Dict[str, List[SlackMessage]],
) -> str:
    id_col, cust_col, amt_col, status_col = excel_keys
    excel_matches = [r for r in excel_rows if str(r.get(id_col, "")).strip() == invoice_id]
    payload = {
        "invoice": invoice_id,
        "excel_matches": excel_matches,
        "slack_hits": [m.__dict__ for m in hits],
        "thread_groups": {k: [m.__dict__ for m in v] for k, v in thread_groups.items()},
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    excel_path = Path(args.excel)
    slack_zip_path = Path(args.slack_zip)
    invoice_id = args.invoice.strip()

    if not excel_path.exists():
        print(f"ERROR: Excel not found: {excel_path}", file=sys.stderr)
        return 2
    if not slack_zip_path.exists():
        print(f"ERROR: Slack ZIP not found: {slack_zip_path}", file=sys.stderr)
        return 2

    excel_headers, excel_rows = read_excel_records(excel_path, args.excel_sheet)

    excel_keys = (
        args.excel_id_column,
        args.excel_customer_column,
        args.excel_amount_column,
        args.excel_status_column,
    )
    for key in excel_keys:
        if key not in excel_headers:
            print(
                f"WARNING: Column '{key}' not found in Excel headers: {excel_headers}",
                file=sys.stderr,
            )

    messages = parse_slack_export_zip(slack_zip_path)
    hits, thread_groups = find_invoice_references(messages, invoice_id)

    if args.format == "md":
        out = build_report_md(invoice_id, excel_headers, excel_rows, excel_keys, hits, thread_groups)
    else:
        out = build_report_json(invoice_id, excel_headers, excel_rows, excel_keys, hits, thread_groups)

    if args.out_file:
        out_path = Path(args.out_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out, encoding="utf-8")
    else:
        print(out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
