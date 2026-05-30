# Model pricing and usage normalization

Last updated: **2026-05-30**

HarnessLab estimates LLM spend from provider usage metadata and a local
**pricing catalog**. The module is intentionally smaller than full billing
systems in OpenCode, OpenClaw, or Hermes-agent, but follows the same shape:
normalize vendor usage → canonical dimensions → apply rate card → attach to
trace and budget ledger.

## Goals

| Goal | Approach |
| --- | --- |
| **Multi-vendor** | One `CanonicalUsage` shape; per-provider `normalize_usage` branches |
| **Cache-aware** | Separate `cache_read`, `cache_write`, optional TTL tiers |
| **Observable** | `usage_breakdown` + `cost_estimate` on every `llm.generate` span (`SpanRecord.metrics`) |
| **Budget-safe** | Session `budget_usage.cost_usd_total` uses the same estimator |
| **Simple to extend** | JSON catalog + small Python package; no runtime network fetch (P0–P1) |
| **Migration-friendly** | Legacy `request_tokens` / `response_tokens` preserved for replay |

Non-goals (for now):

- Invoice-grade accuracy or provider billing API reconciliation
- Automatic catalog sync from models.dev / OpenRouter (Phase P2)
- Tiered pricing by context length (OpenClaw-style tiers — Phase P3)
- Non-USD budget enforcement (catalog may list CNY; ledger stays USD until P2)

## Reference projects (local `~/Github`)

We studied three nearby implementations and kept the useful parts without
copying their complexity.

| Project | What we borrowed | What we deferred |
| --- | --- | --- |
| **Hermes-agent** (`agent/usage_pricing.py`) | `CanonicalUsage`, `CostResult`, `normalize_usage` per API mode, official-docs snapshots | Live OpenRouter/models.dev fetch, `Decimal` everywhere, request-per-call fees |
| **OpenClaw** (`src/utils/usage-format.ts`) | Flat + optional tiered `ModelCostConfig`, pricing fingerprint for cache invalidation | Gateway pricing cache, `models.json` merge, tiered input-length schedules |
| **OpenCode** (`packages/opencode` transform tests) | Cache read/write in model cost objects; subtract cached tokens from billable input | Full models.dev plugin pipeline, generation-level cost API |

HarnessLab’s twist: **schedules in repo JSON** with explicit `pricing_version`,
time windows (`effective_from` / `effective_until`), and **trace-first**
breakdowns so Usage UI and replay can show cache/reasoning without re-parsing
raw provider payloads.

## Architecture

```mermaid
flowchart LR
    subgraph adapters [Provider adapters]
        DS[DeepSeek]
        AN[Anthropic]
        OA[OpenAI Responses]
        GM[Gemini]
    end

    subgraph pricing [providers/pricing]
        NU[normalize_usage]
        CU[CanonicalUsage]
        CAT[pricing_catalog.json]
        EST[estimate_call_cost]
    end

    subgraph runtime [Runtime]
        META[usage_meta_from_response]
        LOOP[HarnessLoop]
        TRACE[llm.generate span]
        BUDGET[session.budget_usage]
        USAGE[/api/usage]
    end

    DS --> META
    AN --> META
    OA --> META
    GM --> META
    META --> NU
    NU --> CU
    CU --> EST
    CAT --> EST
    META --> LOOP
    EST --> LOOP
    LOOP --> TRACE
    LOOP --> BUDGET
    TRACE --> USAGE
```

### Package layout

```
src/harnesslab/providers/
  pricing_catalog.json      # Rate cards (shipped with wheel)
  usage_meta.py             # Adapter helper → breakdown + cost_estimate
  pricing/
    models.py               # CanonicalUsage, CostResult, PricingSchedule
    normalize.py            # Vendor → canonical buckets
    catalog.py              # Load + resolve_schedule + fingerprint
    estimate.py             # estimate_call_cost (+ legacy USD wrapper)
    __init__.py             # Public API
```

Public imports:

