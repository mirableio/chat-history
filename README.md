# Chat History

UI and local tooling for browsing and exporting ChatGPT and Claude conversation history.

## Features

- Unified conversation browser for ChatGPT and Claude exports
- Provider-aware favorites and external links
- Full-text search with optional semantic search (OpenAI embeddings + FAISS)
- Activity and token statistics
- Export conversations to markdown or text for downstream AI workflows

![Screenshot](static/screenshot.png)

## Requirements

- Python 3.11+
- `uv`

## Setup

1. Copy env template:
   - `cp .env.example .env`
2. Set provider export paths in `.env`:
   - `CHAT_HISTORY_CHATGPT_PATH=/absolute/path/to/chatgpt/export/folder` (or direct `conversations.json`)
   - `CHAT_HISTORY_CLAUDE_PATH=/absolute/path/to/claude/export/folder` (or direct `conversations.json`)
3. Install dependencies:
   - `make install`
4. Run server:
   - `make run`
5. Open [http://127.0.0.1:8080](http://127.0.0.1:8080)

## Configuration

Environment variables (`.env`):

- `CHAT_HISTORY_DATA_DIR` (default: `data`)
- `CHAT_HISTORY_CHATGPT_PATH` (optional, folder or `conversations.json`)
- `CHAT_HISTORY_CLAUDE_PATH` (optional, folder or `conversations.json`)
- `CHAT_HISTORY_SETTINGS_DB_PATH` (optional)
- `OPENAI_API_KEY` (optional; enables semantic search)
- `OPENAI_ORGANIZATION` (optional)
- `CHAT_HISTORY_OPENAI_ENABLED` (`true` / `false`, default `false`)
- `OPENAI_EMBEDDING_MODEL` (default `text-embedding-3-small`)

Data layout under `CHAT_HISTORY_DATA_DIR`:

```text
DATA_DIR/
  chatgpt/
    embeddings.db
  claude/
    embeddings.db
  settings.db
  export/
```

## CLI

Main CLI entrypoint is `manage.py`.

- Inspect loaded data:
  - `uv run python manage.py inspect`
- Export conversations:
  - `uv run python manage.py export --provider all --format markdown --out /tmp/chat-export`

Filters:

- `--provider chatgpt|claude|all`
- `--exclude-system`
- `--exclude-tool`
- `--exclude-thinking`
- `--exclude-attachments`
