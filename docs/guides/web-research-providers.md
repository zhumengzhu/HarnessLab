# Web research providers

Last updated: **2026-05-25** (verify pricing on vendor sites before production budgets).

HarnessLab, [OpenClaw](https://docs.claw.so/engine/tools/web/), and
[OpenCode](https://opencode.ai/docs/tools/) all expose **search** and **fetch**
capabilities to agents, but the architecture and paid backends differ.

## How each project implements web tools

### HarnessLab (this repo)

| Tool | Implementation | Backend options |
| --- | --- | --- |
| `web_search` | `httpx` to a pluggable backend | `duckduckgo` (HTML scrape, free, fragile), `brave`, `tavily`, `serpapi` (API keys) |
| `fetch_url` | Plain HTTPS GET + raw body text | No JS; SSRF-safe open mode |
| `html_to_markdown` | Local HTML → markdown parser | Free, offline |
| `read_pdf` | Local PDF text extraction | Free, offline |

Configuration:

- `~/.config/harnesslab/config.json` → `tools.web_search.backend`, `api_key_env`, `api_base_url`
- `~/.config/harnesslab/env` → `WEB_SEARCH_BACKEND`, `TAVILY_API_KEY`, `HTTPS_PROXY`, …
- Env overrides config; see [`scripts/hl-serve.example.env`](../scripts/hl-serve.example.env).

Switch backends without code changes:

```json
{
  "tools": {
    "web_search": {
      "backend": "tavily",
      "max_results": 8,
      "api_key_env": "TAVILY_API_KEY"
    }
  }
}
```

```bash
export TAVILY_API_KEY="tvly-..."
export WEB_SEARCH_BACKEND="tavily"   # optional env override
./hl-serve restart
uv run harnesslab check network
```

### OpenClaw

| Tool | Implementation | Default / options |
| --- | --- | --- |
| `web_search` | Provider API | **Brave Search API** (default) or **Perplexity Sonar** (direct or via OpenRouter) |
| `web_fetch` | HTTP GET → **Readability** main-content extraction → optional **Firecrawl** fallback | Chrome-like UA, caching, SSRF guards |
| Browser tool | Full browser automation | For JS-heavy / login flows (not a HTTP fetch) |

Docs: [Web tools](https://docs.claw.so/engine/tools/web/),
[web_fetch](https://documentation.openclaw.ai/tools/web-fetch).

Key differences vs HarnessLab:

- Search defaults to **paid Brave API**, not HTML scraping.
- Fetch does **Readability + optional Firecrawl** (JS/bot bypass), not raw HTML.
- Proxy: `useTrustedEnvProxy` on fetch for trusted HTTP(S)_PROXY setups.

### OpenCode

| Tool | Implementation | Availability |
| --- | --- | --- |
| `websearch` | **Exa AI** hosted MCP (when `OPENCODE_ENABLE_EXA=1` or OpenCode provider) | No Exa API key required in default docs |
| `webfetch` | HTTP fetch for a specific URL | Built-in retrieval step |
| Plugins | e.g. `opencode-websearch-cited` (Google/OpenAI/OpenRouter grounded search), `opencode-firecrawl` | Ecosystem extensions |

Docs: [Tools](https://opencode.ai/docs/tools/),
[Ecosystem](https://opencode.ai/docs/ecosystem/).

Key differences:

- Search is often **Exa** or **model-native web search** (Gemini/Google Search grounding, OpenAI web search, OpenRouter plugins)—not DuckDuckGo scrape.
- Extension model (TypeScript plugins) vs HarnessLab’s config-driven backends.

## Mainland China / VPN note

Browsers use system or extension proxy; **Python `httpx` only sees `HTTP_PROXY` / `HTTPS_PROXY` /
`ALL_PROXY`**. Set them in `~/.config/harnesslab/env` and restart `./hl-serve`.

```bash
export HTTPS_PROXY="http://127.0.0.1:1087"   # match your VPN local port
uv run harnesslab check network
```

DuckDuckGo HTML scrape often returns HTTP **202 anti-bot** even with proxy—prefer **Tavily** or **Brave** API for search.

`fetch_url` cannot render JavaScript; Google search pages, BBC SPAs, etc. need article URLs + `html_to_markdown`, or a future Firecrawl-style fallback.

## Provider pricing snapshot (2026-05-25)

Verify live pricing before budgeting. “Free tier” rules change; links are official entry points.

### Search backends (HarnessLab `web_search`)

| Provider | HarnessLab backend | Official link | Free tier (as of 2026-05-25) | Paid (summary) |
| --- | --- | --- | --- | --- |
| DuckDuckGo HTML | `duckduckgo` | [duckduckgo.com](https://duckduckgo.com/) | No API key; **not a stable API**—scraping, anti-bot, zero SLA | N/A |
| Tavily | `tavily` | [tavily.com](https://tavily.com/) · [Credits docs](https://docs.tavily.com/documentation/api-credits) | **1,000 credits/month** free, no card | Pay-as-you-go **$0.008/credit**; plans from **$30/mo** (4k credits). Search: **1 credit** (basic) or **2** (advanced) per request |
| Brave Search API | `brave` | [brave.com/search/api](https://brave.com/search/api/) | **$5/month in free credits** (auto-applied) | **Search**: ~**$5 / 1,000 requests**; **Answers** (LLM): **$4 / 1k requests** + token usage |
| SerpAPI | `serpapi` | [serpapi.com/pricing](https://serpapi.com/pricing) | **250 searches/month** free | **$25/mo** (1k searches), **$75/mo** (5k), … Only **successful** searches count |

### Fetch / extraction (comparison — not all wired in HarnessLab today)

| Provider | Used by | Official link | Free tier (2026-05-25) | Paid (summary) |
| --- | --- | --- | --- | --- |
| HarnessLab `fetch_url` | HarnessLab | — | Free (your bandwidth) | — |
| Readability (local) | OpenClaw `web_fetch` | — | Free | — |
| Firecrawl | OpenClaw fallback; OpenCode plugin | [firecrawl.dev/pricing](https://www.firecrawl.dev/pricing) | **1,000 credits/month** | Hobby **~$16/mo** (5k credits, yearly billing shown on site). Scrape **1 credit/page**; Search **2 credits / 10 results** |
| Exa AI | OpenCode `websearch` | [exa.ai](https://exa.ai/) | Docs state **no API key** for default hosted MCP path—confirm on [Exa pricing](https://exa.ai/pricing) | Commercial plans for direct API volume |

### OpenClaw-only search extras

| Provider | Config | Official link | Notes |
| --- | --- | --- | --- |
| Perplexity Sonar | `tools.web.search.provider: perplexity` | [perplexity.ai](https://www.perplexity.ai/) · [OpenRouter](https://openrouter.ai/) | AI-synthesized answers + citations; billing via Perplexity or OpenRouter credits |
| OpenRouter web plugins | OpenCode `opencode-websearch-cited` | [OpenRouter web search](https://openrouter.ai/docs/guides/features/plugins/web-search) | Model + plugin pricing combined |

## HarnessLab operator checklist

1. Copy [`scripts/hl-serve.example.env`](../scripts/hl-serve.example.env) → `~/.config/harnesslab/env`.
2. Set **HTTPS_PROXY** to your VPN local HTTP port (macOS: `scutil --proxy`).
3. Choose **`tools.web_search.backend`**: `tavily` recommended in CN; `brave` if you already use OpenClaw.
4. Run **`uv run harnesslab check network`** after `./hl-serve restart`.
5. Deep research flow: `web_search` → pick article URLs → `fetch_url` → `html_to_markdown` (avoid Google search URLs).

## Related docs

- [`docs/architecture/tool-runtime.md`](../architecture/tool-runtime.md) — tool policy and schemas
- [`skills/deep-research.md`](../../skills/deep-research.md) — research skill workflow