```python
from harnesslab.providers.pricing import (
    CanonicalUsage,
    CostResult,
    estimate_call_cost,
    normalize_usage,
    resolve_schedule,
    catalog_fingerprint,
)
```

## Canonical usage

All providers map into fixed **billing dimensions**:

| Dimension | Meaning |
| --- | --- |
| `input` | Billable non-cached prompt tokens |
| `output` | Completion / visible output tokens |
| `cache_read` | Prompt tokens served from cache (cheaper tier) |
| `cache_write` | Cache creation (generic / 5m tier when not split) |
| `cache_write_5m` | Anthropic 5-minute cache write tier (P2) |
| `cache_write_1h` | Anthropic 1-hour cache write tier (P2) |
| `reasoning` | Reasoning / thinking tokens when billed separately |

Aggregates (for budget counters and span metrics):

- `prompt_tokens` = input + all cache_* buckets
- `response_tokens` (legacy field) = output + reasoning
- `total_tokens` = prompt + output + reasoning

### Normalization rules (P1)

| Provider / mode | Raw fields | Rule |
| --- | --- | --- |
| **Anthropic Messages** | `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `cache_creation.{ephemeral_5m,1h}_input_tokens` | Split 5m/1h write tiers when present; else generic `cache_write` |
| **OpenAI Responses** | `input_tokens`, `input_tokens_details.cached_tokens`, `cache_creation_tokens`, `output_tokens_details.reasoning_tokens` | Subtract cache from input total (OpenCode-style) |
| **OpenAI chat / DeepSeek** | `prompt_tokens`, `prompt_tokens_details`, `prompt_cache_hit_tokens`, `completion_tokens_details` | Subtract cache hits from prompt; map DS cache hit → `cache_read` |
| **Gemini** | `promptTokenCount`, `candidatesTokenCount`, `thoughtsTokenCount` | input / output / reasoning |

Adapters call `usage_meta_from_response(...)` so every `_last_call_meta` includes:

- Legacy: `request_tokens`, `response_tokens`, `total_tokens`
- New: `usage_breakdown`, `cost_estimate`, `pricing_version`

## Pricing catalog

File: `src/harnesslab/providers/pricing_catalog.json`

```json
{
  "schema_version": 1,
  "pricing_version": "2026-05-30",
  "default_currency": "USD",
  "currencies": {
    "USD": { "symbol": "$", "usd_per_unit": 1.0 },
    "CNY": { "symbol": "¥", "usd_per_unit": 0.14 }
  },
  "schedules": [
    {
      "id": "deepseek-v4-flash-usd",
      "model_id": "deepseek-v4-flash",
      "provider": "deepseek",
      "currency": "USD",
      "dimensions": ["input", "output", "cache_read"],
      "rates_per_million": {
        "input": 0.14,
        "output": 0.28,
        "cache_read": 0.0028
      },
      "source": "official_docs_snapshot",
      "source_url": "https://api-docs.deepseek.com/quick_start/pricing"
    },
    {
      "id": "deepseek-v4-flash-cny",
      "model_id": "deepseek-v4-flash",
      "currency": "CNY",
      "rates_per_million": {
        "input": 1.0,
        "output": 2.0,
        "cache_read": 0.02
      },
      "source_url": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing"
    }
  ]
}
```

### Official snapshots (2026-05-30)

Rates are per **million tokens** in the schedule currency. Cache hit maps to
`cache_read`.

| Model | CNY input | CNY output | CNY cache hit | USD input | USD output | USD cache hit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `deepseek-v4-flash` | ¥1 | ¥2 | ¥0.02 | $0.14 | $0.28 | $0.0028 |
| `deepseek-v4-pro` | ¥3 | ¥6 | ¥0.025 | $0.435 | $0.87 | $0.003625 |
| `mimo-v2.5` | ¥1 | ¥2 | ¥0.02 | $0.14 | $0.28 | $0.0028 |
| `mimo-v2.5-pro` | ¥3 | ¥6 | ¥0.025 | $0.435 | $0.87 | $0.0036 |

Sources: [DeepSeek pricing](https://api-docs.deepseek.com/zh-cn/quick_start/pricing),
[MiMo pay-as-you-go](https://platform.xiaomimimo.com/docs/zh-CN/price/pay-as-you-go)
(MiMo effective 2026-05-27).

Set `default_currency` / `display_currency` to `CNY` in
`~/.config/harnesslab/pricing.json` (and optionally
`loop.budget.display_currency` in `config.json`) to estimate and show costs in
RMB while the budget ledger remains USD (converted via `usd_per_unit`).

### `usd_per_unit` (currency conversion)

Each currency may declare how many **US dollars one unit** of that currency
represents when converting native schedule costs to the USD budget ledger:

| Key | Meaning | Example |
| --- | --- | --- |
| `usd_per_unit.CNY = 0.14` | 1 CNY × 0.14 = USD | ¥1 input → $0.14 |
| `usd_per_unit.USD = 1.0` | identity | $1 → $1 |

Formulas:

- **Native → USD (estimate / budget):** `amount_usd = amount_native × usd_per_unit[currency]`
- **USD → display (Usage UI):** `amount_display = amount_usd ÷ usd_per_unit[display_currency]`

Built-in `0.14` for CNY is derived from vendor list prices (e.g. DeepSeek
¥1/M input vs $0.14/M), not live forex. Override in `pricing.json` when you
prefer a market rate.

Legacy key `fx_to_usd` is still accepted as an alias for `usd_per_unit`.

### Schedule resolution

`resolve_schedule(model_name, currency=..., at=...)`:

1. Filter by currency (default from catalog)
2. Filter by `effective_from` / `effective_until`
3. Match exact `model_id`, else longest substring match
4. On miss → `estimate_call_cost` falls back to legacy flat input/output table

### Cost estimation

```python
cost = sum(tokens[d] * rates_per_million[d] for d in usage.to_breakdown()) / 1_000_000
```

`CostResult` fields written to **`llm.generate`** span metrics:

| Field | Purpose |
| --- | --- |
| `amount_usd` | Budget ledger value (USD for P1) |
| `status` | `estimated` \| `unknown` \| `included` |
| `source` | `catalog` \| `legacy_flat` \| `none` |
| `schedule_id` | Winning schedule row |
| `pricing_version` | Catalog version string |
| `notes` | Missing rates, currency conversion deferrals |

## Trace and budget integration

Telemetry is **span-first** ([`observability-v2.md`](observability-v2.md)). Pricing
fields live on completed **`llm.generate`** spans in `SpanRecord.metrics` (legacy
v1 `TraceEvent` / `model_call` payloads are historical only).

### `llm.generate` metrics (additive)

Existing fields unchanged. New optional keys:

| Key | Type | Description |
| --- | --- | --- |
| `usage_breakdown` | `dict[str, int]` | Canonical dimension counts |
| `cost_estimate` | `object` | `CostResult.to_trace_dict()` (stored in span metrics) |

After each model call, `HarnessLoop._accumulate_model_cost`:

1. Prefer `usage_breakdown` → `CanonicalUsage`
2. Else legacy token fields
3. `estimate_call_cost` → add to `session.budget_usage.cost_usd_total`

Budget guardrails (Phase 5.10) continue to use USD totals; see
[`overview.md`](overview.md) § Budget guardrails.

### Usage API

`GET /api/usage` aggregates completed **`llm.generate`** spans via `usage_aggregate.py`:

- Totals and buckets include `dimensions` (per canonical key)
- Cost prefers span `metrics.cost_estimate.amount_usd`, else re-estimates from breakdown

## Configuration

| Phase | Config | Behavior |
| --- | --- | --- |
| **P0–P1** | Built-in catalog | Edit JSON + bump `pricing_version` |
| **P2** (now) | `~/.config/harnesslab/pricing.json` | User overrides / extra schedules; optional `display_currency` + `usd_per_unit` |
| **P2** (now) | `loop.budget.display_currency` in `config.json` | Overrides pricing file default for Usage UI |
| **P3** | Tiered schedules | Context-length tiers (OpenClaw `PricingTier`) |

Environment: `HARNESSLAB_PRICING_CONFIG` points at an alternate pricing override file.

Operator override example:

```json
{
  "display_currency": "CNY",
  "default_currency": "CNY",
  "usd_per_unit": { "CNY": 0.14 },
  "overrides": [
    {
      "model_id": "deepseek-v4-flash",
      "currency": "USD",
      "rates_per_million": { "input": 0.20, "output": 1.0 }
    }
  ]
}
```

`config.json` snippet:

```json
{
  "loop": {
    "budget": {
      "display_currency": "CNY"
    }
  }
}
```

Budget ledger (`session.budget_usage.cost_usd_total`) always accumulates USD;
Usage UI shows `cost_display` when `display_currency` ≠ USD.

## Phased delivery

| Phase | Scope | Status |
| --- | --- | --- |
| **P0** | Package split, catalog JSON, `normalize_usage`, `estimate_call_cost` | **Done** |
| **P1** | Adapters → `usage_meta_from_response`; loop span metrics + budget; Usage API dimensions | **Done** |
| **P2** | User override file; CNY display; Anthropic 5m/1h cache_write split; Usage dimension legend | **Done** |
| **P3** | Tiered pricing; `pricing audit` CLI; `estimate_call_cost_decimal` | **Done** |

### Tiered schedules (P3)

Optional `tiered_rates` on a schedule — half-open input-token ranges
``[start, end)`` with per-tier `rates_per_million` (OpenClaw-style). Tier
selection uses **billable** `usage.input` (non-cached prompt tokens).

```json
{
  "id": "claude-sonnet-4-6-usd-tiered",
  "model_id": "claude-sonnet-4-6",
  "currency": "USD",
  "tiered_rates": [
    {
      "range": [0, 128000],
      "rates_per_million": { "input": 3.0, "output": 15.0, "cache_read": 0.3 }
    },
    {
      "range": [128000, 1000000],
      "rates_per_million": { "input": 6.0, "output": 30.0, "cache_read": 0.6 }
    }
  ]
}
```

When `tiered_rates` is present, flat `rates_per_million` is optional (first
tier may still serve as fallback in tooling).

### Catalog audit CLI (P3)

```bash
harnesslab pricing fingerprint
harnesslab pricing audit --currency USD
```

`audit` compares `ModelCatalog` model IDs to pricing schedules for the
chosen currency and lists missing/orphan rows. Exit code `2` when models
lack schedules (useful in CI).

### Decimal estimates (P3)

`estimate_call_cost_decimal(...)` returns a `Decimal` USD amount without
float drift — intended for eval task pins and regression tests, not the
hot loop path (which keeps float + `CostResult`).

## Testing

- `tests/test_pricing.py` — legacy wrapper + catalog model coverage
- `tests/test_pricing_normalize.py` — Anthropic / OpenAI / DeepSeek normalization
- `tests/test_pricing_catalog.py` — schedule resolution + CNY FX conversion
- `tests/test_pricing_override.py` — user override merge
- `tests/test_pricing_fx.py` — display currency conversion
- `tests/test_pricing_tiers.py` — tier selection + Decimal parity
- `tests/test_pricing_audit.py` — audit report shape
- `tests/test_cli_pricing.py` — `harnesslab pricing` subcommand
- `tests/test_usage_aggregate.py` — breakdown + `cost_estimate` aggregation

When changing normalization or catalog schema, update this doc and the tests
in the same PR.

## Related docs

- [`provider-expansion.md`](provider-expansion.md) — adapters and usage field shapes
- [`data-model.md`](data-model.md) — `SpanRecord` / `llm.generate` metrics contract
- [`observability-v2.md`](observability-v2.md) — span lifecycle and persistence
- [`overview.md`](overview.md) — budget guardrails
- [`../guides/web-research-providers.md`](../guides/web-research-providers.md) — non-LLM provider pricing
