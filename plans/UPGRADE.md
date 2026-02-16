# Upgrade Plan (Direct Cutover)

Last updated: 2026-02-16

## Scope decisions

- No migration track. We do a direct cutover to the new architecture/tooling.
- No legacy data-format support. Target formats are ChatGPT 2026 export and Claude 2026 export only.
- No Poetry support after cutover. `uv` is the only package/runtime workflow.
- Minimum Python version after cutover: 3.11.
- Include `thinking` blocks in exports by default.
- v1 keeps provider JSON files as source of truth; normalized conversation storage is planned for v2.
- Supplementary snapshot files are out of scope for this release and moved to v2.

## Requested outcomes

1. Update all packages to latest stable versions.
2. Switch dependency/tooling workflow from Poetry to `uv`.
3. Replace TOML secrets config with `.env`.
4. Support data directories outside the project root (configured via `.env`).
5. Add export of conversations into text/markdown files for external AI tooling.
6. Reverse engineer and support ChatGPT history export format from `/Users/kuchin/Work/Mirable/chat-history-materials/ChatGPT-2026-02-01`.
7. Reverse engineer and support Claude history export format from `/Users/kuchin/Work/Mirable/chat-history-materials/Claude-2026-02-01`.

## Snapshot findings to drive implementation

### ChatGPT 2026 snapshot (`conversations.json`)

- Top-level object: list of 1924 conversations.
- `mapping` still exists, but one node per conversation has `message: null` (root node).
- Roles observed: `assistant`, `user`, `tool`, `system`.
- Content types observed: `text`, `code`, `multimodal_text`, `thoughts`, `reasoning_recap`, `execution_output`, `sonic_webpage`, `tether_quote`, `tether_browsing_display`, `system_error`.
- Content parts are heterogeneous: plain strings and typed objects (audio/image pointers and others).

### Claude 2026 snapshot (`conversations.json`)

- Top-level object: list of 346 conversations.
- Conversation keys: `uuid`, `name`, `summary`, `created_at`, `updated_at`, `account`, `chat_messages`.
- Message keys: `uuid`, `text`, `content`, `sender`, `created_at`, `updated_at`, `attachments`, `files`.
- Sender values: `human`, `assistant`.
- `content` uses block types such as `text`, `thinking`, `tool_use`, `tool_result`, `voice_note`, `token_budget`, `flag`.

## Delivery plan

## Phase 0: Test and fixture baseline (new formats only)

1. Create fixture slices only for:
   - ChatGPT 2026 export.
   - Claude 2026 export.
2. Use real truncated samples (5-10 conversations/provider), anonymized if needed, under `tests/fixtures/`.
3. Add parser tests:
   - conversation/message count expectations on fixtures,
   - block extraction coverage for non-text content,
   - no-crash behavior on unknown block types.
4. Add parse warnings for unknown fields/content types.

Exit criteria:
- Test suite protects the new parser contracts.

## Phase 1: `uv` cutover and package upgrades

1. Convert `pyproject.toml` to PEP 621-compatible metadata for `uv`.
2. Set `requires-python = ">=3.11"` in `pyproject.toml`.
3. Generate and commit `uv.lock`.
4. Remove Poetry workflow from docs and commands:
   - `make install` -> `uv sync`,
   - `make run` -> `uv run uvicorn app:app --reload --port 8080`.
5. Retire Poetry artifacts (`poetry.lock`, Poetry instructions).
6. Upgrade dependencies to latest stable, including:
   - OpenAI SDK to 1.x API style,
   - keep `pydantic.v1` compatibility shim temporarily until parser rewrite in Phase 3.

Exit criteria:
- Fresh environment boots with `uv sync` + `uv run ...`.

## Phase 2: `.env` config and external data paths

1. Add central config module that reads env vars.
2. Replace `data/secrets.toml` with `.env` and `.env.example`.
3. Add `.env` to `.gitignore`.
4. Support external paths for source data and SQLite DBs.
5. Use one shared settings DB with provider-aware records, plus provider-specific embeddings DBs.
6. Apply settings schema reset for favorites:
   - drop/recreate favorites table as provider-aware (`PRIMARY KEY (provider, conversation_id)`),
   - do not migrate old favorites from legacy schema.

Proposed env vars:

- `CHAT_HISTORY_DATA_DIR`
- `CHAT_HISTORY_CHATGPT_PATH` (path to ChatGPT `conversations.json`)
- `CHAT_HISTORY_CLAUDE_PATH` (path to Claude `conversations.json`)
- `CHAT_HISTORY_SETTINGS_DB_PATH` (optional override for shared settings DB)
- `OPENAI_API_KEY`
- `OPENAI_ORGANIZATION` (optional)
- `CHAT_HISTORY_OPENAI_ENABLED` (`true/false`)

Derived layout under `CHAT_HISTORY_DATA_DIR`:

```
DATA_DIR/
  chatgpt/
    embeddings.db
  claude/
    embeddings.db
  settings.db
  export/
```

Loading logic:

- Load each provider independently when its `*_PATH` env var is set and file exists.
- Merge loaded conversations into one in-memory list with explicit provider tagging.
- Store favorites/settings in shared `settings.db` keyed by `(provider, conversation_id)`.

Exit criteria:
- App runs with data and DB files outside repo root.
- No TOML config dependency remains.

## Phase 3: Parser core rewrite (no legacy adapters)

1. Introduce normalized internal models:
   - `ConversationRecord`,
   - `MessageRecord`,
   - `ContentBlock`.
