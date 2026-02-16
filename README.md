# Chat History

UI and local tooling for browsing and exporting ChatGPT and Claude conversation history.

## Features

- Unified conversation browser for ChatGPT and Claude exports
- Provider-aware favorites and external links
- Full-text search with optional semantic search (OpenAI embeddings + FAISS)
- Activity and token statistics
- Export conversations to markdown for downstream AI workflows

![Screenshot](screenshot.png)

## Basic Usage (uvx)

- Python 3.11+
- `uv`

### Quick start

```bash
uvx chat-history
```

Auto mode behavior:

- If `data/.env` exists in current directory, it starts the server.
- If `data/.env` is missing, it starts the interactive setup wizard.

Common commands:

```bash
uvx chat-history init
uvx chat-history serve --port 8080
uvx chat-history inspect
uvx chat-history export --provider all --out ./data/export --clean
```

Then open [http://127.0.0.1:8080](http://127.0.0.1:8080).

## Developer Setup

1. Sync dependencies:
   - `make install`
2. Create local config:
   - `mkdir -p data && cp .env.example data/.env`
3. Set provider export paths in `data/.env`:
   - `CHAT_HISTORY_CHATGPT_PATH=/absolute/path/to/chatgpt/export/folder` (or direct `conversations.json`)
   - `CHAT_HISTORY_CLAUDE_PATH=/absolute/path/to/claude/export/folder` (or direct `conversations.json`)
4. Start app:
   - `make run`

## Developer Workflow

- Dev server with reload: `make dev`
- Tests: `make test`
- Run CLI directly: `uv run chat-history --help`
- Run packaged entrypoint from repo checkout: `uvx --from . chat-history --help`

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

## Configuration (`data/.env`)

- `CHAT_HISTORY_DATA_DIR` (default: `data`)
- `CHAT_HISTORY_CHATGPT_PATH` (optional, folder or `conversations.json`)
- `CHAT_HISTORY_CLAUDE_PATH` (optional, folder or `conversations.json`)
- `CHAT_HISTORY_SETTINGS_DB_PATH` (optional)
- `OPENAI_API_KEY` (optional; enables semantic search)
- `OPENAI_ORGANIZATION` (optional)
- `CHAT_HISTORY_OPENAI_ENABLED` (`true` / `false`, default `false`)
- `OPENAI_EMBEDDING_MODEL` (default `text-embedding-3-small`)

## CLI Reference

Main CLI entrypoint: `chat-history`

- Start server:
  - `uv run chat-history serve --port 8080`
- Auto mode:
  - `uv run chat-history`
  - If `data/.env` exists in the current directory, starts the server.
  - If `data/.env` does not exist, starts interactive setup wizard.
  - Config is loaded from `./data/.env` only (current working directory); default data path is `./data`.
- Interactive setup wizard:
  - `uv run chat-history init`
  - `uv run chat-history init --path /absolute/path/to/project-dir`

- Inspect loaded data:
  - `uv run chat-history inspect`
- Export conversations:
  - `uv run chat-history export --provider all --out /tmp/chat-export`
  - Add `--clean` to remove old export files before writing new ones.
  - Output layout: `/tmp/chat-export/{chatgpt|claude}/yyyy-mm-dd-hash.md`

Filters:

- `--provider chatgpt|claude|all`
- `--exclude-system`
- `--exclude-tool`
- `--exclude-thinking`
- `--exclude-attachments`
- `--clean`

## Global Command (Local Editable Install)

Install the local repo as a global tool:

- `uv tool install -e .`

Then run from any directory:

- `chat-history --help`
- `chat-history`
- `chat-history serve --port 8080`
- `chat-history init`
- `chat-history inspect`
- `chat-history export --provider all`

Uninstall:

- `uv tool uninstall chat-history`

## Notes

- Export is non-destructive by default. Existing files remain unless `--clean` is used.
- Token stats for Claude are approximate (fallback tokenizer), not exact Claude-native counts.
