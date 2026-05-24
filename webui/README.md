# HarnessLab TS WebUI (Phase A)

This directory hosts the TypeScript frontend foundation described in
`docs/architecture/frontend-ts-migration.md`.

## Commands

```bash
cd webui
npm install
npm run dev
npm run build
```

Build output goes to `src/harnesslab/web/static_ts/`.

## Runtime switch

`harnesslab serve` keeps serving the legacy static UI by default.

To serve the TS build output:

```bash
export HARNESSLAB_WEB_UI_VERSION=ts
uv run harnesslab serve --workspace-root .
```

If `static_ts/` is missing, the server falls back to legacy assets.
