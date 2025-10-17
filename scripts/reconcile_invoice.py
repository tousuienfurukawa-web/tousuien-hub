#!/usr/bin/env python3
"""
reconcile_invoice.py

CLI to extract Slack threads from an export (ZIP or directory),
searching by invoice ID or free-text query, and output a Markdown report.

Key features:
- Load Slack export from a ZIP file or directory
- Parse users to resolve display names and emails
- Search messages by substring (invoice or query), case-insensitive
- Group entire threads (root + replies) via thread_ts
- Format Markdown, marking company users with a green dot (🟢)
- Write to reports/<name>.md or stdout

Examples:
  python scripts/reconcile_invoice.py \
    --slack-zip "海外 Slack export Feb 17 2022 - Oct 16 2025.zip" \
    --invoice "TSE-BGV-058-25" \
    --format md \
    --company-domains tousuien.co.jp \
    --output reports/TSE-BGV-058-25.md

  python scripts/reconcile_invoice.py \
    --slack-dir /data/slack_export \
    --query "payment schedule" \
    --format md

Notes:
- If both --invoice and --query are provided, both are applied (logical AND).
- If neither is provided, all threads are returned (not recommended unless filtered by --channel).
- By default, timestamps are rendered in local time. Use --tz to specify e.g. Asia/Tokyo.
"""
from __future__ import annotations

import argparse
import dataclasses
import html
import io
import json
import os
import re
import sys
import textwrap
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple, Union

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

import zipfile


@dataclass
class SlackUser:
    user_id: str
    username: Optional[str]
    display_name: Optional[str]
    real_name: Optional[str]
    email: Optional[str]

    def best_name(self) -> str:
        if self.display_name:
            return self.display_name
        if self.real_name:
            return self.real_name
        if self.username:
            return self.username
        return self.user_id


@dataclass
class SlackMessage:
    channel: str
    ts: str  # original string timestamp like "1695558321.000000"
    text: str
    user_id: Optional[str] = None
    user_display: Optional[str] = None  # fallback from message.user_profile.username
    thread_ts: Optional[str] = None
    subtype: Optional[str] = None
    is_bot: bool = False

    def thread_key(self) -> str:
        return self.thread_ts or self.ts

    def ts_float(self) -> float:
        # Slack ts is a string like "1695558321.000000" -> float seconds
        try:
            return float(self.ts)
        except Exception:
            # fallback if format unexpected
            parts = self.ts.split(".")
            if parts and parts[0].isdigit():
                return float(parts[0])
            return 0.0


# -------------- Slack export loading --------------


def _iter_zip_json_files(zf: zipfile.ZipFile) -> Iterable[Tuple[str, str]]:
    """Yield (path_in_zip, json_text) for all JSON files in ZIP.
    Skips macOS metadata and non-JSON files.
    """
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = info.filename
        # Slack exports are typically UTF-8 paths; guard weird entries
        if not name.lower().endswith(".json"):
            continue
        # skip root meta we don't need here; we still read users.json separately when needed
        with zf.open(info, "r") as fp:
            try:
                data = fp.read()
                text = data.decode("utf-8", errors="replace")
            except Exception:
                continue
        yield name, text


def _read_zip_file_text(zf: zipfile.ZipFile, member: str) -> Optional[str]:
    try:
        with zf.open(member, "r") as fp:
            return fp.read().decode("utf-8", errors="replace")
    except KeyError:
        return None


