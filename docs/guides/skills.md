# Skills discovery and install

HarnessLab skills are **markdown prompt documents** under `skills/*.md`. They
extend the composer via `/skillname` or `/skill` without changing the tool
runtime boundary.

Phase 7 adds **catalog search**, **explicit install**, and **remove** — skills
remain operator-controlled; the model cannot auto-install.

## Layout

| Location | Scope | Precedence |
|----------|-------|------------|
| `<workspace>/skills/*.md` | workspace | wins on name conflict |
| `~/.config/harnesslab/skills/*.md` | user | fills gaps |

## Front matter (optional)

```yaml
---
description: One-line summary for search and palette
tags: research, web
source: https://example.com/skills/demo.md
---
```

`description` and `tags` improve search. `source` is documentation only unless
you install from a catalog index that references the URL.

## Catalog sources

Configure in `~/.config/harnesslab/config.json`:

```json
"tools": {
  "skills": {
    "selection_mode": "heuristic",
    "catalog_sources": ["bundled", "/path/to/index.json", "https://example.com/skills-index.json"]
  }
}
```

| Source | Meaning |
|--------|---------|
| `bundled` | Built-in sample index (`compact`, `humanizer`, `deep-research`) |
| local path | JSON index file; `source` fields resolve relative to the index directory |
| HTTPS URL | Remote index; cached under `~/.config/harnesslab/catalog-cache/` (1h TTL) |

Index schema:

```json
{
  "version": 1,
  "skills": [
    {
      "id": "compact",
      "name": "compact",
      "description": "Force context compaction",
      "tags": ["context"],
      "source": "samples/compact.md"
    }
  ]
}
```

## CLI

From the repo root (after `uv sync`), use **`uv run`** — the `harnesslab` entry
point is installed in the project venv, not globally on `PATH` unless you
`pip install -e .` / activate `.venv` yourself.

`--workspace-root` belongs on the **`skill`** subcommand, **before** `list` /
`search` / `install` / `remove`:

```bash
uv run harnesslab skill --workspace-root . list
uv run harnesslab skill --workspace-root . search humanizer
uv run harnesslab skill --workspace-root . install --catalog-id compact
uv run harnesslab skill --workspace-root . install /path/to/skill.md --scope user
uv run harnesslab skill --workspace-root . remove compact --scope workspace
```

Optional: `source .venv/bin/activate.fish` (or `activate`) after `uv sync`, then
`harnesslab skill --workspace-root . list` works without the `uv run` prefix.

## Web UI

Settings → **Skills**: search installed + catalog entries, preview markdown,
install from bundled catalog or a local `.md` path.

## Context ring alignment

HarnessLab’s **Context ring** (Web UI) shows per–model-call token breakdown
(`ContextSnapshot`), similar in spirit to Cursor 3.3 **Context Usage
Breakdown** — both help diagnose prompt bloat before compaction. Skills
injected into the composer appear under the **Skills** category when the
adapter reports `prompt_block_breakdown`.

## Audit trace (optional)

Install paths may emit a `skill_installed` trace payload via
`skill_installed_event_payload()` for future session-scoped wiring. CLI/Web
install today does not attach to an active session trace.

## Not included (Phase 7)

- Public marketplace UI
- Model-initiated install
- Skills that execute code outside existing tools/policy

See also: [`docs/roadmap.md`](../roadmap.md) Post-MVP Phase 7,
[`AGENTS.md`](../../AGENTS.md) skill rules.
