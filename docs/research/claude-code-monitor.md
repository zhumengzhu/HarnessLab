# Claude Code: Monitor & Agent View — Research Note

> **Status:** External research, May 2026. **Not a HarnessLab spec.** Mapped
> to HarnessLab's existing contracts at the end for future planning.
> Sources cited inline; all linked-but-uncited claims are corroborated by
> the references listed in §5.

Claude Code ships *two* features that get described as "monitoring" in
its 2026 docs and ecosystem. They are easy to confuse but solve very
different problems. This note pulls them apart, summarises what each
actually does, and notes how the same patterns could land in HarnessLab.

---

## 1. The two "monitor" features at a glance

| Feature | Surface | Introduced | What it really is |
|---|---|---|---|
| **Monitor tool** | Built-in tool inside one session | v2.1.98 (Apr 9, 2026) | A non-blocking `tail -f`–style subprocess whose stdout is streamed back to the model as notifications. Lets the agent *react to log lines / file events / CI status changes* without polling. |
| **Agent view** | Out-of-session CLI dashboard | v2.1.139 (May 2026, research preview) | A live terminal dashboard (`claude agents`) showing every running, blocked, or finished background Claude Code session. Includes a per-user supervisor process that hosts background sessions. |

They compose: agent view shows the *state of sessions*; monitor tool runs
*inside* a session to give that session continuous visibility into a
process. A long-running background session might itself be sitting on a
monitor that is waiting for a deployment to fail.

