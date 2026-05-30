# HarnessLab

**A learning-first agent harness** — a small, runnable codebase for
understanding and implementing your own agent **runtime** (loop, tools,
policy, sessions, compaction, traces, eval), not just calling an LLM API.

HarnessLab is an **experience / lab project**: read the code, run the CLI or
local Web UI, break things safely with `eval` and `replay`, then extend the
harness yourself. It is **not** a drop-in replacement for Cursor or Claude Code.

For motivation, reading order, and “what this is not”, see
[`docs/why-harnesslab.md`](docs/why-harnesslab.md). For how HarnessLab compares
to other agents in 2026, see
[`docs/research/harness-landscape.md`](docs/research/harness-landscape.md).

## What you get

- **Single-process runtime** — `HarnessLoop.run_session` drives a multi-step
  inner loop until `final`, `ask_user`, or `max_steps`.
- **Policy-gated tools** — file, shell, web research, patch, sandbox, MCP, …
  ([`docs/architecture/tool-runtime.md`](docs/architecture/tool-runtime.md)).
- **Sessions as first-class** — persist, list, resume, fork (SQLite).
- **Observable by design** — JSONL traces, context snapshots, eval + replay.
- **Local Web chat** — `harnesslab serve` / `./hl-serve` (TS UI by default when
  built).
