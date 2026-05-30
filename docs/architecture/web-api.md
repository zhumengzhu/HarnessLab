# Web HTTP API

Localhost-only JSON + SSE API served by `harnesslab serve` /
`./hl-serve`. Binds **`127.0.0.1`** only (not a production web app).

Product UX (Thinking blocks, slash commands, SSE semantics) is documented in
[`webui-design.md`](webui-design.md). This document is the **contract
reference** for integrators and TS WebUI maintainers.

## General rules

- **Base URL:** `http://127.0.0.1:{port}/` (default port from config, often `8787`).
- **Content-Type:** JSON request/response unless SSE (see below).
- **Errors:** JSON body `{ "error": "<message>" }` with 4xx/5xx status.
- **Secrets:** never returned from `/api/settings` or `/api/health`.
- **Session lock:** concurrent POSTs for the same `session_id` are serialized.

## Static assets

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/` | Chat SPA (Vite bundle under `web/static_ts/` after `./hl-serve build`) |
| `GET` | `/assets/*` | Vite hashed bundles (TS UI) |

If the TS bundle is missing, `GET /` returns **503** with build instructions.
Legacy `web/static/` was removed in Phase E; `HARNESSLAB_WEB_UI_VERSION=legacy`
is rejected at startup.

## Read endpoints

### `GET /api/health`

Liveness + active model snapshot.

```json
{
  "ok": true,
  "model": "deepseek",
  "model_id": "deepseek-v4-flash",
  "model_label": "DeepSeek V4 Flash",
  "workspace": "/path/to/workspace",
  "runtime_context_tokens": 128000
}
```

### `GET /api/settings`

Operator config snapshot (no secrets) + raw config file text for Advanced UI.

```json
{
  "settings": { "...": "operator snapshot" },
  "config_source": "{ ... config.json text ... }"
}
```

### `GET /api/models`

Catalog entries for the model picker.

```json
{
  "models": [
    {
      "backend": "deepseek",
      "model_id": "deepseek-v4-flash",
      "label": "DeepSeek V4 Flash",
      "thinking_modes": ["disabled", "enabled"]
    }
  ]
}
```

### `GET /api/composer/commands`

Slash palette: built-ins + workspace skills.

```json
{
  "commands": [
    {
      "name": "remember",
      "usage": "/remember <text>",
      "description": "Save a note to this session's memory",
      "insert": "/remember ",
      "kind": "builtin"
    }
  ],
  "skills": [
    {
      "name": "compact",
      "usage": "/compact",
      "description": "Force context compaction",
      "insert": "/compact",
      "kind": "skill"
    }
  ]
}
```

Skills are discovered from `skills/*.md`. Workspace skills appear as
`/skillname` direct invoke (Cursor-style).

### `GET /api/skills`

List installed skills plus catalog-only entries (when configured).

Query: optional `q` for case-insensitive search.

```json
{
  "skills": [
    {
      "name": "compact",
      "description": "...",
      "tags": ["context"],
      "scope": "catalog",
      "path": null,
      "catalog_id": "compact"
    }
  ]
}
```

### `GET /api/skills/preview`

Markdown preview for an installed skill or catalog entry.

Query: `name=<skill>` or `catalog_id=<id>` (one required).

### `POST /api/skills/install`

Operator-initiated install. Body:

```json
{ "catalog_id": "compact", "scope": "workspace" }
```

or `{ "source": "/path/to/skill.md", "scope": "user" }`.

### `GET /api/sessions`

List sessions (newest first).

Query: `limit` (default `50`), optional `status`.

```json
{
  "sessions": [
    {
      "id": "ses_abc",
      "goal": "...",
      "title": "...",
      "status": "done",
      "turn_count": 2,
      "step_count": 5,
      "created_at": "...",
      "last_step_at": "...",
      "parent_session_id": null
    }
  ]
}
```

### `GET /api/sessions/{id}`

Session metadata + full message list + `memory_notes`.

```json
{
  "session": { "...": "metadata", "memory_notes": ["line1"] },
  "messages": [
    {
      "id": "msg_1",
      "role": "user",
      "content": "hello",
      "reasoning_text": null,
      "tool_calls": null
    }
  ]
}
```

Internal `tool` / `system` rows are included for model continuity; Simple
Chat UI may hide them visually.

### `PATCH /api/sessions/{id}`

Update session metadata (sidebar rename, per-session model override).

**Rename:**

```json
{ "title": "My research thread" }
```

- `title`: trimmed, max **60** characters (`TITLE_MAX_LEN`).

**Per-session model** (Web UI model picker when a session is selected):

```json
{
  "model_backend": "deepseek",
  "model_id": "deepseek-v4-pro",
  "effort": "max"
}
```

- Does **not** write `~/.config/harnesslab/config.json`; override is stored on the session row.
- Clear override (revert to global default): `{ "model_backend": null }`.
- At least one of `title` or model fields is required per request.
- Before each turn the runtime binds `loop._model` from the effective config (global or session overlay).

Response: `{ "session": { ...SessionSummary fields including model_backend, model_id, model_effort... } }`

### `GET /api/sessions/{id}/trace`

Completed spans for the session (read from `.harnesslab/spans.jsonl`, filtered by
`session_id`). The Web UI groups the flat list by `trace_id` (one group = one
turn). Shape normative in [`data-model.md`](data-model.md) § SpanRecord.

```json
{
  "session_id": "ses_abc",
  "spans": [
    {
      "trace_id": "tr_…",
      "span_id": "sp_…",
      "parent_span_id": null,
      "name": "harnesslab.turn",
      "kind": "internal",
      "session_id": "ses_abc",
      "turn_index": 0,
      "start_time": "2026-05-31T12:00:00.000Z",
      "end_time": "2026-05-31T12:00:05.000Z",
      "duration_ms": 5000,
      "status": "ok",
      "resource": {
        "service.name": "harnesslab",
        "deployment.environment": "local"
      },
      "attributes": { "harnesslab.session.id": "ses_abc" },
      "events": [],
      "metrics": {}
    }
  ]
}
```

In-flight spans (`span.started` only) are **not** included — use SSE during an
active turn, or merge client-side with stream events (see [`webui-design.md`](webui-design.md)).

### `GET /api/sessions/{id}/trace/jsonl`

Same spans as `…/trace`, returned as a single JSONL string plus metadata:

```json
{
  "session_id": "ses_abc",
  "spans_path": "/path/to/.harnesslab/spans.jsonl",
  "trace_path": "/path/to/.harnesslab/spans.jsonl",
  "line_count": 42,
  "jsonl": "{…}\n{…}\n"
}
```

(`trace_path` is an alias of `spans_path` for backward-compatible clients.)

### `GET /api/sessions/{id}/context`

Latest `ContextSnapshot` from the most recent `llm.generate` span
(`SpanRecord.metrics.context`) for the session.

### `GET /api/proposals?status=open|all`

Proposal headers from `proposals/` directory.

### `GET /api/proposals/{id}`

Full proposal markdown + YAML front-matter metadata.

## Write endpoints

### `POST /api/sessions`

Start a new session and run the first turn.

Body:

```json
{
  "message": "user goal or first message",
  "max_steps": 20,
  "stream": false
}
```

Response (non-stream): turn payload (see **Turn response shape**).

### `POST /api/sessions/{id}/messages`

Continue an existing session.

Body: same as `POST /api/sessions`.

### `POST /api/sessions/{id}/steer`

Inject a user message into the **current inner turn** (Web UI Steer). The message
is queued in `TurnSteerBuffer` and appended to `session.messages` before the
next model call in the active `run_session` loop (step index ≥ 1).

```json
{ "message": "Stop searching — summarize what you have." }
```

- Returns `{ "ok": true, "queued": 1 }` when a turn is active for the session.
- Returns **409** `{ "error": "no active turn for session" }` when idle (client
  may fall back to queuing the next turn).
- Emits trace event `user_steer_received`.

### `POST /api/sessions/{id}/fork`

Fork a session branch.

```json
{ "goal": "optional new goal" }
```

Response: `{ "session": { ... new fork metadata ... } }`

### `GET /api/sessions/{id}/checkpoints`

List checkpoint metadata for a session (SQLite storage only).

Response:

```json
{
  "session_id": "ses_abc",
  "checkpoints": [
    {
      "id": "cp_001",
      "session_id": "ses_abc",
      "tool_name": "write_file",
      "created_at": "2026-05-26T12:00:00+00:00"
    }
  ]
}
```

### `GET /api/sessions/{id}/checkpoints/{checkpoint_id}`

Preview file diffs that a rewind would apply.

Response includes `changes[]` with `{ path, current, restore_to }`.

### `POST /api/sessions/{id}/rewind`

Restore workspace files from a checkpoint. Requires explicit confirmation.

```json
{
  "checkpoint_id": "cp_001",
  "confirm": true
}
```

Response: `{ "session_id", "checkpoint_id", "paths", "preview" }`

### `POST /api/model`

Switch active model backend; persists to `~/.config/harnesslab/config.json`.

```json
{
  "backend": "deepseek",
  "model_id": "deepseek-v4-pro",
  "effort": "high"
}
```

At least one of `backend` or `model_id` is required.

### `POST /api/proposals/{id}/status`

Guarded proposal lifecycle transition (`open` → `accepted|rejected|superseded`).

```json
{
  "status": "accepted",
  "decision_note": "human rationale",
  "superseded_by": "",
  "confirm_reviewed": true,
  "confirm_pytest_green": true,
  "confirm_eval_no_regression": true
}
```

### `POST /api/proposals/gates/run`

Run local quality gate for proposal UX.

```json
{ "gate": "pytest" }
```

or `"eval"`. Returns bounded stdout/stderr in `result`.

## Turn response shape (JSON)

Returned by non-stream POSTs and the SSE `done` event:

```json
{
  "session": { "...": "metadata" },
  "reply": "assistant final text",
  "messages": [ "... persisted user/assistant rows ..." ],
  "tool_cards": [ "... structured tool results for this turn ..." ],
  "context": { "... ContextSnapshot ..." }
}
```

## Server-Sent Events (SSE)

Request streaming by setting `"stream": true` in the POST body **or**
header `Accept: text/event-stream`.

Response: `Content-Type: text/event-stream; charset=utf-8`

Normative span shapes: [`data-model.md`](data-model.md) § SpanRecord,
[`observability-v2.md`](observability-v2.md) § D9.

### Span lifecycle (Observability v2)

| Event | Payload | Persisted to `spans.jsonl` | Purpose |
| --- | --- | --- | --- |
| `span.started` | `{ trace_id, span_id, parent_span_id, name, kind, session_id, turn_index, attributes }` | No | In-flight waterfall / Live Turn / Activity |
| `span.event` | `{ trace_id, span_id, name, attributes, time }` | No | Instant facts (budget, policy deny, steer) |
| `span.completed` | Full `SpanRecord` | Yes (one JSON line per span) | Trace Tab, replay, metrics |
| `span.link` | `{ trace_id, span_id, linked_trace_id, linked_span_id, attributes }` | No | Sub-agent cross-trace link |

Sub-agent turns may include `child_session_id` on `span.started` / `span.completed`
when the span belongs to a child session watched by the parent stream.

### Turn completion and token deltas

| Event | Payload | Persisted | Purpose |
| --- | --- | --- | --- |
| `reasoning_delta` | `{ "text": "...", "step_index": 0 }` | No | Token-level thinking (DeepSeek first) |
| `assistant_delta` | `{ "text": "...", "step_index": 0 }` | No | Token-level answer text |
| `done` | Turn response shape (see above) | N/A | Turn complete |
| `error` | `{ "message": "..." }` | N/A | Turn failed |

### Wire example

```text
event: span.started
data: {"trace_id":"…","span_id":"…","name":"llm.generate","kind":"client","session_id":"ses_…","turn_index":0,"attributes":{}}

event: span.completed
data: {"trace_id":"…","span_id":"…","name":"llm.generate","duration_ms":1234,"metrics":{...},"attributes":{...}}

event: assistant_delta
data: {"text":"partial","step_index":0}

event: done
data: {"session":{...},"reply":"..."}
```

**Ordering:** span lifecycle events for the turn precede the terminal `done`
frame (see `tests/test_web_server.py::test_web_sse_stream_event_ordering`).

v1 `event: trace` with flat `TraceEvent` / `event_type` payloads is **retired**
at Observability v2 cutover.

## Slash commands (transport)

Slash commands are **plain user message text** interpreted by the loop
(not separate HTTP routes):

| Command | Effect |
| --- | --- |
| `/remember <text>` | Session memory write |
| `/remember-global <text>` | Workspace memory write |
| `/compact` | Manual compaction (no model call) |
| `/skillname` | Pin workspace skill |
| `/skill list` | List skills |

## Stability

- Breaking API changes require a note in this file and a TS client update.
- Trace payload shapes are normative in [`data-model.md`](data-model.md).
- Localhost binding and no-auth are intentional; do not expose without a
  separate security RFC.

## Related docs

- [`webui-design.md`](webui-design.md) — UX principles
- [`frontend-ts-migration.md`](frontend-ts-migration.md) — TS client layout
- [`overview.md`](overview.md) — runtime map (non-HTTP)
