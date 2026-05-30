# Compact context

Use **`/compact`** in chat (or `harnesslab run`) to force a context compaction
without waiting for the automatic threshold.

## When to use

- Long research sessions where the context ring is high but the model has not
  hit the auto-compaction threshold yet.
- Before a large new task in the same session when you want a clean summary
  of prior work.

## What happens

1. Older messages are summarized into one `<system-reminder>` block.
2. The last **K** messages are kept verbatim (`compaction_keep_last_messages`
   in operator config; default 20).
3. A **`context.compact`** span is recorded with `harnesslab.compaction.trigger:
   manual` (and before/after message counts).

## Thinking / reasoning after compact

- **Kept** recent messages still carry `reasoning_text` on disk; DeepSeek tool
  loops still replay `reasoning_content` when required.
- **Compacted-away** turns drop raw thinking from the wire; the summary (LLM
  or deterministic) may include clipped thinking in the transcript fed to the
  summarizer.
- Durable notes belong in **`/remember`** or **`/remember-global`**, not in
  thinking blocks.

Automatic compaction still runs before each model call when estimated tokens
exceed `compaction_threshold_tokens`.
