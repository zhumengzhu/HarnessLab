# HarnessLab TS WebUI

This directory hosts the TypeScript frontend foundation described in
`docs/architecture/frontend-ts-migration.md`.

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

1. Start server with TS bundle: `export HARNESSLAB_WEB_UI_VERSION=ts` then
   `uv run harnesslab serve --workspace-root ..` (or `./hl-serve start` from
   repo root after build).
2. In the browser, click **新对话** in the left **Sessions** panel.
3. Type in **Composer** at the bottom and press Enter to send.

Default UI mode is **Simple** (chat-focused). Switch to **Advanced** in the
header for trace, proposals, budget, and settings panels.

## Runtime switch

`harnesslab serve` keeps serving the legacy static UI by default.

To serve the TS build output:

```bash
export HARNESSLAB_WEB_UI_VERSION=ts
uv run harnesslab serve --workspace-root .
```

If `static_ts/` is missing, the server falls back to legacy assets.
