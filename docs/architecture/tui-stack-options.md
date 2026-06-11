# TUI Stack Options (Python Backend)

Status: **Beta** (Textual operator surface shipped; see [`guides/tui.md`](../guides/tui.md)).

## Context

HarnessLab keeps the backend runtime in Python. The question for a future
TUI is whether the client layer should also be Python, or JS/TS.

## Option A: Python-native TUI (recommended first)

Candidate stack:

- `Textual` (preferred) or `prompt_toolkit` + `rich`

Why:

- Reuses Python session/runtime types directly.
- Zero extra Node/TS runtime requirement for operators.
- Easy local packaging (`uv run harnesslab tui`).
- Strong async/event support and component model (Textual).

Trade-offs:

- UI component ecosystem is smaller than web React.
- Sharing UI code with TS Web app is limited.

## Option B: Node/TS terminal UI

Candidate stack:

- `Ink` (React for CLI) or `blessed` ecosystem

Why:

- Mental model aligns with TS web frontend.
- Possible partial component reuse at logic layer.

Trade-offs:

- Adds Node runtime dependency for terminal operator workflows.
- Harder integration with in-process Python loop unless using HTTP bridge.

## Option C: Hybrid (Python core + remote web terminal)

- Keep Python backend.
- Use web UI in terminal via browser/TTY bridge.

Trade-offs:

- More infrastructure complexity than native TUI.

## Recommendation

1. Keep backend in Python.
2. Build first TUI with **Python Textual** for fastest operator value.
3. Keep API/event contracts stable so a TS terminal client can be added later
   if needed.

This gives immediate usability without blocking TS web migration.
