"""Textual TUI for HarnessLab (operator chat + trace surface)."""

from __future__ import annotations

import threading
from pathlib import Path

from rich.markdown import Markdown

from harnesslab.cli import build_runtime
from harnesslab.core.models import Session
from harnesslab.core.operator_config import OperatorConfig, load_operator_config
from harnesslab.core.stream_context import bind_stream_sink, reset_stream_sink
from harnesslab.replay.span_reader import read_spans
from harnesslab.telemetry.recorder_factory import default_spans_path
from harnesslab.tui.history import search_messages
from harnesslab.tui.session_list import (
    filter_sessions,
    format_status_line,
    input_placeholder_for,
    session_label,
)
from harnesslab.tui.settings_actions import (
    apply_failover,
    apply_model_backend,
    format_help,
    format_settings_summary,
    parse_slash_command,
    slash_suggestions,
)
from harnesslab.tui.span_feed import SpanFeedFormatter


def run_tui(workspace_root: Path) -> None:
    from textual import on, work
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.suggester import SuggestFromList
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
            ("f", "fork_session", "Fork"),
            ("r", "refresh_sessions", "Refresh"),
            ("v", "toggle_verbose", "Verbose"),
            ("y", "copy_reply", "Copy"),
            ("pageup", "scroll_chat_up", "Scroll up"),
            ("pagedown", "scroll_chat_down", "Scroll down"),
            ("escape", "cancel_turn", "Stop"),
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
            self._verbose = False
            self._cancel_event = threading.Event()
            self._session_filter = ""
            self._last_reply = ""
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
                    yield Input(
                        id="composer",
                        placeholder="Message · /compact · /help",
                        suggester=SuggestFromList(
                            slash_suggestions(), case_sensitive=False
                        ),
                    )
                yield RichLog(id="trace-pane", highlight=True, markup=True, wrap=True)
            yield Static(id="status-bar")
            yield Footer()

        def on_mount(self) -> None:
            self._refresh_sessions(select_id=self._session.id)
            self._update_status()
            self._sync_input_placeholder()
            self._sync_last_reply()
            self.query_one("#chat-log", RichLog).write(
                "[dim]HarnessLab TUI — n=new · f=fork · v=verbose · s=settings · "
                "/model · /failover · q=quit[/dim]"
            )

        def _sync_input_placeholder(self) -> None:
            composer = self.query_one("#composer", Input)
            composer.placeholder = input_placeholder_for(self._session.status)

        def _sync_last_reply(self) -> None:
            replies = [
                m.content
                for m in self._session.messages
                if m.role == "assistant" and m.content.strip()
            ]
            self._last_reply = replies[-1] if replies else ""

        def _update_status(self) -> None:
            session = self._loop._sessions.get(self._session.id)  # noqa: SLF001
            bar = self.query_one("#status-bar", Static)
            bar.update(
                format_status_line(
                    session,
                    backend=self._operator_config.model_backend,
                    failover_enabled=self._operator_config.model_failover_enabled,
                    max_steps=self._max_steps,
                    session_filter=self._session_filter,
                )
            )

        def _refresh_sessions(self, *, select_id: str | None = None) -> None:
            sessions = filter_sessions(
                self._loop._sessions.list(limit=40),  # noqa: SLF001
                self._session_filter,
            )
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
            self._sync_input_placeholder()
            self._sync_last_reply()

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
            self._sync_input_placeholder()
            self._sync_last_reply()

        def action_fork_session(self) -> None:
            if self._busy:
                self.query_one("#chat-log", RichLog).write(
                    "[yellow]turn in progress…[/yellow]"
                )
                return
            forked = self._loop.fork(self._session.id)
            self._session = self._loop._sessions.get(forked.id)  # noqa: SLF001
            self._span_feed.reset()
            chat = self.query_one("#chat-log", RichLog)
            trace = self.query_one("#trace-pane", RichLog)
            chat.clear()
            trace.clear()
            chat.write(f"[dim]forked session {self._session.id}[/dim]")
            for message in self._session.messages:
                self._render_message(chat, message.role, message.content)
            self._refresh_trace_tree()
            self._refresh_sessions(select_id=self._session.id)
            self._update_status()
            self._sync_input_placeholder()
            self._sync_last_reply()

        def action_refresh_sessions(self) -> None:
            self._refresh_sessions(select_id=self._session.id)

        def action_toggle_verbose(self) -> None:
            self._verbose = not self._verbose
            state = "on" if self._verbose else "off"
            self.query_one("#chat-log", RichLog).write(
                f"[dim]trace verbose {state}[/dim]"
            )
            self._refresh_trace_tree()

        def action_show_help(self) -> None:
            self.query_one("#chat-log", RichLog).write(format_help())

        def action_copy_reply(self) -> None:
            chat = self.query_one("#chat-log", RichLog)
            if not self._last_reply.strip():
                chat.write("[dim]no reply to copy yet[/dim]")
                return
            self.copy_to_clipboard(self._last_reply)
            chat.write("[dim]copied last reply to clipboard[/dim]")

        def action_scroll_chat_up(self) -> None:
            self.query_one("#chat-log", RichLog).scroll_page_up()

        def action_scroll_chat_down(self) -> None:
            self.query_one("#chat-log", RichLog).scroll_page_down()

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
            if command == "/copy":
                self.action_copy_reply()
                return True
            if command == "/search":
                self._handle_search(" ".join(args))
                return True
            if command == "/rename":
                self._handle_rename(" ".join(args))
                return True
            if command == "/delete":
                self._handle_delete()
                return True
            if command == "/find":
                self._session_filter = " ".join(args)
                self._refresh_sessions(select_id=self._session.id)
                self._update_status()
                if self._session_filter.strip():
                    chat.write(f"[green]filter[/green] · {self._session_filter.strip()}")
                else:
                    chat.write("[dim]filter cleared[/dim]")
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

        def _handle_search(self, query: str) -> None:
            chat = self.query_one("#chat-log", RichLog)
            if not query.strip():
                chat.write("[yellow]/search <query>[/yellow]")
                return
            hits = search_messages(self._session.messages, query)
            if not hits:
                chat.write(f"[dim]no matches for {query.strip()!r}[/dim]")
                return
            chat.write(f"[green]{len(hits)} match(es) for[/green] {query.strip()}")
            for hit in hits:
                chat.write(f"[dim]#{hit.index} {hit.role}:[/dim] {hit.snippet}")

        def _handle_rename(self, title: str) -> None:
            chat = self.query_one("#chat-log", RichLog)
            new_title = title.strip()
            if not new_title:
                chat.write("[yellow]/rename <new title>[/yellow]")
                return
            self._session.title = new_title
            self._loop._sessions.save(self._session)  # noqa: SLF001
            self._refresh_sessions(select_id=self._session.id)
            chat.write(f"[green]renamed[/green] → {new_title}")

        def _handle_delete(self) -> None:
            chat = self.query_one("#chat-log", RichLog)
            if self._busy:
                chat.write("[yellow]turn in progress…[/yellow]")
                return
            deleted_id = self._session.id
            self._loop._sessions.delete(deleted_id)  # noqa: SLF001
            remaining = self._loop._sessions.list(limit=1)  # noqa: SLF001
            if remaining:
                self._session = self._loop._sessions.get(remaining[0].id)  # noqa: SLF001
            else:
                self._session = self._loop.start(goal="TUI session")
            self._session_filter = ""
            self._span_feed.reset()
            chat.clear()
            self.query_one("#trace-pane", RichLog).clear()
            chat.write(f"[dim]deleted session {deleted_id}[/dim]")
            chat.write(f"[dim]switched to session {self._session.id}[/dim]")
            for message in self._session.messages:
                self._render_message(chat, message.role, message.content)
            self._refresh_trace_tree()
            self._refresh_sessions(select_id=self._session.id)
            self._update_status()
            self._sync_input_placeholder()
            self._sync_last_reply()

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

        def action_cancel_turn(self) -> None:
            if not self._busy:
                return
            if self._cancel_event.is_set():
                return
            self._cancel_event.set()
            self.query_one("#chat-log", RichLog).write(
                "[yellow]stopping… (cancels at the next step)[/yellow]"
            )

        @work(thread=True)
        def _run_turn(self, text: str) -> None:
            self._busy = True
            self._cancel_event.clear()
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
                    should_cancel=self._cancel_event.is_set,
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
            self._render_assistant(chat, response)
            self._last_reply = response
            self._session = self._loop._sessions.get(self._session.id)  # noqa: SLF001
            if self._session.status == "waiting_user":
                chat.write("[yellow]⏳ the agent is waiting for your reply[/yellow]")
            self._refresh_trace_tree()
            self._update_status()
            self._sync_input_placeholder()
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
                verbose=self._verbose,
            )
            trace.clear()
            for line in lines:
                trace.write(line.markup)

        def _emit_spans(self) -> None:
            self._refresh_trace_tree()

        @staticmethod
        def _render_assistant(log: RichLog, content: str) -> None:
            log.write("[bold green]assistant[/bold green]:")
            if content.strip():
                log.write(Markdown(content))

        @staticmethod
        def _render_message(log: RichLog, role: str, content: str) -> None:
            if not content.strip():
                return
            if role == "user":
                log.write(f"[bold cyan]you[/bold cyan]: {content}")
            elif role == "assistant":
                HarnessTui._render_assistant(log, content)
            elif role == "tool":
                log.write(f"[magenta]tool[/magenta]: {content[:200]}")

    HarnessTui(workspace_root).run()