def load_users(slack_zip: Optional[str], slack_dir: Optional[str]) -> Dict[str, SlackUser]:
    users: Dict[str, SlackUser] = {}
    if slack_zip:
        with zipfile.ZipFile(slack_zip) as zf:
            text = _read_zip_file_text(zf, "users.json")
            if text is None:
                # some exports nest metadata under a folder; find it
                for name, content in _iter_zip_json_files(zf):
                    if name.endswith("/users.json"):
                        text = content
                        break
            if text:
                raw = json.loads(text)
                for u in raw:
                    profile = u.get("profile") or {}
                    users[u.get("id") or "UNKNOWN"] = SlackUser(
                        user_id=u.get("id") or "UNKNOWN",
                        username=u.get("name"),
                        display_name=profile.get("display_name") or profile.get("display_name_normalized"),
                        real_name=profile.get("real_name") or profile.get("real_name_normalized"),
                        email=profile.get("email"),
                    )
                return users
    if slack_dir:
        users_path = os.path.join(slack_dir, "users.json")
        if os.path.exists(users_path):
            with open(users_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for u in raw:
                profile = u.get("profile") or {}
                users[u.get("id") or "UNKNOWN"] = SlackUser(
                    user_id=u.get("id") or "UNKNOWN",
                    username=u.get("name"),
                    display_name=profile.get("display_name") or profile.get("display_name_normalized"),
                    real_name=profile.get("real_name") or profile.get("real_name_normalized"),
                    email=profile.get("email"),
                )
            return users
    return users


def load_messages(slack_zip: Optional[str], slack_dir: Optional[str]) -> List[SlackMessage]:
    messages: List[SlackMessage] = []

    def read_channel_day(channel: str, text: str) -> None:
        try:
            day_msgs = json.loads(text)
        except Exception:
            return
        if not isinstance(day_msgs, list):
            return
        for m in day_msgs:
            # Skip join/leave and other system subtypes unless they carry text
            subtype = m.get("subtype")
            user_id = m.get("user")
            is_bot = bool(m.get("bot_id") or subtype == "bot_message")
            user_profile = m.get("user_profile") or {}
            user_display = user_profile.get("display_name") or user_profile.get("name")
            text_val = m.get("text") or ""
            ts_val = m.get("ts") or "0"
            thread_ts = m.get("thread_ts")

            messages.append(
                SlackMessage(
                    channel=channel,
                    ts=str(ts_val),
                    text=str(text_val),
                    user_id=str(user_id) if user_id else None,
                    user_display=str(user_display) if user_display else None,
                    thread_ts=str(thread_ts) if thread_ts else None,
                    subtype=str(subtype) if subtype else None,
                    is_bot=is_bot,
                )
            )

    if slack_zip:
        with zipfile.ZipFile(slack_zip) as zf:
            for name, text in _iter_zip_json_files(zf):
                base = os.path.basename(name)
                if base in {"users.json", "channels.json"}:
                    continue
                # channel is the first directory component
                parts = name.split("/")
                if len(parts) < 2:
                    continue
                channel = parts[0]
                read_channel_day(channel, text)
    if slack_dir:
        # Expect structure: <dir>/<channel_name>/<YYYY-MM-DD>.json
        for channel in os.listdir(slack_dir):
            ch_path = os.path.join(slack_dir, channel)
            if not os.path.isdir(ch_path):
                continue
            for fname in os.listdir(ch_path):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(ch_path, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        text = f.read()
                except Exception:
                    continue
                read_channel_day(channel, text)

    # Sort globally by timestamp for stable grouping later
    messages.sort(key=lambda m: (m.channel, m.thread_key(), m.ts_float()))
    return messages


# -------------- Searching, grouping, formatting --------------


def normalize_query(q: Optional[str]) -> Optional[str]:
    if not q:
        return None
    return q.strip()


def message_matches(m: SlackMessage, query: Optional[str], invoice: Optional[str]) -> bool:
    text = m.text or ""
    lo_text = text.lower()
    if query:
        if query.lower() not in lo_text:
            return False
    if invoice:
        if invoice.lower() not in lo_text:
            return False
    return True


def group_threads(messages: List[SlackMessage]) -> Dict[Tuple[str, str], List[SlackMessage]]:
    threads: Dict[Tuple[str, str], List[SlackMessage]] = defaultdict(list)
    for m in messages:
        threads[(m.channel, m.thread_key())].append(m)
    # sort each thread by ts
    for key in threads:
        threads[key].sort(key=lambda m: m.ts_float())
    return threads


def select_threads_by_query(messages: List[SlackMessage], query: Optional[str], invoice: Optional[str], channels: Optional[List[str]] = None) -> Dict[Tuple[str, str], List[SlackMessage]]:
    channels_set = set([c.lstrip("#") for c in (channels or [])]) if channels else None

    if not query and not invoice and not channels_set:
        # nothing to filter by -> return everything (could be huge)
        return group_threads(messages)

    matched_thread_keys: set[Tuple[str, str]] = set()
    for m in messages:
        if channels_set and m.channel not in channels_set:
            continue
        if message_matches(m, query=query, invoice=invoice):
            matched_thread_keys.add((m.channel, m.thread_key()))

    if not matched_thread_keys and channels_set:
        # If no query/invoice given, selecting by channel returns all threads in those channels
        if not query and not invoice:
            return {
                key: thread
                for key, thread in group_threads(messages).items()
                if key[0] in channels_set
            }

    threads_all = group_threads(messages)
    return {key: threads_all[key] for key in matched_thread_keys if key in threads_all}


MENTION_RE = re.compile(r"<@([A-Z0-9]+)>")
CHANNEL_RE = re.compile(r"<#([A-Z0-9]+)\|([^>]+)>")
LINK_RE = re.compile(r"<([^>|]+)\|([^>]+)>")
ANGLE_RE = re.compile(r"<([^>]+)>")


def render_plain_text(text: str, users: Dict[str, SlackUser]) -> str:
    # Decode entities
    text = html.unescape(text)

    # Replace mentions <@U123>
    def replace_mention(m: re.Match[str]) -> str:
        uid = m.group(1)
        user = users.get(uid)
        if user:
            return f"@{user.best_name()}"
        return f"@{uid}"

    text = MENTION_RE.sub(replace_mention, text)

    # Replace channel ref <#C123|channel>
    text = CHANNEL_RE.sub(lambda m: f"#{m.group(2)}", text)

    # Replace links <url|label> -> label (url)
    text = LINK_RE.sub(lambda m: f"{m.group(2)} ({m.group(1)})", text)

    # Replace remaining angle form <...>
    text = ANGLE_RE.sub(lambda m: m.group(1), text)

    return text


@dataclass
class CompanyClassifier:
    domains: List[str]
    name_keywords: List[str]
    explicit_user_ids: List[str]

    def is_company_user(self, user: Optional[SlackUser], fallback_display: Optional[str]) -> bool:
        if user:
            if user.email and any(user.email.lower().endswith("@" + d.lower()) or user.email.lower().endswith(d.lower()) for d in self.domains):
                return True
            best = user.best_name()
            if any(k.lower() in best.lower() for k in self.name_keywords):
                return True
            if user.user_id in self.explicit_user_ids:
                return True
        if fallback_display:
            if any(k.lower() in fallback_display.lower() for k in self.name_keywords):
                return True
        return False


def format_markdown(
    threads: Dict[Tuple[str, str], List[SlackMessage]],
    users: Dict[str, SlackUser],
    query: Optional[str],
    invoice: Optional[str],
    tz_name: Optional[str],
    classifier: CompanyClassifier,
) -> str:
    tzinfo = None
    if tz_name and ZoneInfo is not None:
        try:
            tzinfo = ZoneInfo(tz_name)
        except Exception:
            tzinfo = None

    def fmt_ts(ts: str) -> str:
        try:
            sec = float(ts)
        except Exception:
            return ts
        dt = datetime.fromtimestamp(sec, tz=timezone.utc)
        if tzinfo is not None:
            dt = dt.astimezone(tzinfo)
        else:
            dt = dt.astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")

    title_bits: List[str] = []
    if invoice:
        title_bits.append(f"invoice: {invoice}")
    if query:
        title_bits.append(f"query: {query}")
    title = ", ".join(title_bits) if title_bits else "Slack threads"

    out: List[str] = []
    out.append(f"## {title}")
    out.append("")

    # Sort threads by first message timestamp
    threads_sorted = sorted(
        threads.items(),
        key=lambda kv: kv[1][0].ts_float() if kv[1] else float("inf"),
    )

    for (channel, tkey), msgs in threads_sorted:
        if not msgs:
            continue
        root = msgs[0]
        out.append(f"### #{channel} · thread {tkey}")
        out.append("")
        for m in msgs:
            user = users.get(m.user_id or "") if m.user_id else None
            display = user.best_name() if user else (m.user_display or "")
            stamp = fmt_ts(m.ts)
            clean = render_plain_text(m.text or "", users)
            is_company = classifier.is_company_user(user, m.user_display)
            prefix = "🟢 " if is_company else ""
            # Each message as a single paragraph line with quoted content if multiline
            if "\n" in clean:
                quoted = "\n".join("> " + line if line.strip() else ">" for line in clean.splitlines())
                out.append(f"{prefix}{stamp} {display}:")
                out.append(quoted)
            else:
                out.append(f"{prefix}{stamp} {display}: {clean}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


# -------------- CLI --------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extract Slack threads from export by invoice or query and output Markdown",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--slack-zip", dest="slack_zip", help="Path to Slack export ZIP")
    src.add_argument("--slack-dir", dest="slack_dir", help="Path to Slack export directory")

    p.add_argument("--invoice", help="Invoice ID to search (substring match)")
    p.add_argument("--query", help="Free-text query (substring match)")
    p.add_argument("--channel", action="append", help="Restrict to channel(s); repeatable; accepts without #")

    p.add_argument("--format", choices=["md", "markdown", "json", "txt"], default="md", help="Output format")
    p.add_argument("--tz", dest="tz", default=None, help="Timezone name, e.g., Asia/Tokyo")

    p.add_argument("--company-domains", nargs="*", default=["tousuien.co.jp"], help="Email domains considered company users")
    p.add_argument("--company-names", nargs="*", default=["TOUSUIEN", "桃翠園", "tousuien"], help="Name keywords considered company users")
    p.add_argument("--company-users", nargs="*", default=[], help="Explicit Slack user IDs considered company users")

    p.add_argument("--output", help="Output file; if omitted and --invoice provided, writes to reports/<invoice>.md for md format; otherwise prints to stdout")

    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    query = normalize_query(args.query)
    invoice = normalize_query(args.invoice)

    if not query and not invoice and not args.channel:
        print("[WARN] No --invoice or --query or --channel specified; output may be very large.", file=sys.stderr)

    users = load_users(args.slack_zip, args.slack_dir)
    messages = load_messages(args.slack_zip, args.slack_dir)

    threads = select_threads_by_query(messages, query=query, invoice=invoice, channels=args.channel)

    classifier = CompanyClassifier(
        domains=list(args.company_domains or []),
        name_keywords=list(args.company_names or []),
        explicit_user_ids=list(args.company_users or []),
    )

    fmt = (args.format or "md").lower()

    if fmt in ("md", "markdown"):
        body = format_markdown(threads, users, query=query, invoice=invoice, tz_name=args.tz, classifier=classifier)
    elif fmt == "txt":
        # reuse markdown without headers
        md = format_markdown(threads, users, query=query, invoice=invoice, tz_name=args.tz, classifier=classifier)
        # strip '## ' and '### '
        lines = []
        for line in md.splitlines():
            if line.startswith("### "):
                lines.append(line[4:])
            elif line.startswith("## "):
                lines.append(line[3:])
            else:
                lines.append(line)
        body = "\n".join(lines) + "\n"
    elif fmt == "json":
        # emit structured JSON: list of threads with messages
        serial = []
        for (channel, tkey), msgs in sorted(threads.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            serial.append(
                {
                    "channel": channel,
                    "thread_ts": tkey,
                    "messages": [
                        {
                            "ts": m.ts,
                            "user_id": m.user_id,
                            "user": users.get(m.user_id).best_name() if m.user_id and users.get(m.user_id) else m.user_display,
                            "text": render_plain_text(m.text or "", users),
                        }
                        for m in msgs
                    ],
                }
            )
        body = json.dumps(serial, ensure_ascii=False, indent=2) + "\n"
    else:
        print(f"Unsupported format: {fmt}", file=sys.stderr)
        return 2

    out_path = args.output
    if not out_path and fmt in ("md", "markdown") and invoice:
        # default path
        out_dir = os.path.join("reports")
        os.makedirs(out_dir, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", invoice)
        out_path = os.path.join(out_dir, f"{safe}.md")

    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(body)
        print(out_path)
    else:
        sys.stdout.write(body)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
