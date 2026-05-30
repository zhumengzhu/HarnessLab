# Humanizer

Remove AI writing patterns, restore **natural human voice**, and optionally
produce an **audit** before rewrite. One skill for "去 AI 味 / humanize / de-AI-ify".

**Invoke:** `/humanizer` + text or file path. Optional flags in the message:

- **默认** — 审计（简要）+ 改写 + 语气润色，一次完成
- **`audit only`** — 只输出问题清单，不改写
- **`formal`** — 保留正式文体，仅去 AI 模式词，不加口语

**Lineage (merged for HarnessLab):**

- Pattern + personality: [ClawHub humanizer](https://clawhub.ai/biostartechnology/humanizer) (biostartechnology)
- 24-pattern checklist + vocab tiers: [ai-humanizer](https://clawhub.ai/brandonwise/ai-humanizer) (brandonwise)
- Voice + `-HUMAN` file workflow: [de-ai-ify](https://clawhub.ai/ItsFlow/de-ai-ify) (ItsFlow)

## When to use

- Polishing AI drafts before publish (blog, README, report, cover letter)
- Post-processing **`deep-research`** reports for external readers
- User says: humanize, de-AI, 去 AI 味, 更自然, less robotic

## When not to use

- Code, configs, API specs, trace logs
- Text that must stay verbatim (legal quotes)
- Pure data tables with no prose

## HarnessLab workflow (single pass)

1. **Read** — inline text or `read_file` path
2. **Audit (brief)** — scan patterns + Tier 1/2 vocabulary + rhythm (see below)
3. **Rewrite** — fix flagged spans; preserve facts, links, citations
4. **Voice** — vary sentence length; cut buzzwords; add specificity (tone-dependent)
5. **Deliver**
   - Humanized text in chat
   - **Change summary** (bullets)
   - Optional: `write_file` → `{stem}-HUMAN.md` (do not overwrite source unless asked)

For long inputs, prefer file output. For **`audit only`**, skip steps 3–4 and return
findings table only.

## Phase A — Pattern audit

Tick any that apply (combine Wikipedia + 24-pattern sets; duplicates collapsed):

| Area | Watch for |
| --- | --- |
| Significance inflation | pivotal moment, testament to, broader landscape |
| Notability stuffing | media lists without a specific claim |
| Superficial -ing | highlighting… showcasing… reflecting… |
| Promotional tone | nestled, stunning, breathtaking, vibrant |
| Vague attribution | Experts say; Studies show (no source) |
| Formulaic challenges | Despite challenges… continues to thrive |
| AI vocabulary (Tier 1) | delve, tapestry, landscape, robust, seamless, leverage, synergy… |
| AI vocabulary (Tier 2) | furthermore, moreover, paradigm, holistic, utilize… |
| Copula avoidance | serves as, boasts, features → prefer is/has |
| Negative parallelism | It's not just X, it's Y |
| Rule of three / synonym cycling | triple lists; rotating synonyms |
| Em dash / bold spam | — chains; mechanical **emphasis** |
| Chatbot artifacts | I hope this helps!; Great question!; Let me know if… |
| Filler | In order to → to; Due to the fact that → because |
| Stacked hedges | could potentially perhaps |
| Generic conclusions | The future looks bright; Exciting times ahead |
| Soulless rhythm | every sentence same length; no opinion; press-release tone |

**Statistical eye-check:** sentence length variation, repeated paragraph openers
(Additionally, Moreover), repeated trigrams.

## Phase B — Rewrite rules

- Preserve meaning, numbers, dates, names, URLs
- One hedge max per uncertain claim; name sources or drop
- Use **is** / **has** freely
- End on something **specific**, not a motivational poster
- **`formal` mode:** fix patterns only; no slang, minimal first person

## Phase C — Voice (skip in `formal` or `audit only`)

- Mix short and long sentences
- Replace corporate buzz with plain verbs
- Soften robotic transitions (Furthermore → direct flow or new paragraph)
- Allow one concrete reaction or mixed feeling when tone allows
- Flag **[NEEDS EXAMPLE]** where the draft is vague — do not invent facts

## Output formats

**Default (rewrite):**

```markdown
## Humanized text
...

## Changes
- Removed Tier 1 terms: …
- Fixed significance inflation in …
- Varied rhythm / cut chatbot filler
```

**Audit only:**

```markdown
## Findings
| Area | Excerpt | Suggested fix |
| --- | --- | --- |
```

## Pipeline with deep-research

```text
/deep-research …  →  report.md
/humanizer audit only report.md   (optional)
/humanizer report.md              → report-HUMAN.md
```

## Quality bar

- Read-aloud test: sounds like a specific human, not a template
- No fake numeric "AI scores" — qualitative notes only
