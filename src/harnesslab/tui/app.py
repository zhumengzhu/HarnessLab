"""Textual TUI for HarnessLab (operator chat surface)."""

from __future__ import annotations

from pathlib import Path

from harnesslab.cli import build_runtime


def run_tui(workspace_root: Path) -> None:
    from textual.app import App, ComposeResult
    from textual.widgets import Footer, Header, Input, RichLog

    class HarnessTui(App):
        TITLE = "HarnessLab TUI"
        BINDINGS = [("q", "quit", "Quit")]

        def __init__(self, workspace: Path) -> None:
            super().__init__()
            self._workspace = workspace
            self._loop = build_runtime(workspace_root=workspace, storage_backend="sqlite")
            self._session = self._loop.start(goal="TUI session")

        def compose(self) -> ComposeResult:
            yield Header()
            yield RichLog(id="log", highlight=True, markup=True)
            yield Input(placeholder="Type a message and press Enter")
            yield Footer()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            text = event.value.strip()
            if not text:
                return
            log = self.query_one(RichLog)
            log.write(f"[bold cyan]you[/bold cyan]: {text}")
            event.input.value = ""
            response = self._loop.run_session(self._session.id, text, max_steps=5)
            log.write(f"[bold green]assistant[/bold green]: {response}")

    HarnessTui(workspace_root).run()
