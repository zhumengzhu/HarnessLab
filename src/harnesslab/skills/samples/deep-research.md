# Deep research

Multi-source **depth-first research** for learning, decisions, or deliverable
documents. Produces a **cited Markdown report** saved to the workspace — not a
chat-only summary.

**Invoke:** `/deep-research <your topic>` — pins this skill and runs the task
in one turn (Cursor-style). `/deep-research` alone only pins without running.

**Inspired by:** [ClawHub Deep Research Pro](https://clawhub.ai/parags/deep-research-pro)
(parags), DeerFlow `deep-research`, OpenCode `research-deep` — see
[Deep research landscape](https://github.com/zhumengzhu/HarnessLab/blob/c7625595e226daf7ebb715cec82b4d08931ea586/docs/guides/deep-research-landscape.md).
Adapted for HarnessLab `web_search`, `fetch_url`, `html_to_markdown`,
`read_pdf`, and `write_file`.

## When to use

- User wants thorough investigation, not a quick answer
- Topic needs multiple sources, recency checks, or contradiction handling
- Output should be a **document** (report, memo, brief) the user can keep

## When not to use

- Single fact lookup ("what year was X founded?")
- Code changes in this repo (use normal dev tools instead)
- User explicitly asked for a short chat reply only

## HarnessLab tools (required)

| Step | Tool | Notes |
| --- | --- | --- |
| Discover | `web_search` | 2–3 keyword variants per sub-question |
| Fetch | `fetch_url` + `html_to_markdown` | Deep-read 3–5 best sources (not snippets alone) |
| PDFs | `read_pdf` | When primary sources are PDF |
| Persist | `write_file` | Final report under `.harnesslab/research/` |
| Optional | `spawn_sub_agent` | Only if `loop.multi_agent` enabled and topic is large |

## Workflow

### 1. Clarify (≤2 questions, then proceed)

Ask only if missing:

- Goal: learn / decide / write / deliverable?
- Scope: time range, geography, audience, depth?

If the user says "just research it", use sensible defaults and **start**.

### 2. Plan before searching

Break the topic into **3–5 sub-questions**. Emit a short numbered plan in chat
(use `/plan …` or a `plan` decision if planning mode is on), then execute.

Example sub-questions for "AI agent harness landscape 2026":

1. What do major products (Cursor, Claude Code, OpenClaw) optimize for?
2. What capabilities are table-stakes vs differentiators?
3. Where are gaps in open-source / learning harnesses?

### 3. Multi-source search

For **each** sub-question:

- Run `web_search` with varied queries (technical + news angles when relevant)
- Prefer: official docs, primary data, reputable journalism, papers
- Deprioritize: SEO farms, unattributed listicles
- Target **15–30 unique URLs** across the whole run; dedupe by domain + title

### 4. Deep-read key sources

For the **5–8 strongest** URLs:

- `fetch_url` → `html_to_markdown` (or `read_pdf`)
- Extract claims, numbers, dates, and named entities
- Note **conflicts** between sources explicitly

Do not rely on search snippets alone for central claims.

### 5. Synthesize report

Write Markdown with this structure:

```markdown
# [Topic]: Deep Research Report

*Generated: [date] | Sources: [N] | Confidence: High/Medium/Low*

## Executive summary
[3–5 sentences — what a busy reader needs]

## 1. [Theme]
[Claims with inline links: ([Source title](url))]

## 2. [Theme]
...

## Contradictions & gaps
[Where sources disagree or evidence is thin]

## Key takeaways
- [Actionable bullet]
- [Actionable bullet]

## Sources
1. [Title](url) — one-line note
2. ...

## Methodology
Sub-questions, query count, fetch count, date cutoff
```

### 6. Save & deliver

1. Slug: lowercase, hyphenated topic (e.g. `agent-harness-2026`)
2. Path: `.harnesslab/research/{slug}/report.md`
3. Use `write_file` with the full report body
4. In chat: post **executive summary + key takeaways** and the file path
5. Offer to expand any section on request

## Quality rules

1. **Every material claim needs a source** — or label "unverified / inference"
2. **Cross-check** — single-source claims get flagged
3. **Recency** — prefer last 12 months unless historical topic
4. **No hallucination** — if data missing, say "insufficient evidence found"
5. **Separate facts from opinion** — label analyst judgment clearly

## Optional: sub-agent

For very large topics (when multi-agent is enabled), spawn one research child
per major theme; parent synthesizes into one report. Child output must still
land as files or structured tool results the parent can cite.

## Optional: humanize before publish

For external-facing reports, run **`/humanizer`** on the saved Markdown
(`audit only` first if the user wants a review-only pass).
