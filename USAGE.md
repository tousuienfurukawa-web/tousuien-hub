## How to use the Slack Export with GPT

- **Local API**: A FastAPI server exposes the Slack export for GPT Actions.
- **Knowledge files**: Markdown summaries of channels are in `gpt_knowledge/` and zipped as `gpt_knowledge.zip` for upload to GPT knowledge.
- **Action spec**: `gpt_action_openapi.yaml` and `app/openapi.yaml` define the API for use as a GPT Action.

### 1) Run the API locally

```bash
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000/docs` to try endpoints.

### 2) Connect as a GPT Action

- In GPT builder, add an Action and upload `gpt_action_openapi.yaml` (or point to `http://localhost:8000/openapi.json` if reachable).
- Set auth to "None" (local only). If exposing externally, add reverse-proxy and auth.

Key operations:
- `GET /search?q=keyword&limit=20` – keyword search across messages
- `GET /channels` – list channels from export
- `GET /channels/{channel_name}/days` – list available dates for a channel
- `GET /channels/{channel_name}/messages?day=YYYY-MM-DD` – messages for one day (or omit `day` for all)

### 3) Upload knowledge to GPT

- Upload `gpt_knowledge.zip` to your GPT as Knowledge.
- Or drag `gpt_knowledge/*.md` individually for targeted context.

### Troubleshooting when GPT doesn’t “see” Slack data

- **Knowledge vs Action**: Knowledge uploads are static context; Actions require the model to call the API. Verify the model actually called the Action (check the Run log in GPT Builder).
- **CORS/network**: If the Action cannot reach `http://localhost:8000`, it will silently fail. Prefer exposing via a public tunnel (e.g., `cloudflared tunnel`, `ngrok`) and update the server URL in `gpt_action_openapi.yaml`.
- **Schema mismatch**: If you update endpoints, re-upload the OpenAPI. Stale schemas cause the Action to be skipped.
- **Too large knowledge**: The model may truncate. Use the Search Action to retrieve precise snippets instead of only knowledge.
- **Slack export structure**: Place `channels.json`, `users.json`, and channel folders directly under `/workspace/slack_export`.

### Notes

- The export in `/workspace/slack_export` is read-only by the API.
- `tools/generate_markdown.py` can be rerun after new exports.