- **Multiple model backends** — DeepSeek, Anthropic, OpenAI, Gemini, or offline
  `simple`.

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** (dependency and env management)
- **Optional:** [Bun](https://bun.sh/) to build the TS Web UI (`webui/`)
- **Optional:** provider API keys (see [Configuration](#configuration))

## Quick start

```bash
git clone https://github.com/zhumengzhu/HarnessLab.git   # adjust remote if forked
cd HarnessLab
uv sync
uv run pre-commit install   # one-time: local quality-gate hook

# Offline smoke test (no network):
uv run harnesslab run "hello" --model simple

# With DeepSeek (network):
export DEEPSEEK_API_KEY="***"
uv run harnesslab run "list files in this workspace" --model deepseek --storage sqlite

uv run pytest
```

## Two ways to use it daily

| Path | Best for | Command |
| --- | --- | --- |
| **CLI** | Scripts, eval, learning the loop | `harnesslab run`, `session`, `eval` |
| **Web UI** | Interactive chat, trace inspector | `./hl-serve start` → http://127.0.0.1:8787/ |

**Storage note:** `harnesslab run` defaults to **in-memory** stores (state lost
on exit). `harnesslab serve` and `harnesslab session` use **SQLite** under
`<workspace>/.harnesslab/state.sqlite` so Web and CLI sessions can share history.

### Web chat (`serve`)

```bash
export DEEPSEEK_API_KEY="***"   # or another provider key; see Configuration
./hl-serve start
# open http://127.0.0.1:8787/
```

Lifecycle helper (repo root):

```bash
./hl-serve start      # stop | restart | status | build
./hl-serve build      # bun run build → static_ts/
./hl-serve restart --build   # build then restart (common after webui edits)
./hl-serve            # full help

# Optional secrets: ~/.config/harnesslab/env
# See scripts/hl-serve.example.env
```

**Web UI (TypeScript):** after `cd webui && bun install && bun run build`, `serve`
uses the TS bundle by default (`HARNESSLAB_WEB_UI_VERSION=ts`). If the bundle is
missing, `GET /` returns **503** with build instructions — there is no legacy HTML fallback.

- **Chat** — thinking/tool activity, model picker, slash commands, SSE streaming.
- **Operator surfaces** — Trace / Activity / Proposals tabs, session metadata, budget events (see [`docs/architecture/webui-design.md`](docs/architecture/webui-design.md)).
- **Slash commands** — `/remember`, `/remember-global`, `/compact`, `/skill list`,
  and workspace skills as `/skillname <task>` (Cursor-style; see `skills/*.md`).
- **Sub-agent (Phase 6)** — enable `loop.multi_agent.enabled` in config or Web
  Settings; model may call `spawn_sub_agent`. See
  [`docs/guides/multi-agent.md`](docs/guides/multi-agent.md).
- **Composer** — type `/` for the command palette; SSE streaming for tool steps
  and (with thinking models) token-level reasoning/answer deltas.

Use `--model simple` for offline smoke tests. Bind address must stay on
`127.0.0.1` (localhost only).

Rebuild the frontend:

```bash
./hl-serve build
# or, after webui edits: ./hl-serve restart --build
cd webui && bun install && bun run check && bun test && bun run build
```

Details: [`webui/README.md`](webui/README.md), [`docs/architecture/webui-design.md`](docs/architecture/webui-design.md).

## Configuration

Non-secret defaults live in **`~/.config/harnesslab/config.json`**
([`scripts/harnesslab.config.example.json`](scripts/harnesslab.config.example.json)):
model backend, shell profile, compaction limits, serve port, etc.

Secrets stay in the **environment** (or `~/.config/harnesslab/env` for
`./hl-serve`):

| Backend | Typical env var |
| --- | --- |
| DeepSeek | `DEEPSEEK_API_KEY` (optional: `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`) |
| Anthropic | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Gemini | `GEMINI_API_KEY` or `GOOGLE_API_KEY` |

Web UI model changes can persist back to `config.json` via the model picker.

## CLI overview

Run `harnesslab --help` for the full list. Core commands:

| Command | Purpose |
| --- | --- |
| `run` | New session + agent loop |
| `session` | `ls`, `show`, `resume`, `fork`, `checkpoints`, `rewind` |
| `serve` | Local Web UI |
| `eval` | YAML regression suite |
| `replay` | Re-drive traces, detect divergence |
| `metrics` | Aggregate trace stats |
| `context` | Inspect context snapshots from traces |
| `propose` | Advisory improvement proposals from failure clusters |
| `artifact` | List/show stored artifacts |
| `tui` | Textual terminal UI (experimental) |

Global flags such as `--workspace-root` and `--sqlite-path` go **before** the
subcommand: `harnesslab session --workspace-root . ls`.

### Agent loop (`run`)

Each `run` starts a new session and calls `run_session`: the model may invoke
tools until it returns `final`, `ask_user`, or hits `--max-steps` (default 20).

```bash
uv run harnesslab run "find Python files and summarize" --model deepseek --storage sqlite
uv run harnesslab run "hello" --max-steps 3 --model simple
```

Tool surface and policy: [`docs/architecture/tool-runtime.md`](docs/architecture/tool-runtime.md).

### Model backends

| `--model` | Network | Notes |
| --- | --- | --- |
| `simple` | No | Deterministic teaching parser (`/tool`, `/final`, …) |
| `deepseek` | Yes | Default for `serve` when configured |
| `anthropic` | Yes | Messages API + thinking |
| `openai` | Yes | Responses API |
| `gemini` | Yes | generateContent |

Provider details: [`docs/architecture/provider-expansion.md`](docs/architecture/provider-expansion.md).

### Session management (SQLite)

```bash
uv run harnesslab session --workspace-root . ls
uv run harnesslab session --workspace-root . show ses_abc123
uv run harnesslab session --workspace-root . resume ses_abc123 "keep going" --model deepseek
uv run harnesslab session --workspace-root . fork ses_abc123 --goal "try alt approach"
```

### Eval suite

`harnesslab eval` runs versioned YAML tasks (`eval/tasks/*.yaml`, **15**
shipped), compares to `eval/baseline.json`, writes `eval/reports/latest.json`.

```bash
uv run harnesslab eval
uv run harnesslab eval --task 02_write_then_read
uv run harnesslab eval --update-baseline   # after reviewed behavior change
```

| Exit | Meaning |
| --- | --- |
| 0 | All passed, no baseline regression |
| 2 | Task failure |
| 3 | Baseline regression |
| 64 | Usage error |

See [`eval/README.md`](eval/README.md).

### Replay, metrics & context

Telemetry appends to `<workspace>/.harnesslab/spans.jsonl` (Observability v2 span records).

```bash
uv run harnesslab replay .harnesslab/spans.jsonl
uv run harnesslab replay .harnesslab/spans.jsonl --workspace .
uv run harnesslab metrics .harnesslab/spans.jsonl
uv run harnesslab context .harnesslab/spans.jsonl show
```

| `replay` exit | Meaning |
| --- | --- |
| 0 | All sessions matched |
| 2 | Unreplayable trace |
| 4 | Divergence detected |

Semantic replay compares span forests per turn (preorder DFS); timing,
token counts, and `metrics.context` are volatile; span names, attributes,
tool args, and policy outcomes must match.

### Improvement proposals

`harnesslab propose` mines traces/eval for recurring failures and writes
**advisory** markdown under `proposals/`. Proposals are **never auto-applied**;
see [`AGENTS.md`](AGENTS.md) (Proposal Handling).

```bash
uv run harnesslab propose --trace .harnesslab/spans.jsonl
uv run harnesslab propose --trace .harnesslab/spans.jsonl --eval-report eval/reports/latest.json
```

## Contributing

HarnessLab welcomes PRs that keep the harness **readable and testable**.

1. Read [`AGENTS.md`](AGENTS.md) — architecture rules, proposal policy, quality gate.
2. Before commit: `uv run python scripts/check_package_layout.py`,
   `uv run pytest`, and `uv run ruff check` (also enforced by pre-commit).
   CI (`.github/workflows/ci.yml`) additionally runs `uv build` and Web UI
   tests on push/PR to `main`.
3. Behavior or **Port** contract changes → update `docs/architecture/*` and
   tests in the same PR.
4. Intentional eval baseline changes → `uv run harnesslab eval --update-baseline`
   with review.

Learning-oriented design notes belong in [`docs/why-harnesslab.md`](docs/why-harnesslab.md);
runtime contracts belong in [`docs/architecture/`](docs/architecture/).

## Project layout

- `src/harnesslab/core` — loop, contracts, prompt, compaction, context
- `src/harnesslab/tools` — tool registry and implementations
- `src/harnesslab/policy` — authorization and safety
- `src/harnesslab/session`, `memory` — persistence; `/remember` write path
- `src/harnesslab/providers` — `ModelPort` adapters (multi-vendor)
- `src/harnesslab/web`, `webui/` — HTTP server + TS chat UI
- `src/harnesslab/eval`, `replay`, `improve` — eval, replay, proposals
- `eval/` — tasks, baseline, reports
- `skills/` — workspace skills (`/deep-research`, `/humanizer`, `compact`, …)
- `docs/` — roadmap, architecture, research

## Documentation map

| Doc | Content |
| --- | --- |
| [`docs/README.md`](docs/README.md) | **Documentation index** + learning paths |
| [`docs/why-harnesslab.md`](docs/why-harnesslab.md) | **Why this repo exists** (learning harness) |
| [`docs/roadmap.md`](docs/roadmap.md) | Phased delivery + **What's next** backlog |
| [`docs/architecture/overview.md`](docs/architecture/overview.md) | Runtime map and flows |
| [`docs/architecture/tool-runtime.md`](docs/architecture/tool-runtime.md) | Tools and policy |
| [`docs/guides/web-research-providers.md`](docs/guides/web-research-providers.md) | Web search/fetch backends, pricing, VPN/proxy |
| [`docs/guides/deep-research-landscape.md`](docs/guides/deep-research-landscape.md) | Deep research cross-project comparison and design |
| [`docs/guides/deepseek-thinking-troubleshooting.md`](docs/guides/deepseek-thinking-troubleshooting.md) | DeepSeek thinking 400 / `reasoning_content` replay |
| [`docs/architecture/data-model.md`](docs/architecture/data-model.md) | Messages, traces, sessions |
| [`docs/architecture/compaction.md`](docs/architecture/compaction.md) | Auto/manual compaction |
| [`docs/architecture/web-api.md`](docs/architecture/web-api.md) | HTTP + SSE API |
| [`docs/architecture/webui-design.md`](docs/architecture/webui-design.md) | Chat UX principles |
| [`docs/research/harness-landscape.md`](docs/research/harness-landscape.md) | Industry comparison |
| [`AGENTS.md`](AGENTS.md) | Contributor + AI agent guidelines |

## License

MIT — see [`LICENSE`](LICENSE).
