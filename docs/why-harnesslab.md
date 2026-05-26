# Why HarnessLab?

HarnessLab is a **learning project** for understanding and building an
**agent harness** — the runtime around the model, not the model itself.

Industry surveys and post-mortems on tools like Claude Code suggest that most
of the "magic" in a coding agent lives in the harness: the loop, tool policy,
context compaction, session store, traces, eval, and recovery — not in the raw
LLM call. HarnessLab lets you **read, run, and change** that layer in a small,
testable Python codebase.

## What you will learn

Working through this repo (and the phased roadmap in [`roadmap.md`](roadmap.md)),
you can see how a minimal but real harness is put together:

| Topic | Where it lives |
| --- | --- |
| Multi-step agent loop (`final` / `tool` / `ask_user`) | `src/harnesslab/core/loop.py` |
| Ports & adapters (stable contracts) | `src/harnesslab/core/contracts.py`, `providers/` |
| Policy-gated tools | `src/harnesslab/policy/`, `tools/` |
| Prompt composition | `src/harnesslab/core/prompt/` |
| Sessions, fork, checkpoints | `src/harnesslab/session/` |
| Context compaction | `src/harnesslab/core/compaction.py` | [`architecture/compaction.md`](architecture/compaction.md) |
| Traces, replay, divergence | `telemetry/`, `replay/` |
| Regression eval | `eval/`, `harnesslab eval` |
| Local Web UI (SSE, thinking, slash commands) | `web/`, `webui/` |

The design goal is **clarity over cleverness**: every important action should
be observable in JSONL traces and covered by tests where practical.

## What HarnessLab is not

- **Not a ChatGPT wrapper** — the product is the loop and contracts, not a
  single prompt.
- **Not a framework you import to build any agent in five lines** — there is
  no stable public SDK yet; the code is meant to be read and forked.
- **Not a replacement for Cursor, Claude Code, or OpenClaw** — those are
  mature products. HarnessLab is a **lab bench** to compare approaches; see
  [`research/harness-landscape.md`](research/harness-landscape.md).
- **Not production SaaS** — single-process, localhost-first, explicit
  operator trade-offs.

## Suggested reading order

1. [`architecture/overview.md`](architecture/overview.md) — runtime map.
2. Run `uv run harnesslab run "hello" --model simple` and inspect
   `.harnesslab/trace.jsonl`.
3. [`architecture/tool-runtime.md`](architecture/tool-runtime.md) — safety model.
4. [`architecture/data-model.md`](architecture/data-model.md) — messages, trace
   events, sessions.
5. `uv run harnesslab eval` — see invariants as YAML tasks.
6. [`roadmap.md`](roadmap.md) — what shipped vs planned.

## How to use it as a build-your-own-agent exercise

Typical experiments people run on top of HarnessLab:

- Add a tool or tighten policy → watch trace + eval tasks.
- Swap `ModelPort` (DeepSeek, Anthropic, …) without touching the loop.
- Change compaction or memory rules → confirm replay/eval still pass.
- Extend the Web UI while keeping trace as the engine ([`architecture/webui-design.md`](architecture/webui-design.md)).

If you change a **stable Port** or data contract, update architecture docs and
tests in the same change — see [`AGENTS.md`](../AGENTS.md).

Documentation index: [`README.md`](README.md).