There is also a third, **third-party** "monitor" — the open-source
[`Glsme/agent-monitor`](https://github.com/Glsme/agent-monitor) desktop
app, which polls `~/.claude/teams/` and `~/.claude/tasks/` to draw a
pixel-art office for Claude Code agent teams. Pretty, but
informational only — not part of the official surface.

---

## 2. Monitor tool — deep dive

### 2.1 What it does

The Monitor tool lets the model spawn a background subprocess and
receive **every line of stdout as a notification inside the
conversation**, with the main loop free to keep working. Compared with
the existing `Bash run_in_background` flag (which produces one exit-time
notification), Monitor is a continuous event stream.

Typical phrasing from the agent's side:

> *"Watch `app.log` and tell me when an ERROR or Traceback appears."*

Claude writes a small watch script (`tail -f app.log | grep
--line-buffered -E "ERROR|Traceback|FAILED"`), runs it via Monitor, and
each matching line is pushed back into the conversation as a
notification. Lines emitted within a ~200 ms window batch into a single
notification. Stderr is redirected to a file rather than streamed.

### 2.2 Parameters

| Param | Purpose | Default / cap |
|---|---|---|
| `description` | Short label shown on every notification | required |
| `command` | Shell script whose stdout becomes the event stream | required |
| `timeout_ms` | Kill the watch after this many ms | 300_000 (5 min); max 3_600_000 (1 h) |
| `persistent` | If `true`, runs for the whole session (`TaskStop` to cancel) | `false` |

Permissions: **reuses the Bash allow/deny rules** — there is no separate
Monitor allowlist, so anything you have already locked down for `Bash`
is locked down for Monitor automatically.

Availability: Anthropic's first-party Claude only — *not* available on
Amazon Bedrock, Google Vertex AI, Microsoft Foundry, or when
`DISABLE_TELEMETRY` / `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` is set.

Lifecycle: **session-scoped.** Every monitor dies when the session
exits. If the user needs the watch to outlive a session, the docs
explicitly point them to an external supervisor (systemd, CI, etc.).

### 2.3 Why it matters

The pattern Monitor formalises is **event-driven inversion of control
for an LLM agent**. Without it, the agent's only options for "is the
build done?" are:

- A blocking `Bash` call that locks the loop for the full build,
- A polling `/loop` (or `cron`-like task) that re-spends tokens every
  tick to ask the same question, or
- Manual hand-offs back to the user.

Monitor lets the model *attach* to the existing event source and only
spend tokens when something interesting actually happens. Ecosystem
write-ups consistently frame it as the missing piece between "one-shot
bash" and "ChatOps-style watch."

Concrete use cases that recur across the third-party guides:

1. **Tail logs while debugging.** Agent edits a file and watches the
   server log for the next error.
2. **Watch a dev server boot.** Agent fixes a bug; monitor surfaces
   compilation errors as they appear.
3. **Track CI / PR status.** A polling script (`gh pr checks --watch
   ...`) emits a line per status change; the agent reacts on transition,
   not on a fixed timer.
4. **File-system watchers.** `inotifywait` / `fswatch` lines route into
   the conversation as events.

### 2.4 Comparison the docs draw themselves

| | Monitor | `/loop` / scheduled tasks | `Bash run_in_background` |
|---|---|---|---|
| Trigger | Each stdout line from a process | Timer interval | One exit event |
| Cadence | Continuous stream | ≥ 1 minute | Once |
| Script lifecycle | Managed by Monitor (session-scoped) | Re-runs Claude each fire | Bash subprocess |
| Best for | Streaming logs, file watchers, low-frequency async events | Periodic full status check that needs reasoning | Fire-and-forget command |

---

## 3. Agent view — deep dive

### 3.1 What it does

`claude agents` (v2.1.139+) opens a full-terminal dashboard listing
every Claude Code session by state — *running*, *blocked on user input*,
or *done*. From inside it you can:

- See each session's name, current activity, and how long ago it last
  changed.
- Pin a background session (`Ctrl+T`) so it survives idle and
  auto-restarts after Claude Code updates instead of dying with the
  terminal.
- Rename a session (`Ctrl+R`).
- Detach / close a session (`←`) while preserving its state.
- Open a session in the editor (`v`).

The count of sessions awaiting input also shows in the terminal **tab
title**, so the developer can see "3 agents need me" without bringing
the dashboard forward.

### 3.2 Supervisor architecture

Behind agent view sits a **per-user supervisor process** that hosts
background sessions independently of any terminal. Key properties from
the docs:

- Started automatically the first time you background a session or open
  agent view; the user does not manage it directly.
- Each background session is **its own Claude Code process**, owned by
  the supervisor.
- A session counts as "active work" — and therefore stays alive — when
  it has a terminal attached, is waiting for input, **or has a running
  background shell command / subagent / workflow / monitor**. So a long
  dev-server-tailing monitor (§2) is enough to keep its session
  resident.

Pinning is the explicit lever for "I want this session to survive even
when idle" and for "auto-restart on Claude Code upgrades".

### 3.3 What it's not

Agent view is the **process-level dashboard**, not a per-session
streaming UI. It tells you that session `refactor-auth` last changed 12
minutes ago and is blocked on input; it doesn't show what tools that
session is running right now. For per-step inspection you still open
the individual session.

It is also **research preview**: keyboard shortcuts and screens are
explicitly subject to change.

### 3.4 Companion CLI surface

The same release wave shipped flags useful for production background
workers:

| Flag | Purpose |
|---|---|
| `--bg` | Run a session in the background instead of attaching the terminal. |
| `/goal "…"` | Set a persistent objective; Claude loops across turns until it is met (OpenAI's Codex Goals is the equivalent feature shipped May 2026). |
| `--permission-mode`, `--fallback-model`, `--add-dir` | Per-session policy + provider fallback + workspace mount configuration (May 2026). |

Combined, these turn a chat assistant into something closer to a
"scheduled background worker that pings you when stuck" — which is
exactly what the agent-view dashboard is built around.

---

## 4. Mapping to HarnessLab today

HarnessLab does **not** have either feature. Here is how each would
land if/when we decided to ship it, mapped onto our existing
contracts.

### 4.1 Monitor tool ↔ HarnessLab tools / loop

| Concern | Today | A "Monitor" port |
|---|---|---|
| Tool dispatch | `ToolPort.execute(call) → ToolResult` is **synchronous**: one call, one normalized result. | Needs an async surface; the cleanest add is a sibling `StreamingToolPort.execute_stream(call) -> Iterator[ToolStreamEvent]`. |
| Loop integration | Loop processes one `Decision`, one tool result, then re-calls model. | Loop would need an "interject" path: a streaming tool can deliver `ToolStreamEvent` items that *append* observations to the next model call's prompt, without re-running the model on every line. |
| Trace | Completed **`tool.{name}`** span records `output_preview` in metrics. | Streaming could add volatile span events (same replay family as `output_preview`). |
| Policy | `PolicyPort.allow_tool(call)` decides once. | Same call gate, plus a per-line size cap and a hard max-events-per-session bound to prevent log-flood DoS on the context. |
| Replay | `ReplayModel` deterministically reproduces decisions from **`llm.generate`** span attrs. | Streaming tools are non-deterministic by definition. Either: (a) record the stream as span events and replay from spans, or (b) mark streaming-tool tasks as **excluded from semantic compare**. Option (a) matches the project's "spans are source of truth" stance. |
| Sandbox / shell allowlist | `run_shell_safe` allowlist + `dev`/`read_only`/`strict` profiles. | Reuse Claude Code's "Monitor inherits Bash rules" decision — a `run_shell_monitor` would inherit `run_shell_safe`'s policy, no new allowlist. |

**Why this is non-trivial:** today our `ModelPort.decide(session,
user_input) -> Decision` plus a synchronous tool result is the entire
loop contract. Streaming tools force a second loop edge (model ↔ tool
stream) that does not exist now. This is a Phase 5+ design decision,
not a Phase 5 line item.

### 4.2 Agent view ↔ HarnessLab session surface

Agent view maps onto contracts that **already exist** in HarnessLab:

| Concern | HarnessLab today | Gap to "agent view" |
|---|---|---|
| Per-session lifecycle | `Session.status ∈ {pending, running, waiting_user, done, failed, aborted}` plus `step_count` / `last_step_at` / `parent_session_id` / `title`. | None — exact same vocabulary. |
| List sessions | `SessionStorePort.list(*, limit, status)` + `harnesslab session ls`. | None — already newest-first with status filter. |
| Background work | Web UI runs in-process; CLI is foreground. | **Missing:** no per-user supervisor process, no way for a session to keep running detached from its terminal. |
| Multi-session dashboard | Web UI + CLI both show one session at a time. | **Missing:** there is no "fleet view" terminal UI; `session ls` is a one-shot table. |
| Pinning / auto-restart | n/a | **Missing.** |
| Tab-title badge ("N sessions need you") | n/a | **Missing**, but cheap to add in the Web UI (favicon/title) once a fleet endpoint exists. |
| Persistence of session state across restarts | SQLite store already persists everything. | None — sessions survive across CLI invocations by construction. |

**The "supervisor" question is the actual decision.** Agent view's
killer feature is not the TUI; it's the per-user supervisor process
that owns background sessions. HarnessLab's current model is "the CLI
*is* the runtime; no daemon". A supervisor changes that — it is
adjacent territory to the Phase 6 "background / async sub-agents" shape
that the multi-agent RFC already classifies as out of scope for the
initial PoC.

If we ever want this, the minimum viable form is probably:

1. A long-lived `harnesslab serve --supervisor` process that hosts a
   thread/process per active session (existing Web UI already runs the
   loop in-process; this is closer than it sounds).
2. A `harnesslab agents` CLI that talks to the supervisor over a
   Unix socket and renders the same fleet table the Web UI shows.
3. `harnesslab session run --bg <goal>` as the spawn surface.

That is squarely a Phase 6+ piece, and only worth doing once Phase 5.3
plan mode + Phase 6 PoC have a real reason for multiple sessions to be
live at once.

---

## 5. References

- [Manage multiple agents with agent view](https://code.claude.com/docs/en/agent-view.md) — official agent view + supervisor docs.
- [Tools reference — Monitor](https://code.claude.com/docs/en/tools-reference) — official Monitor tool entry.
- [Claude Code 2.1 Agent View & `/goal`: Autonomous Dev Guide 2026 (dev.to)](https://dev.to/akaranjkar08/claude-code-21-agent-view-goal-autonomous-dev-guide-2026-31hk) — practitioner walkthrough of `claude agents`, `--bg`, `/goal`.
- [Monitor tool: real-time background process streaming in Claude Code (AI Codex)](https://www.aicodex.to/articles/monitor-tool-def) — first deep external write-up of Monitor.
- [Monitor Tool: Event Streaming from Background Scripts (AgentPatterns.ai)](https://agentpatterns.ai/tools/claude/monitor-tool/) — Monitor vs `Bash run_in_background` vs `/loop` table.
- [Claude Code Monitor Tool (BuildThisNow)](https://www.buildthisnow.com/blog/guide/mechanics/monitor) — Monitor parameter reference and stream-filter examples.
- [Monitor in Claude Code: event-driven not every 30 seconds (wmedia.es)](https://wmedia.es/en/tips/claude-code-monitor-tool-event-driven) — `/loop` vs Monitor decision matrix.
- [`Glsme/agent-monitor` (GitHub)](https://github.com/Glsme/agent-monitor) — third-party desktop visualiser; not part of official surface.
- [`kexi/claude-code-monitor` (GitHub)](https://github.com/kexi/claude-code-monitor) — third-party terminal-tab dashboard that reads `~/.claude-monitor/sessions.json`.
