# OpenRouter and OpenAI-compatible proxies

Status: **operator guide** (2026-06). HarnessLab does not ship a dedicated
OpenRouter adapter — you route through the **OpenAI Chat Completions**
transport with a custom base URL.

## When to use

- One API key for multiple upstream models (Anthropic, Gemini, DeepSeek, etc.)
- Local experimentation without juggling per-vendor SDK keys
- **Not** a substitute for native adapters when you need full thinking/tool
  replay semantics — see [Caveats](#caveats).

## Quick setup

1. Create an [OpenRouter](https://openrouter.ai/) API key.
2. Export env (or `~/.config/harnesslab/env` for `./hl-serve`):

```bash
export OPENAI_API_KEY="sk-or-v1-..."
export OPENAI_BASE_URL="https://openrouter.ai/api/v1"
```

3. Point HarnessLab at the OpenAI backend with an OpenRouter model id in
   `~/.config/harnesslab/config.json`:

```json
{
  "model": {
    "default_backend": "openai",
    "openai_model_id": "anthropic/claude-sonnet-4"
  }
}
```

4. Run:

```bash
uv run harnesslab serve --model openai
# or
uv run harnesslab run --model openai --storage sqlite "hello"
```

Catalog entries that declare `reasoning_support: proxy` in
[`provider-expansion.md`](../architecture/provider-expansion.md) apply here:
thinking behavior follows **what the gateway exposes**, not the upstream
vendor docs.

## Trace / pricing

- Token buckets normalize via `providers/pricing/normalize.py`; when the
  gateway reports cache fields, they appear in **`llm.generate`** span
  `metrics.usage_breakdown` (`cache_read`, `cache_write`, …) and in the Web
  Trace **Token breakdown** panel.
- Cost estimates use [`pricing_catalog.json`](../../src/harnesslab/providers/pricing_catalog.json);
  OpenRouter-specific per-model pricing may be **unknown** until you add a
  catalog override.

## Optional live smoke

Connectivity-only tests (skipped unless opted in):

```bash
RUN_OPENROUTER_LIVE=1 OPENAI_API_KEY=sk-or-v1-... OPENAI_BASE_URL=https://openrouter.ai/api/v1 \\
  uv run pytest tests/manual/test_openrouter_live.py -m network -v -rs
```

Does not run in default CI.

## Caveats

| Topic | Native adapter | OpenRouter / proxy |
| --- | --- | --- |
| Thinking replay on tool loops | Per-family transforms | **Best-effort**; gateway may strip or reshape reasoning |
| Tool call wire shape | Validated in contract tests | Depends on gateway + model pair |
| Failover chain | Mix native backends | Prefer **one** proxy backend per chain unless you accept semantic drift |
| Eval / replay | Deterministic `simple` / `ReplayModel` | Live proxy **out of scope** for eval baseline |

## Related

- [`docs/architecture/provider-expansion.md`](../architecture/provider-expansion.md) §2.6
- [`docs/guides/web-research-providers.md`](web-research-providers.md) (Perplexity via OpenRouter)
