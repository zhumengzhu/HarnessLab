# Agent Harness Landscape & HarnessLab Capability Gap

> **Status:** External research, May 2026. Synthesises the public state
> of agent harnesses, frameworks, IDE agents, and open-source coding
> agents, then scores HarnessLab against the recurring capability list.
> Sources cited inline; see §6 for the full reference list.

This document answers two questions:

1. **What capabilities have agent-harness projects converged on by mid-2026?**
2. **Where does HarnessLab stand on each, and what is genuinely missing
   versus deliberately deferred?**

It is meant to inform — but not preempt — Phase 5/6 planning in
[`docs/roadmap.md`](../roadmap.md). For HarnessLab's learning-first scope, see
[`docs/why-harnesslab.md`](../why-harnesslab.md).

---

## 1. Taxonomy: what people actually mean by "agent X"

A 2026 industry survey ([dev.to / All Agent Harnesses][devto-harness])
draws from Anthropic engineering's own taxonomy and lands on six
distinct categories. We adopt it here because the rest of this doc is
incoherent without the distinction.

| Category | Who owns the loop | Examples |
|---|---|---|
| **Agent Harness** | The platform / runtime container | GitHub Copilot, Bedrock Agents, Vertex AI Agent Builder |
| **Agent Framework** | The developer | LangChain / LangGraph, CrewAI, AutoGen, Semantic Kernel |
| **Agent SDK** | The vendor's runtime, via a thin client | OpenAI Agents SDK, Google ADK |
| **Agent Tool / Sandbox** | N/A — it is a tool | E2B, Daytona, Modal, Cloudflare Workers |
| **Agent Orchestrator** | A control plane over multiple harnesses | Warp Oz |
| **IDE Agent** | The IDE vendor | Cursor, Windsurf, JetBrains AI, Antigravity |
| **Autonomous Agent** | The agent itself | Devin |

**HarnessLab is an Agent Harness** (control plane: the loop is ours).
It is *not* a framework — there is no public SDK contract for
"compose your own agent" yet — and it is *not* an IDE agent.

Two empirical observations from the same survey are worth pinning to
the wall before reading the rest of this document:

- A May 2026 MBZUAI study quantified Claude Code's source as
  **~98.4% harness infrastructure** (permissions, context management,
  sandboxing, tool routing, recovery) and **~1.6% AI decision logic**.
- Four independently-built agents (Claude Code, Codex CLI, Aider,
  OpenClaw) converged on substantially the **same harness pattern**,
  suggesting the architecture is a constraint of the problem, not a
  fashion.

That ratio is the project HarnessLab is implicitly working on. The
gap analysis below treats it as the brief.

---

## 2. The recurring capability list (2026)

Distilling the public surface of the harnesses, IDE agents, and
open-source coders below, the capabilities a "credible" agent harness
in mid-2026 is expected to expose group into seven layers:

1. **Loop & decision model** — multi-step inner loop, terminal kinds,
   compaction / context window management, deterministic replay.
2. **Tool / extension surface** — file ops, structured shell, MCP,
   plugins, custom skills, streaming tools, browser, sandboxed code
   execution.
3. **Policy & sandboxing** — tool allow / deny lists, OS-level
   sandbox, content / prompt-injection guardrails, per-tool budgets,
   pre/post-tool hooks.
4. **Memory & context** — short-term (compaction), session-scoped
   notes, project / workspace memory (`CLAUDE.md`, `AGENTS.md`,
   `.claude/`), codebase index, semantic / vector retrieval, artifact
   refs.
5. **Multi-agent & subagents** — sub-session delegation,
   advisor/executor patterns, parallel work (worktrees / fleets),
   inter-agent messaging, supervisor process.
6. **Observability & lifecycle** — JSONL trace, OTel export, replay
   + divergence, eval suites, checkpoints / rewind, session list /
   fleet view, run-to-completion goals.
7. **Operator & deployment** — operator config, secret separation,
   provider failover, scheduled / cron / webhook triggers, background
   daemon, multi-user / RBAC, plugin marketplace.

The next section runs HarnessLab through this list.

---

## 3. HarnessLab capability scorecard

Legend: ✅ shipped · 🟡 partial / planned in Phase 5 · 🔲 deferred · ❌
out of scope by project charter.

### 3.1 Loop & decision model

