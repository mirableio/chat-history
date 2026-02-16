# Plan: Make chat-history runnable via `uvx`

## Context

The project currently runs only from the repo root via `make run` / `uv run uvicorn app:app`.
The goal is to enable `uvx chat-history` to work as a zero-install experience: the user runs
it in any directory, gets an interactive setup wizard if no data is found, or the web server
starts automatically if data is already configured.

This requires converting the flat-file project into a proper installable Python package with
a console entry point.

## Two-phase delivery

The work splits into two independent phases:

**Phase A — Packaging:** Move files into a package, fix imports, add entry point with
`serve`/`export`/`inspect` subcommands. Pure mechanical refactoring. Result: `chat-history serve`
works, `uv tool install -e .` works, all tests pass.

**Phase B — Init wizard:** Add the `init` subcommand with interactive setup, Downloads
scanning, ZIP extraction, broken-path recovery. New feature on top of a working package.

Phase A is verified and committed before Phase B starts. If the wizard has bugs, the core
tool still works.

---

## Phase A: Packaging

### A1. Create package directory and move files

Create `chat_history/` package at project root. Move all Python source files and `static/`
into it.

**Files to move (root → `chat_history/`):**
- `app.py`, `config.py`, `embeddings.py`, `exporter.py`, `models.py`,
  `parsers.py`, `server.py`, `services.py`, `storage.py`, `utils.py`
- `static/` → `chat_history/static/` (entire directory)

**New file:** `chat_history/__init__.py` (minimal, exports `__version__`)

**Delete after move:** `manage.py` (absorbed into `cli.py`), original root-level `.py`
files, `static/` directory

**Files that stay at root:** `pyproject.toml`, `Makefile`, `README.md`, `LICENSE`,
`.env.example`, `.gitignore`, `tests/`, `plans/`, `data/`

### A2. Delete `manage.py`, create `cli.py`

`manage.py` is ~140 lines of argparse + two thin functions (`run_export`, `run_inspect`).
All of it folds into `cli.py`. There is no reason to keep both files.

`cli.py` absorbs:
- `manage.build_parser()` argparse definitions → become subparsers of the new CLI
- `manage.run_export()` → `cli._cmd_export()`
- `manage.run_inspect()` → `cli._cmd_inspect()`
- `manage.main()` → replaced by `cli.main()`

One test imports from manage (`tests/test_exporter.py: from manage import run_export`).
Update to `from chat_history.cli import _cmd_export`.

### A3. Update all internal imports

Every bare import like `from config import ...` becomes `from chat_history.config import ...`.

Files with internal imports to update:
- `chat_history/app.py` — 1 import (`server`)
- `chat_history/server.py` — 2 imports (`config`, `services`)
- `chat_history/services.py` — 6 imports (`config`, `embeddings`, `models`, `parsers`, `storage`, `utils`)
- `chat_history/embeddings.py` — 1 import (`models`)
- `chat_history/parsers.py` — 1 import (`models`)
- `chat_history/exporter.py` — 1 import (`models`)

Files with NO internal imports (no changes): `models.py`, `storage.py`, `utils.py`, `config.py`

Test files to update:
- `tests/test_api.py` — `from chat_history.server import create_app`
- `tests/test_exporter.py` — `from chat_history.cli import _cmd_export` + other imports
- `tests/test_parsers.py` — `from chat_history.parsers import ...`

### A4. Fix static file resolution in `server.py`

Current (breaks when installed as package):
```python
app.mount("/", StaticFiles(directory="static", html=True), name="Static")
```

Fix:
```python
_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="Static")
```

### A5. Update `pyproject.toml`

- Remove `[tool.uv] package = false`
- Add `[project.scripts]`: `chat-history = "chat_history.cli:main"`
- Add `[tool.hatch.build]`: `packages = ["chat_history"]`
- Bump version to `0.3.0`

### A6. `cli.py` — subcommands (Phase A scope)

Phase A delivers three subcommands plus auto-detect:

```
chat-history              → auto-detect: if .env exists in CWD → serve; else → print help
chat-history serve        → start web server + open browser
chat-history export ...   → export conversations (from manage.py)
chat-history inspect      → print conversation counts (from manage.py)
```

**Auto-detect logic (`main()` with no subcommand):**
- Check CWD for `.env` file
- If found → run `serve`
- If not found → print help text suggesting `chat-history init` or `chat-history serve`

(The `init` wizard is added in Phase B.)

