# Model parameters reference

Status: **maintained with catalog changes**.  
Goal: record **official vendor parameters** per catalog model and how HarnessLab
maps them in operator config, runtime limits, and the Web UI.

Related: [provider-expansion.md](./provider-expansion.md), [data-model.md](./data-model.md),
catalog JSON under `src/harnesslab/providers/catalog/`.

Re-check vendor docs when adding a model or upgrading SDK majors.

---

## HarnessLab mapping rules

| Concern | Behavior |
|---------|----------|
| **Context window** | Taken from catalog `context_window`. `build_runtime()` and model switch call `align_runtime_limits_with_model()` so `RuntimeLimits.context_window_tokens` and compaction threshold match the model maximum. **Not user-editable in Web UI.** |
| **Context ring** | Uses aligned `context_window_tokens`, not the legacy 16K MVP default. |
| **Thinking / effort** | Per-vendor; see table below. Web UI **Edit** menu exposes effort where the adapter supports it. |
| **Output caps** | Operator `limits.max_output_tokens` (and provider defaults) still apply separately from context window. |

---

## Catalog models

### DeepSeek V4 Flash (`deepseek-v4-flash`)

| Field | Official / catalog | HarnessLab |
|-------|-------------------|------------|
| Context | **1,048,576** tokens (1M) | Catalog + runtime aligned; UI label **1M** |
| Max output | **384,000** tokens (catalog metadata) | Provider may cap via `limits`; not a separate UI control |
| Thinking | `thinking.type`: `enabled` \| `disabled` | Config `model.deepseek.thinking` |
| Reasoning effort | `reasoning_effort`: **`high`** (default) \| **`max`**; `low`/`medium` map to `high` per vendor | Config `model.deepseek.reasoning_effort`; UI **Off / High / Max** |
| Temperature | Not supported in thinking mode | Omitted from request when thinking enabled |

**Web UI effort levels:** `disabled` → Off, `high` → High, `max` → Max.

**Docs:** [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode), [Pricing / models](https://api-docs.deepseek.com/quick_start/pricing)

---

### DeepSeek V4 Pro (`deepseek-v4-pro`)

Same API surface as V4 Flash; HarnessLab uses the same thinking/effort mapping and 1M context alignment.

| Field | Official / catalog | HarnessLab |
|-------|-------------------|------------|
| Context | **1,048,576** tokens | Same as Flash |
| Max output | **384,000** tokens | Catalog metadata |
| Thinking + effort | Same as Flash | Same UI: Off / High / Max |

---

### Claude Sonnet 4.6 (`claude-sonnet-4-6`)

| Field | Official / catalog | HarnessLab |
|-------|-------------------|------------|
| Context | **200,000** tokens | Catalog + runtime aligned; UI **200K** |
| Thinking | **Adaptive (recommended):** `thinking.type: adaptive` + `output_config.effort` | Config `model.anthropic.thinking` object |
| Effort levels | `low`, `medium`, `high`, `max` (adaptive) | Web UI level picker when on Anthropic backend |
| Legacy | `thinking.type: enabled` + `budget_tokens` | Supported in adapter; not primary UI path |

**Docs:** [Extended thinking](https://platform.claude.com/docs/en/build-with-claude/extended-thinking), [Adaptive thinking](https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking)

---

### GPT-5 Mini (`gpt-5-mini`)

| Field | Official / catalog | HarnessLab |
|-------|-------------------|------------|
| Context | **128,000** tokens | Catalog + runtime aligned; UI **128K** |
| API family | OpenAI **Responses** API | `OpenAIResponsesModel` |
| Reasoning | `reasoning.effort` model-dependent | Config `model.openai.reasoning_effort`; UI effort levels from OpenAI set |

**Docs:** [Reasoning models](https://developers.openai.com/api/docs/guides/reasoning), [Using GPT-5.5](https://developers.openai.com/api/docs/guides/latest-model)

---

### Gemini 2.5 Flash (`gemini-2.5-flash`)

| Field | Official / catalog | HarnessLab |
|-------|-------------------|------------|
| Context | **1,048,576** tokens | Catalog + runtime aligned; UI **1M** |
| Thinking schema | **`thinking_budget`** (integer) | Config `model.gemini.thinking_budget`; UI budget-style effort |
| Budget semantics | `0` = off (where supported), `-1` = dynamic | Parsed in operator config |
| **Do not mix** | `thinking_level` + `thinking_budget` on same request | Catalog `thinking_schema: budget` |

**Docs:** [Gemini thinking](https://ai.google.dev/gemini-api/docs/thinking)

---

### Gemini 3 Flash Preview (`gemini-3-flash-preview`)

| Field | Official / catalog | HarnessLab |
|-------|-------------------|------------|
| Context | **1,048,576** tokens | Catalog + runtime aligned; UI **1M** |
| Thinking schema | **`thinking_level`** (e.g. `low`, `high`) | Config `model.gemini.thinking_level`; UI level-style effort |
| Default thinking | `high` (catalog) | Shown as default in model picker |

**Docs:** [Gemini thinking](https://ai.google.dev/gemini-api/docs/thinking)

---

### Simple (local deterministic)

| Field | Value |
|-------|-------|
| Context | N/A (no LLM context window) |
| Thinking | None |

Used for eval/replay and offline development.

---

## Operator config examples

DeepSeek with thinking at max effort:

```json
{
  "model": {
    "deepseek": {
      "model_name": "deepseek-v4-flash",
      "thinking": "enabled",
      "reasoning_effort": "max"
    }
  }
}
```

Shorthand (thinking + effort in one field):

```json
{
  "model": {
    "deepseek": {
      "thinking": "max"
    }
  }
}
```

---

## When to update this doc

Update in the **same change** when:

- Adding or removing a catalog JSON entry
- Changing `context_window`, thinking schema, or UI effort mapping
- Changing `align_runtime_limits_with_model()` behavior

Also update contract tests under `tests/test_provider_catalog.py` and any provider-specific tests.
