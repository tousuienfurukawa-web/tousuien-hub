#!/usr/bin/env python3
"""
slack_chat_command.py

Natural-language chat command wrapper to extract Slack conversations
by invoice ID (e.g., TSE-BGV-058-25) or free-text query.

Usage examples (run from repo root):
  # Japanese natural text with invoice ID
  python3 scripts/slack_chat_command.py "SlackからTSE-BGV-058-25のやり取りを出して"

  # Explicit free-text query
  python3 scripts/slack_chat_command.py --query "payment schedule"

Behavior:
- Finds a Slack export ZIP or directory automatically if not specified
  (checks env SLACK_ZIP / SLACK_DIR, otherwise picks the most recent
   ZIP file in the current directory matching '*Slack*export*.zip').
- Extracts one or more invoice IDs like TSE-XXX-XXX-XX from the input text.
- Prints Markdown to stdout (does not write files).

Tip:
- Set SLACK_TZ=Asia/Tokyo to override timezone (default Asia/Tokyo).
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from typing import List, Optional, Tuple

# Ensure repo root on import path so we can import the CLI module
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(REPO_ROOT)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    # Import the existing CLI module to reuse its main()
    from scripts import reconcile_invoice  # type: ignore
except Exception as e:  # pragma: no cover
    print(f"Failed to import scripts.reconcile_invoice: {e}", file=sys.stderr)
    sys.exit(2)


# Accept various hyphen/dash characters or spaces between parts
# Example matches: TSE-BGV-058-25, TSE–BGV–058–25, TSE BGV 058 25
INVOICE_RE = re.compile(
    r"TSE[\-–—－_ ]([A-Z0-9]{3})[\-–—－_ ](\d{3})[\-–—－_ ](\d{2})",
    re.IGNORECASE,
)


def extract_invoices(text: str) -> List[str]:
    matches = INVOICE_RE.finditer(text or "")
    unique: List[str] = []
    seen = set()
    for m in matches:
        part1, part2, part3 = m.group(1), m.group(2), m.group(3)
        val = f"TSE-{part1}-{part2}-{part3}".upper()
        if val not in seen:
            seen.add(val)
            unique.append(val)
    return unique


def auto_locate_slack_source(
    slack_zip: Optional[str], slack_dir: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    if slack_zip:
        return slack_zip, None
    if slack_dir:
        return None, slack_dir

    # Environment variables first
    env_zip = os.environ.get("SLACK_ZIP")
    env_dir = os.environ.get("SLACK_DIR")
    if env_zip and os.path.exists(env_zip):
        return env_zip, None
    if env_dir and os.path.isdir(env_dir):
        return None, env_dir

    # Heuristic: prefer most recent ZIP with "Slack" and "export"
    candidates = [
        *glob.glob("*Slack*export*.zip"),
        *glob.glob("*slack*export*.zip"),
        *glob.glob("*.zip"),  # last resort
    ]
    candidates = [p for p in candidates if os.path.isfile(p)]
    if candidates:
        candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return candidates[0], None

    # Fallback: common directories
    for d in ("data/slack_export", "slack_export", "data/Slack_export"):
        if os.path.isdir(d):
            return None, d

    return None, None


def run_for_text(
    text: str,
    slack_zip: Optional[str] = None,
    slack_dir: Optional[str] = None,
    tz: Optional[str] = None,
) -> int:
    invoices = extract_invoices(text)

    slack_zip, slack_dir = auto_locate_slack_source(slack_zip, slack_dir)
    if not slack_zip and not slack_dir:
        print("Could not find Slack export ZIP or directory. Set SLACK_ZIP or SLACK_DIR.", file=sys.stderr)
        return 2

    tz = tz or os.environ.get("SLACK_TZ") or "Asia/Tokyo"

    exit_code = 0
    if invoices:
        for inv in invoices:
            # Print a small header to separate multiple outputs
            print(f"## invoice: {inv}")
            code = reconcile_invoice.main([
                "--slack-zip", slack_zip,
                "--invoice", inv,
                "--format", "md",
                "--tz", tz,
                "--output", "/dev/stdout",
            ] if slack_zip else [
                "--slack-dir", slack_dir,
                "--invoice", inv,
                "--format", "md",
                "--tz", tz,
                "--output", "/dev/stdout",
            ])
            if code != 0:
                exit_code = code
    else:
        # Fallback to free-text query if no invoice found
        q = text.strip()
        if not q:
            print("No input text provided.", file=sys.stderr)
            return 2
        code = reconcile_invoice.main([
            "--slack-zip", slack_zip,
            "--query", q,
            "--format", "md",
            "--tz", tz,
            "--output", "/dev/stdout",
        ] if slack_zip else [
            "--slack-dir", slack_dir,
            "--query", q,
            "--format", "md",
            "--tz", tz,
            "--output", "/dev/stdout",
        ])
        exit_code = code

    return int(exit_code)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Chat-style command wrapper for Slack report extraction",
    )
    p.add_argument("text", nargs="?", help="Natural text containing invoice or query")
    p.add_argument("--query", help="Explicit fallback query if no invoice in text")
    p.add_argument("--slack-zip", dest="slack_zip", help="Path to Slack export ZIP")
    p.add_argument("--slack-dir", dest="slack_dir", help="Path to Slack export directory")
    p.add_argument("--tz", dest="tz", default=None, help="Timezone (default from SLACK_TZ or Asia/Tokyo)")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    text = args.text or args.query or ""
    if not text:
        print("Provide natural text or --query.", file=sys.stderr)
        return 2
    return run_for_text(text, slack_zip=args.slack_zip, slack_dir=args.slack_dir, tz=args.tz)


if __name__ == "__main__":
    raise SystemExit(main())
