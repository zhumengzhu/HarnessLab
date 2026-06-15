"""Textual TUI for HarnessLab (operator chat + trace surface)."""

from __future__ import annotations

from pathlib import Path

from harnesslab.cli import build_runtime
from harnesslab.core.models import Session
from harnesslab.core.operator_config import OperatorConfig, load_operator_config
from harnesslab.core.stream_context import bind_stream_sink, reset_stream_sink
from harnesslab.replay.span_reader import read_spans
from harnesslab.telemetry.recorder_factory import default_spans_path
from harnesslab.tui.settings_actions import (
    apply_failover,
    apply_model_backend,
    format_settings_summary,
    parse_slash_command,
)
from harnesslab.tui.span_feed import SpanFeedFormatter


def run_tui(workspace_root: Path) -> None:
    from textual import on, work
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, RichLog, Static

    class SessionRow(ListItem):
        def __init__(self, session: Session) -> None:
            super().__init__()
            self.session = session

        def compose(self) -> ComposeResult:
            title = session_label(self.session)
            yield Label(title)

    class HarnessTui(App):
        TITLE = "HarnessLab TUI"
        CSS = """
        #sidebar { width: 28; min-width: 24; border-right: solid $primary; }
        #trace-pane { width: 1fr; border-left: solid $primary-darken-2; }
        #chat-log { height: 1fr; }
        #status-bar {
            dock: bottom;
            height: 1;
            background: $surface;
            color: $text-muted;
            padding: 0 1;
        }
        #stream-live {
            height: auto;
            max-height: 14;
            padding: 0 1;
            display: none;
        }
        #stream-live.visible { display: block; }
        """

        BINDINGS = [
            ("q", "quit", "Quit"),
            ("n", "new_session", "New"),
            ("r", "refresh_sessions", "Refresh"),
            ("?", "show_help", "Help"),
            ("s", "show_settings", "Settings"),
        ]

        def __init__(self, workspace: Path) -> None:
            super().__init__()
            self._workspace = workspace
            self._operator_config: OperatorConfig = load_operator_config()
            self._loop = build_runtime(
                workspace_root=workspace,
                storage_backend="sqlite",
                operator_config=self._operator_config,
            )
            self._session = self._loop.start(goal="TUI session")
            self._max_steps = self._operator_config.serve_max_steps
            self._spans_path = default_spans_path(workspace)
            self._span_feed = SpanFeedFormatter()
            self._busy = False
            self._stream_reasoning: list[str] = []
            self._stream_assistant: list[str] = []
            self._stream_started = False

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal():
                yield ListView(id="session-list")
                with Vertical(id="main-pane"):
                    yield RichLog(id="chat-log", highlight=True, markup=True, wrap=True)
                    yield Static(id="stream-live")
                    yield Input(placeholder="Message · /compact · /help")
                yield RichLog(id="trace-pane", highlight=True, markup=True, wrap=True)
            yield Static(id="status-bar")
            yield Footer()

        def on_mount(self) -> None:
            self._refresh_sessions(select_id=self._session.id)
            self._update_status()
            self.query_one("#chat-log", RichLog).write(
                "[dim]HarnessLab TUI — n=new · s=settings · /model · /failover · q=quit[/dim]"
            )

        def _update_status(self) -> None:
            session = self._loop._sessions.get(self._session.id)  # noqa: SLF001
            bar = self.query_one("#status-bar", Static)
            backend = self._operator_config.model_backend
            failover = "on" if self._operator_config.model_failover_enabled else "off"
            bar.update(
                f"session {self._session.id[:12]}… · model={backend} · "
                f"failover={failover} · turns={session.turn_count} · "
                f"steps={session.step_count} · max_steps={self._max_steps}"
            )

        def _refresh_sessions(self, *, select_id: str | None = None) -> None:
            sessions = self._loop._sessions.list(limit=40)  # noqa: SLF001
            view = self.query_one("#session-list", ListView)
            view.clear()
            active_id = select_id or self._session.id
            for session in sessions:
                view.append(SessionRow(session))
            if sessions:
                index = next(
                    (i for i, s in enumerate(sessions) if s.id == active_id),
                    0,
                )
                view.index = index

        @on(ListView.Selected, "#session-list")
        def _on_session_selected(self, event: ListView.Selected) -> None:
            item = event.item
            if not isinstance(item, SessionRow):
                return
            self._session = self._loop._sessions.get(item.session.id)  # noqa: SLF001
            self._span_feed.reset()
            chat = self.query_one("#chat-log", RichLog)
            trace = self.query_one("#trace-pane", RichLog)
            chat.clear()
            trace.clear()
            chat.write(f"[dim]resumed session {self._session.id}[/dim]")
            for message in self._session.messages:
                self._render_message(chat, message.role, message.content)
            self._refresh_trace_tree()
            self._update_status()

        def action_new_session(self) -> None:
            self._session = self._loop.start(goal="TUI session")
            self._span_feed.reset()
            self.query_one("#chat-log", RichLog).clear()
            self.query_one("#trace-pane", RichLog).clear()
            self.query_one("#chat-log", RichLog).write(
                f"[dim]new session {self._session.id}[/dim]"
            )
            self._refresh_sessions(select_id=self._session.id)
            self._update_status()

        def action_refresh_sessions(self) -> None:
            self._refresh_sessions(select_id=self._session.id)

        def action_show_help(self) -> None:
            chat = self.query_one("#chat-log", RichLog)
            chat.write(
                "[dim]/compact · /settings · /model simple|deepseek|… · "
                "/failover on|off · n=new session · s=settings[/dim]"
            )

        def action_show_settings(self) -> None:
            chat = self.query_one("#chat-log", RichLog)
            chat.write(f"[dim]{format_settings_summary(self._operator_config)}[/dim]")

        def _handle_slash(self, text: str) -> bool:
            parsed = parse_slash_command(text)
            if parsed is None:
                return False
            command, args = parsed
            chat = self.query_one("#chat-log", RichLog)
            if command in {"/help", "/?"}:
                self.action_show_help()
                return True
            if command == "/settings":
                self.action_show_settings()
                return True
            if command == "/failover":
                flag = args[0]
                if flag not in {"on", "off"}:
                    chat.write("[yellow]/failover on|off[/yellow]")
                    return True
                try:
                    self._operator_config = apply_failover(
                        self._loop,
                        workspace_root=self._workspace,
                        config=self._operator_config,
                        enabled=flag == "on",
                        fallbacks=list(self._operator_config.model_fallbacks) or None,
                    )
                    chat.write(
                        f"[green]failover {flag}[/green] · "
                        f"{format_settings_summary(self._operator_config)}"
                    )
                    self._update_status()
                except Exception as exc:  # noqa: BLE001
                    chat.write(f"[red]failover failed: {exc}[/red]")
                return True
            if command == "/model":
                backend = args[0]
                try:
                    self._operator_config, norm = apply_model_backend(
                        self._loop,
                        workspace_root=self._workspace,
                        config=self._operator_config,
                        backend=backend,
                    )
                    chat.write(f"[green]model → {norm}[/green]")
                    self._update_status()
                except Exception as exc:  # noqa: BLE001
                    chat.write(f"[red]model switch failed: {exc}[/red]")
                return True
            return False

        @on(Input.Submitted)
        def _on_input(self, event: Input.Submitted) -> None:
            text = event.value.strip()
            event.input.value = ""
            if not text:
                return
            if self._handle_slash(text):
                return
            if self._busy:
                self.query_one("#chat-log", RichLog).write("[yellow]turn in progress…[/yellow]")
                return
            self.query_one("#chat-log", RichLog).write(f"[bold cyan]you[/bold cyan]: {text}")
            self._run_turn(text)

        @work(thread=True)
        def _run_turn(self, text: str) -> None:
            self._busy = True
            self._stream_started = False
            self._stream_reasoning = []
            self._stream_assistant = []

            def on_delta(kind: str, delta: str, _step_index: int) -> None:
                if not delta:
                    return
                if not self._stream_started:
                    self._stream_started = True
                    self.call_from_thread(self._begin_stream)
                self.call_from_thread(self._append_stream_delta, kind, delta)

            token = bind_stream_sink(on_delta)
            streamed = False
            try:
                response = self._loop.run_session(
                    self._session.id,
                    text,
                    max_steps=self._max_steps,
                )
                streamed = self._stream_started
            finally:
                reset_stream_sink(token)
                self._busy = False
            self.call_from_thread(self._finish_turn, response, streamed)

        def _begin_stream(self) -> None:
            live = self.query_one("#stream-live", Static)
            live.add_class("visible")
            live.update("[dim]streaming…[/dim]")

        def _append_stream_delta(self, kind: str, text: str) -> None:
            if kind == "reasoning":
                self._stream_reasoning.append(text)
            else:
                self._stream_assistant.append(text)
            live = self.query_one("#stream-live", Static)
            parts: list[str] = []
            if self._stream_reasoning:
                parts.append(f"[dim italic]{''.join(self._stream_reasoning)}[/dim italic]")
            if self._stream_assistant:
                parts.append(
                    f"[bold green]assistant[/bold green]: {''.join(self._stream_assistant)}"
                )
            live.update("\n".join(parts) if parts else "[dim]streaming…[/dim]")

        def _clear_stream_preview(self) -> None:
            live = self.query_one("#stream-live", Static)
            live.remove_class("visible")
            live.update("")

        def _finish_turn(self, response: str, streamed: bool) -> None:
            chat = self.query_one("#chat-log", RichLog)
            self._clear_stream_preview()
            if streamed and self._stream_reasoning:
                chat.write(f"[dim italic]{''.join(self._stream_reasoning)}[/dim italic]")
            chat.write(f"[bold green]assistant[/bold green]: {response}")
            self._session = self._loop._sessions.get(self._session.id)  # noqa: SLF001
            self._refresh_trace_tree()
            self._update_status()
            self._refresh_sessions(select_id=self._session.id)

        def _refresh_trace_tree(self) -> None:
            path = self._spans_path
            trace = self.query_one("#trace-pane", RichLog)
            if not path.is_file():
                trace.clear()
                return
            spans = read_spans(path)
            lines = self._span_feed.render_session_tree(
                spans,
                session_id=self._session.id,
            )
            trace.clear()
            for line in lines:
                trace.write(line.markup)

        def _emit_spans(self) -> None:
            self._refresh_trace_tree()

        @staticmethod
        def _render_message(log: RichLog, role: str, content: str) -> None:
            if not content.strip():
                return
            if role == "user":
                log.write(f"[bold cyan]you[/bold cyan]: {content}")
            elif role == "assistant":
                log.write(f"[bold green]assistant[/bold green]: {content}")
            elif role == "tool":
                log.write(f"[magenta]tool[/magenta]: {content[:200]}")

    HarnessTui(workspace_root).run()


def session_label(session: Session) -> str:
    title = (session.title or session.goal or "session").strip()
    if len(title) > 22:
        title = f"{title[:19]}…"
    return f"{title} · t{session.turn_count}"
