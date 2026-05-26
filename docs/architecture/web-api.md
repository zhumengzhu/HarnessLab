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
| `GET` | `/` | Chat SPA (`web/static_ts/` when built, else `web/static/`) |
| `GET` | `/static/*` | Legacy static files |
| `GET` | `/assets/*` | Vite hashed bundles (TS UI) |

UI version: `HARNESSLAB_WEB_UI_VERSION=ts|legacy` (default `ts` when bundle exists).

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

### `GET /api/sessions/{id}/trace`

Filtered trace events for the Advanced trace panel (tool/step subset).

```json
{
  "session_id": "ses_abc",
  "events": [
    {
      "event_type": "model_call",
      "payload": { "decision_kind": "tool", "context": {}, "prompt_blocks": [] }
    }
  ]
}
```

### `GET /api/sessions/{id}/context`

Latest `ContextSnapshot` from the most recent `model_call` in trace.

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

### `POST /api/sessions/{id}/fork`

Fork a session branch.

```json
{ "goal": "optional new goal" }
```

Response: `{ "session": { ... new fork metadata ... } }`

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

### Event types

| Event | Payload | Purpose |
| --- | --- | --- |
| `trace` | Trace event JSON (subset of `TOOL_PANEL_EVENT_TYPES`) | Step / model_call / tool activity |
| `reasoning_delta` | `{ "text": "...", "step_index": 0 }` | Token-level thinking (DeepSeek first) |
| `assistant_delta` | `{ "text": "...", "step_index": 0 }` | Token-level answer text |
| `done` | Turn response shape (above) | Turn complete |
| `error` | `{ "message": "..." }` | Turn failed |

Wire format:

```text
event: trace
data: {"event_type":"step_started","payload":{...}}

event: reasoning_delta
data: {"text":"partial","step_index":0}

event: done
data: {"session":{...},"reply":"..."}
```

SSE deltas are **not** persisted to `trace.jsonl` (ephemeral UI only).
See [`data-model.md`](data-model.md).

Common `trace` event types consumed by Chat UI: `step_started`,
`model_call_started`, `model_call`, `decision_made`, `tool_executed`,
`tool_denied`, `compaction_started`, `compaction_completed`.

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
