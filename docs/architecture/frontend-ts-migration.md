# Frontend TS Migration RFC (OpenClaw-style)

Status: In progress (Phase A/B/C complete, Phase D started)

## Why this exists

HarnessLab's current Web UI is a lightweight static frontend
(`web/static/index.html` + `app.js`). It is good for rapid iteration,
but Phase 5+ features (proposal review, budgets, hooks, checkpoints,
streaming UX) benefit from:

- stronger type safety
- modular UI composition
- reusable API client + SSE abstractions
- better testability and maintainability

This RFC defines a migration plan to a TypeScript-based frontend,
while keeping the existing Python runtime and API contracts stable.

Current progress snapshot:

- `webui/` scaffold exists (Vite + React + TS + typed API/SSE helper stubs).
- Build target is `src/harnesslab/web/static_ts/`.
- `harnesslab serve` supports runtime switch via `HARNESSLAB_WEB_UI_VERSION=ts`
  with automatic fallback to legacy assets.
- Phase B read surfaces are live in TS UI (sessions/trace/proposals/settings).
- Phase C interactive parity shipped:
  - composer send + SSE `trace/done/error`
  - session fork action
  - `/remember` and `/skill` affordance buttons/modes
  - tool cards + stream error rendering
- Phase D started: proposal status transitions (accept/reject/supersede)
  wired in TS UI against guarded backend API, with explicit gate
  acknowledgements before `accepted`.
- Proposal panel includes gate-run buttons (`pytest`/`eval`) with inline
  pass/fail output cards to support operator decisions.
- Feature-slice migration started in code (`features/proposals`,
  `features/sessions`) to reduce `App.tsx` coupling.
- Continued split for shared surfaces (`features/composer`,
  `features/settings`) so `App.tsx` stays orchestration-focused.
- Trace and send-flow state handling are now split (`features/trace`,
  `features/composer/useComposerController`) to reduce top-level component
  state coupling.
- Frontend test skeleton started with Vitest (utility-level tests first,
  expanding toward component tests in later phases).
- Proposal panel component-level test coverage has started (`ProposalPanel`
  gate run + checkbox sync path).
- **Simple Chat Mode** (default): header toggle hides trace/proposals/settings
  until operator switches to Advanced; reduces onboarding friction for daily chat.

## Scope and non-goals

Scope:

- Migrate Web UI implementation to TypeScript incrementally.
- Preserve existing server APIs and session semantics.
- Keep localhost-first serving model (`harnesslab serve`).

Non-goals:

- No immediate backend rewrite to Node/TS.
- No distributed runtime or plugin marketplace changes.
- No forced redesign of loop/policy contracts during UI migration.

## Design principles (OpenClaw-inspired)

Reference style: clear contract boundaries, typed data models, modular
feature slices, and stable event streaming wrappers.

Apply to HarnessLab as:

1. **Typed boundary first**: generate/maintain TS API types from
   documented JSON payload shapes.
2. **Feature modules**: `sessions`, `trace`, `proposals`, `settings`,
   `composer` as independent UI modules.
3. **Single stream abstraction**: one SSE client layer for trace/done/error.
4. **State is explicit**: loading/error/empty states per feature module.
5. **Progressive migration**: old static UI remains fallback until parity.

## Target stack

- Runtime: `React` + `TypeScript`
- Build/dev: `Vite`
- Package manager: `bun` (primary) with npm-compatible scripts preserved
- Data fetching/cache: `@tanstack/react-query`
- Forms/validation: `zod` + thin helpers
- UI primitives: minimal local components first (no heavy design system initially)
- Testing:
  - Unit/component: `vitest` + `@testing-library/react`
  - E2E smoke (optional phase): `playwright` (UI only, no agent browser automation)

## Proposed directory layout

```
webui/
  src/
    app/
    features/
      sessions/
      trace/
      proposals/
      settings/
      composer/
    lib/
      api-client.ts
      sse-client.ts
      schemas.ts
    components/
  index.html
  vite.config.ts
```

Build output is copied/symlinked into `src/harnesslab/web/static/`
for `harnesslab serve` to host unchanged.

## API contract strategy

Do not change server routes as migration prerequisite. Keep:

- `GET /api/settings`
- `GET /api/sessions`
- `GET /api/sessions/{id}`
- `GET /api/sessions/{id}/trace`
- `POST /api/sessions`
- `POST /api/sessions/{id}/messages`
- `POST /api/sessions/{id}/fork`
- `GET /api/proposals`
- `GET /api/proposals/{id}`

Add typed TS schemas for each payload; keep runtime validation at API edge.

## Migration phases

### Phase A: foundation

- Initialize `webui/` with TS toolchain.
- Implement typed `api-client` + `sse-client`.
- Add build pipeline to emit assets consumed by Python server.

Exit: TS app can render shell and fetch `/api/health` + `/api/settings`.

### Phase B: read surfaces parity

- Migrate session list/detail rendering.
- Migrate trace panel (including hook events, budget events).
- Migrate proposal list/detail read-only panel.

Exit: old and new UI read paths are functionally equivalent.

### Phase C: interactive parity

- Migrate composer + send stream handling.
- Migrate fork, `/remember`, `/skill` affordances.
- Ensure tool cards and streaming done/error behavior parity.

Exit: core chat workflow parity complete.

### Phase D: advanced controls

- Proposal status transitions + gate actions UI.
- Budget/plan/hook richer visualizations.
- Session checkpoints/rewind UI (when backend is ready).

Exit: Phase 5 Web surfaces fully hosted in TS frontend.

### Phase E: default switch

- Make TS build output default served assets.
- Keep legacy static UI behind fallback switch for one release window.

Exit: legacy JS UI can be safely removed.

## Compatibility and rollout controls

- Config flag: `web.ui_version = legacy|ts` (or env override).
- During rollout:
  - CI runs existing Python tests + frontend TS tests.
  - No API breaking changes without schema/version notes.

## Frontend testing coverage strategy

The TS UI uses layered test coverage so migration can proceed without slowing
feature delivery:

- **Utility layer (fastest):** pure helpers in `features/*` and `lib/*`
  (example: proposal gate output summarization).
- **Component layer (current focus):** React Testing Library + Vitest around
  feature slices; mock `/api/*` and assert user-visible states (loading, error,
  success, disabled transitions).
- **Stream integration layer (next):** targeted SSE flow tests for
  `trace/done/error` ordering and tool-card rendering.
- **E2E smoke layer (optional):** Playwright checks for core chat workflows,
  run as a non-blocking lane until TS UI becomes default.

Current baseline:

- Proposal panel has utility coverage and component scenarios for:
  - gate success -> confirmation auto-check
  - gate failure -> confirmation reset behavior
  - gate API error -> inline error message rendering
- App-level mode toggle tests cover Simple default and Advanced panel visibility.

## Risks and mitigations

- **Risk:** API drift between Python and TS models.
  - **Mitigation:** shared schema snapshots + contract tests.
- **Risk:** SSE regressions under long-running tool turns.
  - **Mitigation:** dedicated stream integration tests.
- **Risk:** migration interrupts active feature delivery.
  - **Mitigation:** phased replacement, feature-by-feature.

## Acceptance criteria for scheduling

This migration remains deferred until:

1. Phase 5 core items are stable enough to avoid moving UI targets.
2. Phase 6 shape is settled (avoid remigrating around multi-agent UX shifts).
3. Web API contract is declared stable for one release cycle.

When these are met, this RFC becomes implementation plan-of-record.
