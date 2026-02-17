# Plan: Multimodal Attachments and Asset Rendering

## Context

Current chat rendering is text-first. Attachments/files are mostly placeholders.

Goal: render multimodal content directly in the chat pane, provider-aware, with graceful fallbacks.

Sources analyzed:

- ChatGPT: `/Users/kuchin/Work/Mirable/chat-history-materials/ChatGPT-2026-02-01/conversations.json`
- Claude: `/Users/kuchin/Work/Mirable/chat-history-materials/Claude-2026-02-01/conversations.json`
- Claude new default zip: `/Users/kuchin/Work/Mirable/chat-history-materials/data-2026-02-16-18-17-35-batch-0000.zip`

## Data Findings

### ChatGPT

- Top-level message `content_type` includes `multimodal_text` (2037 messages).
- Multimodal part types:
  - `audio_transcription` (1641)
  - `audio_asset_pointer` (821)
  - `real_time_user_audio_video_asset_pointer` (820)
  - `image_asset_pointer` (502)
  - `string_part` (877)
- Pointer schemes:
  - `sediment://...` (1758)
  - `file-service://...` (385)
- Audio format observed: `wav` only.
- Realtime AV parts contain audio only in this snapshot:
  - `video_container_asset_pointer` not present
  - `frames_asset_pointers` empty

### Claude

- Message blocks are mostly `text`, `thinking`, `tool_use`, `tool_result`.
- Attachments are outside content blocks:
  - `attachments[]`: `file_name`, `file_size`, `file_type`, `extracted_content`
  - `files[]`: `file_name`
- Snapshot counts:
  - messages with non-empty `attachments[]`: 122
  - messages with non-empty `files[]`: 150
- New default zip counts:
  - messages with non-empty `attachments[]`: 130
  - messages with non-empty `files[]`: 161
- `attachments[].file_type` is mostly `txt`/`text/plain`.
- Many `attachments[].file_name` and `files[].file_name` are empty.

## File Discovery (Concrete)

### ChatGPT export root and path derivation

Resolver root for ChatGPT is `chatgpt_path.parent` (where `chatgpt_path` is resolved `conversations.json`).

Observed local file patterns:

- `file-service://file-<id>` pointers often map to files like:
  - `file-<id>-<suffix>.<ext>`
- `sediment://file_<id>` pointers map to files like:
  - `file_<id>-<suffix>.<ext>`
  - audio often under `<conversation_uuid>/audio/file_<id>-<suffix>.wav`

Observed resolution quality in analyzed snapshot:

- `image_asset_pointer` + `sediment://`: ~97%
- `image_asset_pointer` + `file-service://`: ~88%
- `audio_asset_pointer` + `sediment://`: ~42%
- `real_time_user_audio_video_asset_pointer` + `sediment://`: ~42%

Conclusion: best-effort local resolution is viable, but unresolved assets are expected.

### Claude export root and path derivation

Resolver root for Claude is `claude_path.parent`.

Observed archive structure:

- `Claude-2026-02-01.zip` and `data-...-batch-0000.zip` contain only JSON files at root in analyzed samples.
- No binary payload files are present in those zips.

Conclusion: for Claude V1, treat `attachments[]` primarily as text payload (`extracted_content`) and `files[]` as metadata references, usually unresolved for binary open/download.

## Architecture Decision

Use a single message-content path (no parallel `assets` list).

Decision: keep `ContentBlock` as canonical message representation and enrich attachment-related blocks with structured asset metadata in `ContentBlock.data`.

Reason:

- avoids dual-path (`content` vs `assets`) complexity
- avoids frontend dedupe logic
- preserves exporter behavior based on `message.text()`
- is incremental with current code and tests

## UX Behavior by Type

### Image blocks

- Render thumbnail grid for resolved images.
- Click opens full image.
- If unresolved, show metadata chip with pointer ID.

### Audio blocks

- Render `<audio controls>` when resolved.
- Show format/duration if available.
- If unresolved, show audio metadata chip.

### Transcript blocks (`audio_transcription`)

- Render transcript as text block with direction badge (`in`/`out`).

### Claude text attachments (`attachments[].extracted_content`)

- Render collapsible “Document text” block.
- Supports markdown/plain toggle.

### Generic files (`files[]`, unresolved or unknown)

- Render file chips with extension-based icon and metadata.
- If resolved, provide open/download link.

## Parser and Model Changes

### Parser (`chat_history/parsers.py`)

1. ChatGPT:
   - Parse multimodal parts into explicit `ContentBlock`s:
     - `image_asset_pointer`
     - `audio_asset_pointer`
     - `real_time_user_audio_video_asset_pointer` (audio-focused in V1)
     - `audio_transcription`
   - For asset blocks, populate `block.data.asset` with normalized fields:
     - `asset_id`, `kind`, `source_pointer`, `mime_type`, `size_bytes`, `width`, `height`, `format`, `duration`, `is_resolved`, `asset_url`

2. Claude:
   - Convert `attachments[]` and `files[]` into `ContentBlock`s with structured metadata.
   - Preserve long `extracted_content` explicitly in parser flow before `_lightweight_metadata`:
     - map full `extracted_content` to `block.text` for text-attachment rendering/search
     - if needed, also keep raw value in a dedicated data key (e.g. `data.extracted_content_raw`)
     - do not route long `extracted_content` through `_lightweight_metadata` (it has truncation caps)
   - Add fallback naming when `file_name` is empty.
   - Keep `attachments[]` and `files[]` separate (`attachment` vs `file`) in V1/V2.
     - do not merge by heuristic; metadata shapes and UX roles differ.

### Model (`chat_history/models.py`)

