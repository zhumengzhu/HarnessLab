# HarnessLab TS WebUI

This directory hosts the TypeScript frontend described in
[`docs/architecture/frontend-ts-migration.md`](../docs/architecture/frontend-ts-migration.md).
Product UX principles live in
[`docs/architecture/webui-design.md`](../docs/architecture/webui-design.md).

WebUI package management is bun-first (`bun.lock` is the lockfile of record).

## Commands

```bash
cd webui
bun install
bun run dev
bun run build
bun run check
bun run test
# run one spec file:
bun run vitest run src/features/proposals/ProposalPanel.test.tsx
```

Build output goes to `src/harnesslab/web/static_ts/` (gitignored; run
`bun run build` before serving TS UI).

## Simple chat (3 steps)

1. Build the bundle (`bun run build`), then from repo root:
   `./hl-serve start` or `uv run harnesslab serve --workspace-root .`
2. In the browser, click **新对话** in the left **Sessions** panel.
3. Type in **Composer** at the bottom; type `/` for slash commands; press
   Enter to send (IME-safe for Chinese input).

Default UI mode is **Simple** (chat-focused). Switch to **Advanced** in the
header for trace, proposals, budget, and settings panels. Last session and
mode are restored from `localStorage` on refresh.

## Runtime switch

When `web/static_ts/` exists (after `bun run build`), `harnesslab serve`
**defaults to the TS bundle** (`HARNESSLAB_WEB_UI_VERSION` defaults to `ts`).

To force the legacy static UI:

```bash
export HARNESSLAB_WEB_UI_VERSION=legacy
uv run harnesslab serve --workspace-root .
```

If `static_ts/` is missing, the server falls back to legacy assets regardless
of the env var.

See also [`docs/README.md`](../docs/README.md) for the full documentation map.
