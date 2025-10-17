from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json
from typing import List, Dict, Any, Optional

EXPORT_ROOT = Path('/workspace/slack_export')

app = FastAPI(title="Slack Export API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def read_json_file(path: Path) -> Any:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    try:
        with path.open('r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Invalid JSON: {path}: {e}")


@app.get("/channels")
def list_channels() -> List[Dict[str, Any]]:
    path = EXPORT_ROOT / 'channels.json'
    return read_json_file(path)


@app.get("/users")
def list_users() -> List[Dict[str, Any]]:
    path = EXPORT_ROOT / 'users.json'
    return read_json_file(path)


@app.get("/channels/{channel_name}/days")
def list_days(channel_name: str) -> List[str]:
    channel_dir = EXPORT_ROOT / channel_name
    if not channel_dir.exists() or not channel_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_name}")
    days = sorted([p.stem for p in channel_dir.glob('*.json')])
    return days


@app.get("/channels/{channel_name}/messages")
def get_messages(channel_name: str, day: Optional[str] = None) -> List[Dict[str, Any]]:
    channel_dir = EXPORT_ROOT / channel_name
    if not channel_dir.exists() or not channel_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Channel not found: {channel_name}")

    def load_day(day_path: Path) -> List[Dict[str, Any]]:
        data = read_json_file(day_path)
        if isinstance(data, list):
            return data
        return []

    if day:
        day_path = channel_dir / f"{day}.json"
        return load_day(day_path)

    messages: List[Dict[str, Any]] = []
    for day_path in sorted(channel_dir.glob('*.json')):
        messages.extend(load_day(day_path))
    return messages


@app.get("/search")
def search_messages(q: str, limit: int = 50) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for channel_dir in EXPORT_ROOT.iterdir():
        if not channel_dir.is_dir():
            continue
        for day_path in sorted(channel_dir.glob('*.json')):
            try:
                for msg in read_json_file(day_path):
                    text = msg.get('text') or ''
                    if q.lower() in text.lower():
                        results.append({
                            'channel': channel_dir.name,
                            'day': day_path.stem,
                            'ts': msg.get('ts'),
                            'user': msg.get('user'),
                            'text': text,
                            'files': msg.get('files'),
                            'reactions': msg.get('reactions'),
                        })
                        if len(results) >= limit:
                            return results
            except Exception:
                continue
    return results
