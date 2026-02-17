# Chat History

Browse and export your ChatGPT and Claude conversations locally.

![Screenshot](screenshot.png)

## Getting Started

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

1. **Export your chats** from [ChatGPT](https://chatgpt.com/#settings/DataControls) or
   [Claude](https://claude.ai/settings/data-privacy-controls) (Settings → Export data).
   Both services send a ZIP file by email.

2. **Create a folder** for your chat history, save the ZIP there,
   and open a terminal in that folder. The wizard will store all data inside it.

3. **Run the setup wizard:**

   ```bash
   uvx chat-history
   ```

   The wizard finds your export files, configures everything, and opens the browser.

Next time, run `uvx chat-history` in the same folder to start browsing.
To update to the latest version, run `uvx chat-history install`.

To export all conversations as markdown (useful for feeding to other AI tools):

```bash
uvx chat-history export
```

## Features

- Unified conversation browser for ChatGPT and Claude exports
- Provider-aware favorites and external links
- Full-text search with optional semantic search (OpenAI embeddings + FAISS)
- Activity and token statistics
- Export conversations to markdown for downstream AI workflows

## CLI Reference

All commands work as `uvx chat-history <command>` or, if installed locally, `chat-history <command>`.

| Command | Description |
|---------|-------------|
| *(none)* | Start server if configured, otherwise run setup wizard |
| `init` | Run the interactive setup wizard |
| `serve` | Start the web server |
| `export` | Export conversations to markdown |
| `inspect` | Print conversation and message counts |
| `install` | Reinstall `chat-history` via `uvx --reinstall chat-history` |

### serve

```bash
uvx chat-history serve [--host 127.0.0.1] [--port 8080] [--no-browser]
```

### export

```bash
uvx chat-history export [--provider chatgpt|claude|all] [--out DIR] [--clean]
                        [--exclude-system] [--exclude-tool]
                        [--exclude-thinking] [--exclude-attachments]
```

- `--clean` removes old export files before writing (scoped to `--provider` if set)
- Default output: `./data/export/{chatgpt|claude}/`

### init

```bash
uvx chat-history init [--path DIR]
```

Scans the current folder and `~/Downloads` for export ZIPs, validates them,
extracts to `./data/`, writes `./data/.env`, and offers to start the server.
Supports adding a second provider to an existing setup.

## Configuration

All config lives in `./data/.env` (created by the wizard or manually):

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAT_HISTORY_DATA_DIR` | `data` | Root directory for derived data |
| `CHAT_HISTORY_CHATGPT_PATH` | — | Path to ChatGPT export folder or `conversations.json` |
| `CHAT_HISTORY_CLAUDE_PATH` | — | Path to Claude export folder or `conversations.json` |
| `CHAT_HISTORY_OPENAI_ENABLED` | `false` | Enable semantic search |
| `OPENAI_API_KEY` | — | Required if semantic search is enabled |
| `OPENAI_ORGANIZATION` | — | Optional OpenAI org |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model for semantic search |
| `CHAT_HISTORY_SETTINGS_DB_PATH` | — | Override path for settings SQLite DB |

## Developer Setup

```bash
make install    # uv sync
make dev        # uvicorn with hot-reload on :8080
make test       # run tests
```

Install as a global command from the local repo (editable, changes reflected immediately):

```bash
make tool-install         # uv tool install -e .
chat-history              # works from any directory
make tool-uninstall       # uv tool uninstall chat-history
```

## Notes

- Export is non-destructive by default. Existing files remain unless `--clean` is used.
- Token stats for Claude are approximate (fallback tokenizer), not exact Claude-native counts.
