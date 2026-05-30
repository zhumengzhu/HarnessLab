# DeepSeek thinking mode — troubleshooting

Status: **operator runbook** (updated when replay semantics or error
handling change).

This doc captures recurring production issues with **DeepSeek V4 + thinking
enabled** (`thinking.type: enabled`, Web UI **High / Max**). The same class
of bug has surfaced multiple times in long **tool-heavy** sessions (deep
research, multi-step agent loops).

Related:

- [`../architecture/provider-expansion.md`](../architecture/provider-expansion.md) §6.6.1 — design + replay policy
- [`../architecture/model-parameters.md`](../architecture/model-parameters.md) — operator config
- [`../architecture/compaction.md`](../architecture/compaction.md) — what happens to thinking after `/compact`
- Golden tests: `tests/test_openai_chat_transform.py`, `tests/test_deepseek_provider.py`

---

## Symptom: HTTP 400 on the next model call

Assistant reply in chat (or trace) may look like:

```text
DeepSeek request failed: BadRequestError: Error code: 400 - {'error': {'message':
'The reasoning_content in the thinking mode must be passed back to the API.', ...}}
```

**Meaning:** DeepSeek rejected the **request body**, not your prompt text.
The API saw one or more **historical assistant messages** that originally
had thinking output, but the reserialized wire transcript omitted
`reasoning_content`.

This is **not** a network/proxy failure. `harnesslab check network` will
still pass.

---

## Why it happens (vendor rule)

In thinking mode, DeepSeek treats reasoning as part of the conversation
state — similar to Anthropic thinking blocks in a tool loop.

| Rule (simplified) | HarnessLab implication |
| --- | --- |
| Assistant message that issued `tool_calls` **must** include `reasoning_content` when resent | Persist as `Message.reasoning_text`; replay on wire as `reasoning_content` |
| Same turn may include **non-tool** assistant rows with thinking (plan / intermediate assistant) | Those rows also need replay when thinking was captured |
| New user turn after a prior tool loop | Historical tool assistants **still** need reasoning — not only the open loop |
| Plain chat, thinking off | Prior reasoning can be omitted on the next user turn |

Official reference: [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode).

---

## How HarnessLab implements replay

```mermaid
sequenceDiagram
  participant Loop as HarnessLoop
  participant DS as DeepSeekModel
  participant TX as openai_chat transform
  participant API as DeepSeek API

  Loop->>DS: decide(session)
  DS->>TX: serialize_messages(composed, session)
  Note over TX: For each conversation block origin session:msg_id,<br/>inject reasoning_content from Message.reasoning_text
  TX->>API: POST /chat/completions (messages[])
  API-->>DS: assistant + reasoning_content (+ tool_calls)
  DS-->>Loop: Decision + reasoning_text in last_call_meta
  Loop->>Loop: append Message(reasoning_text=...)
```

**Storage:** `Message.reasoning_text` (SQLite column `messages.reasoning_text`).

**Wire injection:** `ComposedPrompt.as_openai_messages(reasoning_by_message_id=…)`
maps each assistant block’s `origin` (`session:<msg_id>`) to persisted
reasoning. The `openai_chat` transform builds that map from the session.

**Do not** infer reasoning from span events in the Web UI — completed
`llm.generate` span `metrics` is the canonical source for displayed thoughts; replay uses
**persisted messages**, not trace JSONL.

---

## Recurring failure modes (lessons learned)

These caused repeated 400s in the field before fixes landed:

