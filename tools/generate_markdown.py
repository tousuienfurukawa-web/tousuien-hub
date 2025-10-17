import json
from pathlib import Path
from typing import Dict, Any, List
import re

EXPORT_ROOT = Path('/workspace/slack_export')
OUTPUT_ROOT = Path('/workspace/gpt_knowledge')
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w\-一-龯ぁ-んァ-ヶー０-９]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "untitled"


def load_json(path: Path):
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def build_index(channels_file: Path) -> Dict[str, Any]:
    channels = load_json(channels_file)
    return {c.get('name', c.get('id', 'unknown')): c for c in channels}


def write_channel_markdown(channel: str, channel_dir: Path):
    messages_count = 0
    output_path = OUTPUT_ROOT / f"slack_{sanitize_filename(channel)}.md"
    with output_path.open('w', encoding='utf-8') as out:
        out.write(f"# Slack channel: {channel}\n\n")
        for day_path in sorted(channel_dir.glob('*.json')):
            day = day_path.stem
            try:
                messages: List[Dict[str, Any]] = load_json(day_path)
            except Exception:
                continue
            if not isinstance(messages, list):
                continue
            out.write(f"## {day}\n\n")
            for msg in messages:
                text = msg.get('text') or ''
                user = msg.get('user') or 'unknown'
                ts = msg.get('ts') or ''
                attachments = msg.get('attachments')
                files = msg.get('files')
                out.write(f"- [{ts}] <@{user}>: {text}\n")
                if attachments:
                    out.write(f"  - attachments: {json.dumps(attachments, ensure_ascii=False)}\n")
                if files:
                    out.write(f"  - files: {json.dumps(files, ensure_ascii=False)}\n")
                messages_count += 1
            out.write("\n")
    return output_path, messages_count


def main():
    channels_file = EXPORT_ROOT / 'channels.json'
    users_file = EXPORT_ROOT / 'users.json'
    if not channels_file.exists():
        print("channels.json not found in export root")
    index = build_index(channels_file) if channels_file.exists() else {}

    total_messages = 0
    channel_files = []

    for channel_dir in sorted(EXPORT_ROOT.iterdir()):
        if not channel_dir.is_dir():
            continue
        output_path, count = write_channel_markdown(channel_dir.name, channel_dir)
        channel_files.append(output_path)
        total_messages += count

    # write a small README for GPT
    readme_path = OUTPUT_ROOT / 'README.md'
    with readme_path.open('w', encoding='utf-8') as f:
        f.write("# Knowledge Base: Slack Export\n\n")
        f.write("This folder contains markdown summaries of Slack channels exported from your workspace.\n\n")
        f.write("## Files\n")
        for p in channel_files:
            f.write(f"- {p.name}\n")
        f.write(f"\nTotal messages summarized: {total_messages}\n")

    print(f"Generated {len(channel_files)} channel files, messages: {total_messages}")


if __name__ == '__main__':
    main()