2. Implement format detectors for:
   - ChatGPT 2026,
   - Claude 2026.
3. Add `provider` field to `ConversationRecord`.
4. Model message content as `List[ContentBlock]` (not single-block assumptions).
5. Normalize timestamps at parse time to internal UTC `datetime` objects:
   - parse ChatGPT Unix float timestamps and Claude ISO8601 timestamps into one consistent type.
6. Migrate parser models to native Pydantic v2 here (remove shim usage).
7. Remove assumptions tied to legacy ChatGPT-only schema.
8. Keep current API response contract stable for frontend compatibility.

Exit criteria:
- App reads both target providers through one normalized parser layer.

## Phase 4: ChatGPT 2026 implementation

1. Add schema inventory tooling for unknown key/type discovery.
2. Implement robust mapping traversal and active-branch selection:
   - find root (`parent: null`),
   - walk branch toward `current_node`,
   - choose child ancestor of `current_node` at forks,
   - emit canonical message sequence in traversal order.
3. Implement renderer rules per content type with fallback placeholders.
4. Preserve references to attachments/media/tool output in normalized metadata.

Exit criteria:
- Full ChatGPT 2026 snapshot parses and renders without crashes.

## Phase 5: Claude implementation

1. Parse conversation/message metadata and block structure.
2. Normalize Claude block types (`text`, `thinking`, `tool_use`, `tool_result`, etc.).
3. Use structured `content` blocks as source of truth and treat top-level `text` as derived/convenience.
4. Represent attachments/files in normalized metadata and export output.

Exit criteria:
- Full Claude snapshot parses and renders without crashes.

## Phase 6: Frontend, statistics, and export

1. Lock entry-point split:
   - `/Users/kuchin/Work/Mirable/chat-history/app.py` exposes ASGI `app` only for `uvicorn`.
   - `/Users/kuchin/Work/Mirable/chat-history/manage.py` is the CLI entry for script tasks.
2. Add export command under `manage.py`, for example:
   - `uv run python manage.py export --provider chatgpt --format markdown --out /path`
3. Runtime commands:
   - server: `uv run uvicorn app:app --reload --port 8080`
   - scripts: `uv run python manage.py <command> ...`
4. Keep `app.py` thin:
   - avoid heavy initialization at import time,
   - move operational and batch logic behind CLI commands.
5. Output formats:
   - plain text transcript,
   - markdown transcript with metadata.
6. Export contract:
   - one file per conversation,
   - stable filename slug + conversation id.
7. Add switches for including/excluding block categories (`system`, `tool`, `thinking`) and attachment references.
8. Default behavior:
   - include `thinking` blocks unless explicitly disabled.
9. Frontend changes are in scope:
   - provider indicator in sidebar/list,
   - provider-specific external links,
   - rendering for new block types (`thinking`, `tool_use`, `tool_result`, `code`, etc.).
10. Replace dollar-cost view with token statistics for both providers:
   - aggregate token counts by provider and model,
   - keep endpoint name or rename endpoint during implementation (`/api/ai-cost` -> token stats behavior).

Exit criteria:
- Frontend renders both providers with provider-specific links and new block types.
- Token statistics endpoint returns aggregate token counts by provider and model.
- Export output is deterministic and ready for downstream AI ingestion.

## Phase 7: Hardening and release

1. Run performance checks on full snapshots.
2. Run API smoke tests on main endpoints (`/api/conversations`, `/api/search`, `/api/activity`, `/api/statistics`).
3. Update docs:
   - `uv` setup/run,
   - `.env` configuration,
   - external data directory usage,
   - export command examples.
4. Prepare release checklist and cutover notes.

Exit criteria:
- Updated app is documented, validated, and ready for use on both target providers.

## Execution order

1. Phase 0.
2. Phase 1.
3. Phase 2.
4. Phase 3.
5. Phase 4 and Phase 5.
6. Phase 6.
7. Phase 7.

## Key risks and mitigations

- Risk: OpenAI SDK 1.x migration changes embeddings behavior.
  Mitigation: isolate SDK calls and add regression checks for search behavior.

- Risk: New block types continue to appear.
  Mitigation: permissive parser + explicit unknown-block fallbacks + warnings.

- Risk: Large snapshots increase memory/time costs.
  Mitigation: benchmark full snapshots and optimize parsing/serialization hotspots early.

## V2 roadmap: normalized storage

Goal:

- Move from raw JSON-at-runtime to a normalized local store while keeping JSON import support.

Scope:

1. Add normalized storage backend (SQLite) for parsed conversations/messages/content blocks.
2. Ingest pipeline per provider:
   - source = provider JSON export,
   - upsert by `(provider, external_id)`,
   - change detection via content hash/import metadata.
3. Proposed tables:
   - `conversations`,
   - `messages`,
   - `content_blocks`,
   - `attachments`,
   - `imports` (run metadata/checkpoints).
4. Add reimport commands in `manage.py`:
   - full rebuild,
   - incremental refresh per provider.
5. Switch API/query paths to read from normalized storage (with optional JSON fallback during rollout).

Exit criteria:

- Full snapshots import successfully into normalized storage.
- App startup and query performance improve vs direct large-JSON parsing.
- Deterministic exports and search continue to work from normalized data.

## Deferred to v2

- Normalized storage implementation and incremental import pipeline.
- ChatGPT supplementary files:
  - `shared_conversations.json`
  - `sora.json`
  - `message_feedback.json`
  - `user.json`
- Claude supplementary files:
  - `memories.json`
  - `projects.json`