| Failure mode | What went wrong | Fix / guard |
| --- | --- | --- |
| **Index-based replay** | Injecting `reasoning_content` by counting assistant+tool rows; one missing `reasoning_text` desynced all following steps | Replay by **`session:msg_id`** via composer origins |
| **Tool-only replay** | Only tool-call assistants got `reasoning_content`; plan/assistant steps with thinking were skipped | Inject for **every** assistant message that has `reasoning_text` |
| **Missing persistence** | Stream showed thinking in UI but `reasoning_text` NULL in DB (older builds / edge paths) | Loop stores `_model_reasoning_text()` on every assistant append; stream deltas are a fallback. **Tool assistants in thinking mode** persist `reasoning_text=""` when capture is empty so replay can send `reasoning_content: ""` |
| **Compaction** | Prefix turns summarized away; tail keeps `reasoning_text` | See [`compaction.md`](../architecture/compaction.md) — compacted thinking is **not** replayed |
| **Corrupt session history** | Session created under a buggy build: tool assistant exists, `reasoning_text` empty | Replay now sends empty `reasoning_content` for tool rows when thinking is on; if 400 persists, fork session |

When adding a new thinking model on the OpenAI-chat wire shape, extend
**fixture tests first** — live API keys are not required for replay coverage.

---

## Operator recovery

### 1. Upgrade and restart

Ensure you are on a build that includes msg-id replay (see git log /
release notes for `reasoning_by_message_id` / openai_chat transform changes).

```bash
./hl-serve restart --build
```

Use `--build` when you changed the TS Web UI (`webui/`); it rebuilds the bundle
then restarts serve. Config-only or Python-only changes can use `./hl-serve restart`.

### 2. Retry in the same session

Send **`continue`** (or a short follow-up). If all historical assistant
rows still have `reasoning_text` in the database, the next request should
 succeed.

### 3. If 400 persists — check for corrupt history

Inspect assistant tool rows missing reasoning (replace `ses_xxx` and DB path):

```bash
sqlite3 ~/.harnesslab/sessions.db "
  SELECT id, role,
         CASE WHEN reasoning_text IS NULL OR reasoning_text = '' THEN 'MISSING' ELSE 'ok' END AS reasoning,
         length(content) AS content_len
  FROM messages
  WHERE session_id = 'ses_xxx' AND role = 'assistant'
  ORDER BY ord;
"
```

If any **MISSING** row has `tool_calls` (or you were in thinking mode for
that step), that session cannot be safely continued on DeepSeek thinking —
the API requires content we no longer have.

**Workarounds:**

- **Fork** the session (Web UI or CLI) and paste a short summary of progress
  into a **new** user message.
- Start a **new session** for the remaining work.
- Temporarily set thinking **Off** (`model.deepseek.thinking: disabled`) —
  only helps if you also avoid resending broken history (usually means new
  session).

### 4. Prevention for long research

- Prefer **`/deep-research <topic>`** so the skill budget applies.
- Use **`/remember`** for facts that must survive `/compact`.
- After **`/compact`**, assume old thinking blocks are gone from the wire.
- For daily tool-heavy work with fewer 400 surprises, consider **thinking
  Off** and enable **High/Max** only for research sessions.

---

## Debugging for contributors

| Check | Where |
| --- | --- |
| Request messages include `reasoning_content` | `llm.generate` span `metrics.api_messages`, or log in `DeepSeekModel._request_body` |
| Reasoning persisted | `GET /api/sessions/{id}` → `messages[].reasoning_text` |
| Transform tests green | `uv run pytest tests/test_openai_chat_transform.py tests/test_deepseek_provider.py` |
| UI thought duplication | Web UI reads `llm.generate` span metrics only — not decision attrs on other spans |

**Contract rule:** changes to replay behavior **must** update this doc,
`provider-expansion.md` §6.6.1, and the tests above in the same PR.

---

## Quick reference: error string → action

| Error substring | Likely cause | First action |
| --- | --- | --- |
| `reasoning_content in the thinking mode must be passed back` | Missing replay on wire | Restart, retry; then inspect `reasoning_text` in SQLite |
| `context_length_exceeded` / context length | Token overflow | `/compact` or shorter goal; not a replay bug |
| `DeepSeek request failed: APIConnectionError` | Network / proxy | `harnesslab check network`, proxy env |