**`serve` subcommand:**
- Flags: `--port` (default 8080), `--host` (default 127.0.0.1), `--no-browser`
- Starts uvicorn programmatically via `uvicorn.run("chat_history.app:app", ...)`
- Opens browser in background thread after 1.5s delay (unless `--no-browser`)

**`export` and `inspect`:** same argparse and logic as current `manage.py`, just
living in `cli.py` now.

### A7. Update Makefile

```makefile
run:
	uv run chat-history serve --port 8080

dev:
	uv run uvicorn chat_history.app:app --reload --port 8080

install:
	uv sync

test:
	uv run python -m unittest discover -s tests -v

tool-install:
	uv tool install -e .

tool-uninstall:
	uv tool uninstall chat-history
```

### A8. Move `screenshot.png` out of static

`static/screenshot.png` is only used by README, not the web app. Move it to repo root
to keep the wheel smaller. Update README image reference.

### Phase A execution order

1. Create `chat_history/` directory and `__init__.py`
2. Move all source files and `static/` into `chat_history/`
3. Create `chat_history/cli.py` with serve/export/inspect (absorbing manage.py)
4. Delete `manage.py` and original root-level `.py` files
5. Update all imports (source + tests)
6. Fix static file path in `server.py`
7. Update `pyproject.toml`
8. Update `Makefile`
9. `uv sync` + run tests → all pass
10. `uv run chat-history serve --port 8080` → server starts
11. `uv tool install -e .` → `chat-history` works globally
12. Move `screenshot.png`, update README

### Phase A verification

1. `uv sync` — no errors
2. `uv run python -m unittest discover -s tests -v` — all tests pass
3. `uv run chat-history --help` — shows subcommands
4. `uv run chat-history serve --port 8080` — server starts, browser opens
5. `uv run chat-history inspect` — prints conversation counts
6. `make dev` — uvicorn starts with hot-reload
7. `uv tool install -e .` then from any directory:
   - `chat-history --help` — works without `uv run` prefix
   - `chat-history inspect` — prints conversation counts

---

## Phase B: Init wizard

### B1. Add `init` subcommand to `cli.py`

New subcommand: `chat-history init [--path DIR]`

Supports both fresh setup and additive updates. If `.env` already exists, the wizard
reads it, shows current configuration, and lets the user add or replace providers.

### B2. Wizard flow

```
Step 1: Determine target directory
├── Default: CWD
├── Override: --path /some/dir
└── Create dir if it doesn't exist

Step 2: Detect existing config
├── If .env exists → read it, show summary:
│   "Current config:"
│   "  ChatGPT: /path/to/chatgpt/conversations.json (1,432 conversations)"
│   "  Claude:  not configured"
│   "  Data:    /path/to/data/"
│   Then ask which provider to add/update
└── If no .env → fresh setup, ask about both providers

Step 3: Auto-scan ~/Downloads for export files
├── Scan for files matching known patterns:
│   *.zip files containing "chatgpt" or "claude" in the name
│   (actual ZIP naming TBD — verify against real exports before implementing)
├── Sort by modification time (newest first)
├── If matches found, show numbered list:
│   "Found potential ChatGPT exports in ~/Downloads:"
│   "  [1] chatgpt-2026-02-10.zip (45 MB, 6 days ago)"
│   "  [2] chatgpt-2025-11-01.zip (38 MB, 3 months ago)"
│   "  [3] Enter path manually"
│   "  [4] Skip ChatGPT"
└── If no matches → prompt for path or skip

Step 4: Process selected file (per provider)
├── If ZIP file:
│   ├── Extract to data/<provider>/ in the target directory
│   ├── Look for conversations.json inside the extracted contents
│   │   (may be at root of ZIP or in a subdirectory)
│   ├── If not found → error: "No conversations.json found in ZIP"
│   └── Record the extracted path
├── If directory:
│   ├── Check for conversations.json inside
│   └── Record the path
├── If conversations.json file directly:
│   └── Record the path
└── Validate:
    ├── Load file, parse first item to detect format:
    │   ChatGPT: has "mapping" and "current_node" keys
    │   Claude:  has "uuid" and "chat_messages" keys
    ├── If format doesn't match declared provider → warn and ask to continue
    ├── Count total conversations
    └── Print: "✓ Found 1,432 ChatGPT conversations (Oct 2023 – Feb 2026)"

Step 5: Repeat step 3-4 for the other provider (if applicable)

Step 6: Optional OpenAI API key
├── "Enable semantic search? (requires OpenAI API key)"
├── If yes → prompt for key, validate format (sk-...)
└── If no → skip, set CHAT_HISTORY_OPENAI_ENABLED=false

Step 7: Write .env
├── If .env exists → update only changed keys, preserve others
├── If fresh → write all keys
├── Always use absolute paths
├── Template:
│   CHAT_HISTORY_DATA_DIR=/absolute/path/to/data
│   CHAT_HISTORY_CHATGPT_PATH=/absolute/path/to/data/chatgpt
│   CHAT_HISTORY_CLAUDE_PATH=/absolute/path/to/data/claude
│   CHAT_HISTORY_OPENAI_ENABLED=false
└── Print final summary

Step 8: Offer to start
├── "Start browsing? [Y/n]"
├── If yes → call serve logic (start uvicorn, open browser)
└── If no → print "Run 'chat-history' to start later"
```

