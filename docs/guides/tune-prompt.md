# Prompt tuning (`harnesslab tune-prompt`)

Bayesian self-evolution **Layer B2** scores frozen prompt candidates with a
**live-model benchmark** that is completely separate from `eval` / `replay`.
Output is an advisory `prompt_tuning` proposal — never auto-applied.

Design background: [`research/bayesian-self-evolution.md`](../research/bayesian-self-evolution.md).

## Quick start

```bash
# Generate candidates + score against the default bundled suite (needs API key)
source ~/.config/harnesslab/env   # or export DEEPSEEK_API_KEY=…

uv run harnesslab tune-prompt \
  --generate "Make replies terse; follow formatting instructions exactly." \
  --n 3 \
  --model deepseek \
  --repeats 2 \
  --out proposals/
```

Fast iteration on one task:

```bash
uv run harnesslab tune-prompt \
  --generate "Be more concise" --n 2 --model deepseek \
  --task exact_token --repeats 1 --out /tmp/tune
```

## Candidate sources (pick one)

| Flag | Meaning |
| --- | --- |
| `--generate "<instruction>" --n N` | Live LLM proposes `N` system prompts, frozen to `prompt_candidates.json` |
| `--candidates frozen.json` | Score pre-frozen candidates (no generation call) |

Mutually exclusive. Generation uses a neutral meta-prompt (not the agent identity)
so the model returns a JSON array of prompt strings.

## Benchmark suite

Default: six single-turn tasks baked into Python (`DEFAULT_BENCHMARK_SUITE`) that
reward terse, instruction-following replies (exact tokens, `max_chars`, no product
name leakage, compact JSON).

Override with YAML:

```bash
uv run harnesslab tune-prompt \
  --candidates cands.json \
  --benchmark-dir src/harnesslab/tune/prompt/benchmarks/minimal \
  --model deepseek
```

Shipped examples:

| Directory | Purpose |
| --- | --- |
| `src/harnesslab/tune/prompt/benchmarks/minimal/` | Two cheap smoke tasks |
| `src/harnesslab/tune/prompt/benchmarks/style/` | Style / identity checks |

### Task YAML schema

Single task file:

```yaml
id: my_task          # optional; defaults to filename stem
input: "User message sent to the agent"
max_steps: 3         # optional; default 3
checks:
  - kind: contains
    value: "42"
  - kind: max_chars
    limit: 8
  - kind: equals
    value: DONE
  - kind: not_contains
    value: HarnessLab
  - kind: regex
    value: '\\{"status":\\s*"ok"\\}'
  - kind: iregex
    value: '\\bparis\\b'
  - kind: judge
    value: "Reply must be polite and under two sentences."
```

Full suite file:

```yaml
tasks:
  - id: a
    input: "…"
    checks: [ … ]
```

Directory: every `*.yaml` at the top level is one task (sorted by name).

### Check kinds

| Kind | Pass when |
| --- | --- |
| `contains` | substring present in final reply |
| `not_contains` | substring absent |
| `regex` / `iregex` | pattern matches final reply |
| `equals` | normalized equality (strip, casefold, trim punctuation) |
| `max_chars` | `len(reply.strip()) <= limit` |
| `judge` | injectable LLM judge grades reply against rubric (`value`) |

All checks on a task must pass. A task failure counts against the candidate's
Beta-Binomial success posterior (same estimator as Layer A, with passes as the
numerator).

### LLM judge (optional)

Tasks with `kind: judge` need a second model:

```bash
uv run harnesslab tune-prompt \
  --candidates cands.json \
  --benchmark-dir ./bench_with_judge/ \
  --model deepseek \
  --judge-model deepseek
```

The default bundled suite uses **no** judge checks (zero extra API cost).

## Ranking and proposals

- Baseline (project default system prompt) is always scored alongside candidates.
- Ranking uses the **lower credible bound** on success rate so thin evidence is
  penalised.
- `improved: true` only when the best candidate's LCB beats the baseline LCB.
- Proposal markdown includes an acceptance checklist (`pytest`, `eval`, human review).

Re-run with higher `--repeats` before trusting a narrow margin — the benchmark is
non-deterministic.

## Writing benchmarks for your domain

1. Start from `benchmarks/minimal/` and add tasks that fail on behaviours you
   want to fix (verbosity, preamble, ignoring format instructions).
2. Prefer deterministic checks; reserve `judge` for rubrics hard to encode.
3. Keep tasks **single-turn** and tool-free when possible (cheaper, clearer signal).
4. Do **not** reuse `eval/tasks/*.yaml` — eval is for deterministic regression;
   prompt tuning needs live-model scoring.

## Related commands

| Command | Layer | Scoring |
| --- | --- | --- |
| `harnesslab propose` | A | failure clusters → advisory fixes |
| `harnesslab tune` | B1 | deterministic eval suite → runtime knobs |
| `harnesslab tune-prompt` | B2 | live prompt benchmark → system prompt |