| Capability | Status | Notes |
|---|---|---|
| Multi-step inner loop with terminal kinds | ✅ | `run_session` + `final` / `ask_user` (Phase 2.1). |
| Token threshold + overflow compaction | ✅ | `core/compaction.py` + `ModelOverflowError` (Phase 2.4). |
| Deterministic replay model + divergence detector | ✅ | `ReplayModel` + `FrozenClock` + `detect_divergence` (Step 5). |
| Plan-before-execute mode | 🟡 | Phase 5.3 in roadmap; `Decision.kind: plan` not yet shipped. |
| Goal / "run until condition met" mode | 🔲 | Equivalent to Claude Code `/goal` + OpenAI Codex Goals; depends on Phase 5.3. |
| Streaming model output | ❌ | All providers `decide(...)` synchronously; deliberate Post-MVP simplification ([provider-expansion.md][prov-exp] §6.6). |

### 3.2 Tool / extension surface

| Capability | Status | Notes |
|---|---|---|
| File ops (read / write / edit / patch) | ✅ | `read_file`, `write_file`, `edit_file`, `apply_patch`. |
| Code search (grep / glob) | ✅ | Native walk with noise-dir skip list. |
| Allowlisted shell | ✅ | `run_shell_safe` + 3 shell profiles. |
| Read-only HTTP fetch | 🟡 | `fetch_url` exists; allowlist is single-host (`wttr.in`). Phase 5.1 widens it. |
| Web search | 🔲 | Phase 5.1. Universally present in Cursor, Claude Code (via MCP / Brave), Cline, Aider. |
| HTML / PDF ingest | 🔲 | Phase 5.1 (`html_to_markdown`, `read_pdf`). |
| MCP support | 🔲 | Phase 5.4. Now the de-facto plugin protocol across Claude Code, OpenAI Agents SDK ([alicelabs.ai][alicelabs] ranks Claude Agent SDK #2 partly because of native MCP), Continue, Cline, Roo Code, Kilo Code. |
| Sandboxed code execution (Python) | 🔲 | Phase 5.5. Cursor / Devin / OpenAI Agents SDK rely on first-class sandboxes (E2B, Modal, Daytona, Cloudflare, Vercel, Blaxel, Runloop); Claude Code uses `/sandbox` for OS-level isolation [(best-practices)](https://code.claude.com/docs/en/best-practices). |
| Browser automation | 🔲 (defer) | 操作员路径：MCP `@playwright/mcp`（[`guides/mcp-servers.md`](../guides/mcp-servers.md)）。OpenClaw 为 Gateway 内置 browser + CDP/Playwright；HarnessLab 不 ship in-process driver（[`guides/browser-automation.md`](../guides/browser-automation.md)）。 |
| Streaming / monitor tool | 🔲 | Claude Code's Monitor (v2.1.98) is the canonical example; see [`claude-code-monitor.md`](claude-code-monitor.md). Requires a new `StreamingToolPort` — not in Phase 5. |
| Custom skills / project workflows | 🟡 | `AGENTS.md` injected as dynamic prompt block today. Claude Code "Skills" are richer (markdown workflows invokable as `/skill foo` or preloaded into a subagent). Not on Phase 5 roadmap. |
| Plugins (third-party tool packages) | 🟡 | Discussed in [provider-expansion §6.7][prov-exp]; explicit non-goal for now. |

### 3.3 Policy & sandboxing

| Capability | Status | Notes |
|---|---|---|
| Default-deny tool policy | ✅ | `PolicyPort.allow_tool` returns `(bool, reason)`. |
| Workspace path containment | ✅ | All file tools + `apply_patch`. |
| Shell allowlist + git subcommand gate | ✅ | `SAFE_GIT_SUBCOMMANDS`. |
| Named shell profiles | ✅ | `dev`, `read_only`, `strict` (Phase 3.4). |
| OS-level sandbox | 🔲 | Phase 5.5. Claude Code `/sandbox` and Cursor's containers / Devin's per-session VMs all sit here. |
| Pre/post-tool hooks | 🔲 | Claude Code `hooks.json` ([hooks reference][cc-hooks]) fires on every tool event (`PreToolUse`, `PostToolUse`, `SubagentStart`, `SubagentStop`, …); GitHub Copilot has analogous `hookflows`. HarnessLab has `TraceRecorderPort` for *observation* but no *interception*. Real gap; candidate for Phase 5.7 (proposal review) or its own Phase 6 piece. |
| Guardrails (input / output validation) | 🔲 | OpenAI Agents SDK has a Guardrails API; Bedrock has content filters. HarnessLab relies on policy + tool schemas. |
| Auto-mode safety classifier | 🔲 | Claude Code "auto mode" runs a small classifier on every command (best-practices §"Auto mode"). |
| Per-tool / per-session budgets | 🟡 | `RuntimeLimits` covers output bytes and compaction; no token / cost budget yet. |

### 3.4 Memory & context

| Capability | Status | Notes |
|---|---|---|
| Session-scoped notes | ✅ | `/remember` → `session:{id}:notes`. |
| Workspace-scoped notes | ✅ | `/remember-global` → KV in `MemoryStorePort`. |
| Project-level instruction file | ✅ | `AGENTS.md` injected as dynamic prompt block. Claude Code uses `CLAUDE.md` / `.claude/*`. |
| Skills / per-project workflows | 🔲 | See §3.2; richer than current static blocks. |
| Codebase index | 🔲 | Cursor, Cline, Roo Code, Continue, Claude Code all index the repo for ranked retrieval. HarnessLab relies on grep/glob (live, no index). For a *small* workspace this is fine; for a 100k-file monorepo this is the largest gap. |
| Semantic / vector memory retrieval | 🔲 (deferred) | Roadmap "Deferred" — `SemanticMemoryStorePort` sketch, gated on Phase 5 producing real cross-session research need. |
| Artifact / blob refs | 🔲 | Phase 5.2 (`ArtifactStorePort`). |
| Context observability per call | ✅ | `ContextSnapshot` on every **`llm.generate`** span; `harnesslab context show / series`. **More transparent than most competitors.** |

### 3.5 Multi-agent & subagents

| Capability | Status | Notes |
|---|---|---|
| Parent / child session model | ✅ | `Session.parent_session_id` + `spawn_sub_agent` (Phase 6 shipped). |
| Spawn sub-agent as a tool | ✅ | `tool.spawn_sub_agent` behind policy + span links to child turn traces. |
| Advisor / executor pattern (small model triages, big model executes) | 🔲 | Claude Code "managed agents" (Code With Claude 2026) — interesting but premature for HarnessLab. |
| Parallel sub-agents (fleet mode) | 🔲 | Devin's "parallel Devins", Cursor IDE multi-session, Aider+worktrees, GitHub Copilot Agent Tasks REST API. |
| Worktree isolation per agent | 🔲 | Aider, Claude Code (auto mode + worktrees), GitHub Copilot desktop (per-task git worktrees) all converge here. |
| Inter-agent messaging (A2A protocol) | ❌ | CrewAI v1.14.5 added Google's A2A; outside HarnessLab's "single-process, observable, replayable" charter for the foreseeable future. |

### 3.6 Observability & lifecycle

| Capability | Status | Notes |
|---|---|---|
| JSONL spans (Observability v2) | ✅ | `SpanRecorderPort` + `LocalSpanRecorder` → `.harnesslab/spans.jsonl`. |
| Per-call telemetry (`llm.generate`, `tool.*`, `context.compact`) | ✅ | Includes `ContextSnapshot` on `llm.generate` metrics. |
| OTel span export | ✅ | `OtelSpanRecorder` lifecycle spans (P7 / O4). |
| OTel metrics histograms | ✅ | Phase 5.6 / O4 — `OtelMetricsRecorder` on completed spans. |
| Replay + divergence detector | ✅ | Semantic and strict modes; **rare** in this space. LangSmith records but does not re-run. |
| Eval task suite + baseline gate | ✅ | 14 tasks + `baseline.json` + GH Actions. **Even rarer.** |
| Checkpoints / `/rewind` | 🔲 | Claude Code snapshots files before each edit and offers a rewind menu (`Esc Esc`, `/rewind`). HarnessLab has none — `apply_patch` + `git` is the de-facto checkpoint. Real ergonomics gap. |
| Improvement proposals from failure clustering | ✅ | `harnesslab propose` — uncommon. |
| Session list + filter | ✅ | `harnesslab session ls` + status filter. |
| Multi-session fleet dashboard | 🔲 | Claude Code `claude agents` ([`claude-code-monitor.md`](claude-code-monitor.md) §3) is the obvious reference. Phase 6+ territory because it needs a supervisor. |

### 3.7 Operator & deployment

| Capability | Status | Notes |
|---|---|---|
| Operator config (JSON) + secrets separation | ✅ | `~/.config/harnesslab/config.json` + `~/.config/harnesslab/env`. |
| Multi-provider registry | ✅ | `simple` / `deepseek` / `anthropic` / `openai` / `gemini` (P0–P5). |
| Provider failover chain | ✅ | `FailoverModel` (P6). Same idea Claude Code shipped as `--fallback-model`. |
| `hl-serve` lifecycle helper | ✅ | start / stop / restart wrapper. |
| Background daemon / supervisor process | 🔲 | Claude Code supervisor hosts background sessions; HarnessLab has no equivalent — see [`claude-code-monitor.md`](claude-code-monitor.md) §4.2. Phase 6+ piece. |
| Scheduled / cron / webhook triggers | 🔲 | Claude Code "routines" + GitHub Copilot Agent Tasks REST API + Bedrock EventBridge integration. Could ship cheaply as `harnesslab schedule`, but not on the current roadmap. |
| Multi-user / RBAC | ❌ | Single-user local runtime by design. |
| Cost / token meter | 🔲 | Phase 5.6 metric histograms include token counters, but no per-session budget UI / alarms. |
| Plugin marketplace | ❌ | Charter non-goal. |

---

## 4. The honest gap list (filtered)

Of the 🔲 items above, the ones I would prioritise *if* the goal is
"close the distance to a credible 2026 agent harness" — independently
of the existing Phase 5 plan:

### 4.1 Already on Phase 5 (validated by this scan)

These showed up as recurring across competitors; the existing Phase 5
order is consistent with the survey:

1. **Web tools + web search** (5.1) — universal capability; HarnessLab's
   single-host allowlist is the most visible 2026 anachronism.
2. **MCP adapter** (5.4) — the protocol every other harness already
   speaks. Without it, HarnessLab is talking past the ecosystem.
3. **Artifact store** (5.2) — prerequisite for any long-running research
   task; competitors mostly handle this implicitly via their sandbox or
   file store, but the explicit `ArtifactStorePort` is cleaner.
4. **Plan-then-execute** (5.3) — table stakes since GitHub Plan Agent
   (May 2026) and Cursor Composer 2.5.
5. **Python sandbox** (5.5) — research/data-analysis enabler; defers to
   OS sandbox in Cursor/Claude Code/Devin.
6. **OTel metrics histograms** (5.6) — operator hygiene.
7. **Proposal review UI** (5.7) — HarnessLab-specific improvement loop.

### 4.2 Genuinely missing, not yet on the roadmap

Things competitors universally have that HarnessLab does not, where the
omission is *not* an explicit charter decision. These are candidates
for a Phase 5.x or Phase 6 line item:

1. **Pre/post-tool hooks (`PolicyPort` extension or new `HooksPort`).**
   Claude Code's `hooks.json` + GitHub `hookflows` are the
   industry-standard interception point: lint after every edit, block
   on policy violation, fire a notification. HarnessLab observes
   everything via trace but **cannot intercept**. Concrete change:
   `PolicyPort` already returns `(allow, reason)`; add a `before_tool`
   / `after_tool` hook table populated from config that can short-circuit
   or annotate. Small surface, big ergonomics win.
2. **Checkpoint / rewind on tool-edit boundaries.**  Today the only
   recoverable state is `git reset`; users routinely want
   "undo this multi-step run and try a different prompt". Could ship
   as a thin layer that snapshots changed files into
   `.harnesslab/checkpoints/<session>/<step>/` before any `write_file`
   / `edit_file` / `apply_patch` / `run_shell_safe` and exposes
   `harnesslab session rewind <session> <step>`. Phase 5.2 artifact
   store is a natural substrate.
3. **Cost / token budgets and alarms.** `RuntimeLimits` covers bytes
   and compaction; nothing covers tokens or money. Even a soft cap
   (`max_tokens_per_session`, warn at 80%) would close a complaint we
   would otherwise hear immediately as soon as Phase 5 enables longer
   research tasks.
4. **Codebase index.** `grep + glob` is fine for small repos; for
   anything > ~5k files the lack of a ranked index is the single
   biggest accuracy gap vs Cursor / Cline / Continue. **Caveat:** an
   index lives in the same neighbourhood as semantic memory (vector
   embeddings on chunks), which the project has explicitly deferred.
   Worth re-litigating only if/when a real workspace runs into the
   wall.
5. **Streaming model output + streaming tools.** The Monitor pattern
   ([`claude-code-monitor.md`](claude-code-monitor.md) §2) is the
   single largest "feels modern" gap. Both legs require a meaningful
   loop redesign; not Phase 5 work, but worth keeping in mind so the
   Phase 5 contracts don't accidentally cement the synchronous model.
6. **Skills as first-class artifacts.** Claude Code's skills =
   markdown invokable as `/skill foo` (or preloaded into a subagent).
   HarnessLab already loads `AGENTS.md`; extending to a `skills/` dir
   with on-demand load + `/skill` command is small. Composes with
   Phase 5.3 plan mode.

### 4.3 Deliberately not chasing (charter-aligned non-goals)

For the record, the following recurring capabilities are *correctly*
absent from HarnessLab and should stay absent unless the project
mission changes:

- **Distributed runtime, multi-user RBAC.** Bedrock Agents / Vertex AI
  / Devin live here. HarnessLab is a learning-first local harness.
- **Plugin marketplace.** Charter non-goal. MCP (Phase 5.4) covers the
  legitimate extension need.
- **Inter-agent / A2A protocols.** Out of scope until at least Phase 6
  PoC succeeds.
- **Auto-applied improvement proposals.** Permanently blocked by
  AGENTS.md proposal lifecycle.
- **TS migration.** Deferred until Phase 5 + 6 close; Ports designed
  for the eventual port.

---

## 5. Suggested follow-ups for the roadmap

Concretely, after the existing Phase 5 lands, the highest-leverage
*additions* this survey suggests are:

| Idea | Where it fits | Why |
|---|---|---|
| **Phase 5.x — pre/post tool hooks** | After 5.4 MCP (so MCP tools are coverable) | Real interception capability; tiny new surface on `PolicyPort`; competitors universally have it. |
| **Phase 5.y — checkpoint / rewind** | After 5.2 artifact store | Ergonomics; mounts cheaply on the artifact store. |
| **Phase 5.z — token / cost budgets** | After 5.6 metrics | Once histograms exist, budgets are trivially layered. |
| **Phase 6.x — supervisor + agent view CLI** | After Phase 6 PoC | If multi-agent survives the PoC, an `agent view`–style dashboard becomes inevitable. Cheaper to design when the PoC's session topology is known. |
| **Phase 6.y — streaming tools + monitor port** | After Phase 6 PoC | Plan only; this is the loop-contract change to make `Decision`/`Tool` async-friendly. |

None of these need to be acted on now. They are recorded so the next
person planning Phase 5.x has the survey results in writing.

---

## 6. References

- [`devto-harness`][devto-harness] — "All Agent Harnesses: The Live Comparison" (May 2026 living article). Comparison tables for harnesses, frameworks, IDE agents.
- [`alicelabs`][alicelabs] — "AI Agent Frameworks 2026: Production-Tested Ranking" (Alice Labs, May 2026). Production score per framework.
- [`tokenmix`][tokenmix] — "Agent Frameworks 2026: LangGraph vs CrewAI vs AutoGen vs OpenAI SDK". When-to-pick decision matrix.
- [`bestaiweb`][bestaiweb] — "LangGraph vs CrewAI vs AutoGen: How to Choose in 2026". AutoGen → MS Agent Framework transition.
- [`kunalganglani`][kunalganglani] — "LangGraph vs CrewAI 2026: Full Comparison". Checkpointer / interrupt / observability comparison.
- Open-source coding agents survey: [`wetheflywheel`][wetheflywheel], [`frontman`][frontman], [`rightaichoice`][rightaichoice], [`pkgpulse`][pkgpulse].
- Claude Code feature surface: [features-overview][cc-features], [best-practices][cc-best], [subagents][cc-subagents], [hooks][cc-hooks].
- Related internal note: [`claude-code-monitor.md`](claude-code-monitor.md).
- HarnessLab planning: [`docs/roadmap.md`](../roadmap.md) Phase 5 + Phase 6; [`docs/architecture/provider-expansion.md`][prov-exp]; [`docs/architecture/multi-agent-exploration.md`](../architecture/multi-agent-exploration.md).

[devto-harness]: https://dev.to/htekdev/all-agent-harnesses-the-live-comparison-1km5
[alicelabs]: https://alicelabs.ai/en/insights/best-ai-agent-frameworks-2026
[tokenmix]: https://tokenmix.ai/blog/agent-frameworks-2026-langgraph-crewai-autogen-openai-sdk
[bestaiweb]: https://www.bestaiweb.ai/how-to-choose-and-build-with-langgraph-crewai-autogen-or-llamaindex-workflows-in-2026/
[kunalganglani]: https://www.kunalganglani.com/blog/langgraph-vs-crewai
[wetheflywheel]: https://wetheflywheel.com/en/guides/open-source-ai-coding-agents-2026/
[frontman]: https://frontman.sh/blog/best-open-source-ai-coding-tools-2026/
[rightaichoice]: https://rightaichoice.com/compare/cline-vs-aider-vs-continue
[pkgpulse]: https://www.pkgpulse.com/guides/cline-vs-roo-code-vs-aider-open-source-ai-coding-agents-2026
[cc-features]: https://code.claude.com/docs/en/features-overview
[cc-best]: https://code.claude.com/docs/en/best-practices
[cc-subagents]: https://code.claude.com/docs/en/sub-agents
[cc-hooks]: https://code.claude.com/docs/en/hooks.md
[prov-exp]: ../architecture/provider-expansion.md