### B3. Broken path recovery

When `chat-history` is run (no subcommand) and `.env` exists but referenced data paths
are missing or unreadable, detect broken paths and offer to fix interactively:

```
"⚠ ChatGPT path not found: /old/path/chatgpt/conversations.json"
"Would you like to:"
"  [1] Provide a new path"
"  [2] Remove this provider from config"
"  [3] Continue anyway (provider will be skipped)"
```

### B4. Provider auto-detection from file content

When a user provides a file/ZIP and the wizard isn't sure which provider it belongs to,
inspect the first JSON array element:
- Has `"mapping"` + `"current_node"` → ChatGPT
- Has `"uuid"` + `"chat_messages"` → Claude
- Neither → unknown, ask the user

### B5. ZIP extraction details

- Use Python `zipfile` module (stdlib, no extra dependency)
- Extract to `data/<provider>/` within the target directory
- Handle nested directory structures (some ZIPs have a top-level folder)
- After extraction, locate `conversations.json` by walking the extracted tree
- If multiple `conversations.json` found, use the shallowest one

### B6. Update auto-detect logic

After Phase B, the auto-detect changes:

```
chat-history    → if .env exists → serve
                → if no .env    → init (was: print help)
```

### Phase B verification

1. Fresh init in empty directory:
   `cd /tmp && mkdir test-ch && cd test-ch && chat-history init`
2. Additive update: run `chat-history init` in a directory that already has `.env`
   with one provider configured → add the second provider
3. Broken path recovery: edit `.env` to point at a nonexistent path, run
   `chat-history` → offers to fix
4. ZIP extraction: provide a real export ZIP → extracts correctly, finds
   conversations.json

---

## Files summary

### Files to create

| File | Purpose |
|------|---------|
| `chat_history/__init__.py` | Package marker, `__version__` |
| `chat_history/cli.py` | Single entry point: auto-detect, serve, init, export, inspect |

### Files to delete

| File | Reason |
|------|--------|
| `manage.py` | Absorbed into `cli.py` |

### Files to modify

| File | Change |
|------|--------|
| `pyproject.toml` | Remove `package = false`, add scripts + hatch build config |
| `chat_history/server.py` | Static dir resolution via `Path(__file__).parent` |
| `chat_history/app.py` | Import path |
| `chat_history/services.py` | Import paths (6 imports) |
| `chat_history/embeddings.py` | Import path |
| `chat_history/parsers.py` | Import path |
| `chat_history/exporter.py` | Import path |
| `tests/test_api.py` | Import paths |
| `tests/test_exporter.py` | Import paths (manage → cli) |
| `tests/test_parsers.py` | Import paths |
| `Makefile` | New targets: `dev`, `test`, `tool-install`; update `run` |
| `README.md` | uvx/tool usage, new CLI docs, screenshot path |

## Local tool install

After Phase A, you can install the tool globally from the local repo using editable mode:

```bash
uv tool install -e .
```

This creates a symlink in `~/.local/bin/chat-history` pointing back to the source tree.
Source code changes are reflected immediately — no reinstall needed. Only `pyproject.toml`
changes (new deps, new entry points) require `uv tool install -e . --force`.

To uninstall: `uv tool uninstall chat-history`

**Difference from `uvx`:** `uv tool install -e .` is a permanent local install with
live source edits. `uvx chat-history` is a one-shot run that pulls from PyPI (requires
publishing first). Both work after the restructuring, but local tool install is the
development workflow.

## Open question

- The `.env` file is loaded from CWD (`dotenv_values(".env")`). When running `chat-history`
  from an arbitrary directory, the tool expects `.env` in that directory. This is the intended
  UX: each data directory is self-contained with its own `.env`. No global config.