No new top-level `MessageAsset` model in V1.

Optional refinement:

- add a typed helper for `block.data["asset"]` shape (typed dict/dataclass utility), while keeping external payload backward-compatible.

## Asset ID and Stability

Define deterministic `asset_id`:

`sha1(f"{provider}|{conversation_id}|{message_id}|{block_type}|{source_pointer_or_filename}|{block_index}")[:20]`

Stability guarantee:

- session-stable/reload-stable for the same parser output
- not guaranteed permanently stable across parser changes that shift block ordering (`block_index` can change)

Decision:

- acceptable for V1 because IDs are ephemeral and registry-backed
- do not persist `asset_id` into long-lived stores (DB/cache/index)

## Serving Strategy

### Decision: keep controlled API endpoint

Use:

- `GET /api/assets/{provider}/{asset_id}`

Why not static mount in V1:

- provider export roots may contain sensitive JSON (`conversations.json`, `users.json`, etc.)
- pointer-to-file mapping is not 1:1 path derivation in many cases
- unresolved assets need explicit 404 behavior via registry

Endpoint rules:

- server-side lookup from `asset_id` registry
- no direct client-supplied filesystem paths
- strict existence checks and path normalization
- return 404 for unresolved/missing assets
- set content type from extension or metadata
- set `Cache-Control: private, max-age=86400` for resolved assets (safe local cache)

## Service/API Changes

### `GET /api/conversations/{provider}/{conv_id}/messages`

- keep current payload shape
- enrich `blocks[*].data.asset` for multimodal/attachment/file blocks
- no separate top-level `assets` array in V1

### Asset registry lifecycle

- Build registry on `service.load()`
- Key by `asset_id` -> resolved absolute path + metadata
- Rebuild on reload/init
- Expected memory footprint:
  - ~3k-5k assets: low single-digit MB
  - even ~50k assets is still manageable (mostly short strings + paths)

## Frontend Changes

Primary files:

- `chat_history/static/script.js`
- `chat_history/static/style.css`

Rendering strategy:

1. Detect `block.data.asset` and route to asset renderer.
   - current hook point is existing `ATTACHMENT_BLOCK_TYPES` handling in `renderMessageBlock`.
2. Add per-kind renderers:
   - image
   - audio
   - transcript
   - document text
   - file chip
3. Keep current text rendering for non-asset blocks.
4. Show unresolved fallback chips without breaking message flow.

## Exporter Impact

Current exporter path uses `message.text()` from content blocks.

V1 behavior:

- preserve placeholder text for asset blocks (e.g. `[Image]`, `[Audio]`, `[Attachment] ...`)
- include attachment extracted text for Claude when present (collapsible in UI, textual in export)

Optional V1.1:

- append resolved asset links in markdown export when `include_attachments=true`
- append unresolved pointer stubs when not resolvable

## Search Impact

No search architecture change in V1.

Behavior:

- transcript and extracted text blocks are searchable as normal text
- binary asset metadata can be indexed later if needed

## Phase Plan (Visible Value Early)

### Phase 1: End-to-end images first

Scope:

- parse ChatGPT image assets into blocks with metadata
- resolve pointer -> local file (best effort)
- add `/api/assets/{provider}/{asset_id}`
- render images in chat pane

Exit criteria:

- image thumbnails visible for resolvable assets
- unresolved images show clean fallback chip
- no regressions in current chat rendering

### Phase 2: Audio + Claude attachments/files + polish

Scope:

- ChatGPT audio/realtime-audio + transcription rendering
- Claude `attachments[].extracted_content` and `files[]` blocks
- `_lightweight_metadata`/parser adjustments for long attachment text
- exporter update for attachment text/link behavior
- UI polish and performance checks

Exit criteria:

- audio players and transcripts render correctly
- Claude document text and file chips render correctly
- exporter behavior documented and tested

## Testing Plan

### Unit tests

1. ChatGPT multimodal parsing:
   - image pointers
   - audio pointers
   - realtime audio pointers
   - transcription blocks
2. Claude parsing:
   - attachments with long `extracted_content`
   - files with empty/non-empty names
3. Deterministic `asset_id` stability.
   - explicitly test that stability is parser-output dependent (not persisted-contract stable).

### API tests

1. messages endpoint includes enriched asset metadata inside blocks.
2. assets endpoint:
   - success for resolved asset
   - 404 for unresolved
   - 404 for unknown `asset_id`
   - traversal attempt cannot escape root

### UI smoke tests

1. images render as thumbnails
2. audio renders as players
3. transcripts render as labeled text
4. Claude attachment text renders collapsibly
5. unresolved assets are visible and non-fatal

## Risks and Mitigations

1. Partial ChatGPT pointer resolution.
   - Mitigation: explicit unresolved state; non-fatal rendering.

2. Very large Claude `extracted_content`.
   - Mitigation: collapsible UI + preview clipping + lazy expand.

3. Serving security.
   - Mitigation: asset registry + strict endpoint + no raw path exposure.

4. Performance on long conversations.
   - Mitigation: lazy loading for media-heavy blocks, compact cards, avoid reflow-heavy DOM patterns.

## Open Questions

1. Should unresolved assets be included in markdown export as pointer stubs by default?
2. Should transcript blocks be grouped per user turn or rendered inline as-is?
3. Should we add a UI toggle to hide/show all attachment blocks?

## Definition of Done (V1)

1. Image/audio/transcript/document/file rendering works in chat pane for both providers.
2. Resolver and asset serving are safe and deterministic.
3. Unresolved assets render clearly with no runtime errors.
4. Exporter behavior is explicit and tested.
5. Tests cover parser/API/UI smoke paths.
