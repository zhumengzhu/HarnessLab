"""Tests for session title derivation and LLM auto-naming."""

from __future__ import annotations

from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import Decision, Message, Session
from harnesslab.core.replay import ReplayTraceRecorder
from harnesslab.core.simple_model import SimpleModel
from harnesslab.core.title import (
    LiveTitleNamer,
    build_title_prompt,
    derive_title_from_text,
    sanitize_title,
)
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.tools.registry import ToolRegistry


def test_derive_title_truncates_long_first_line() -> None:
    long_line = "x" * 100
    title = derive_title_from_text(long_line)
    assert len(title) <= 60
    assert title.endswith("…")


def test_sanitize_title_strips_quotes_and_newlines() -> None:
    assert sanitize_title('  "Hello World"\n') == "Hello World"


def test_build_title_prompt_includes_user_and_assistant_excerpt() -> None:
    session = Session(
        id="s1",
        goal="goal",
        messages=[
            Message(role="user", content="fix the login bug", session_id="s1"),
            Message(role="assistant", content="I'll grep for login", session_id="s1"),
        ],
    )
    prompt = build_title_prompt(session)
    assert "fix the login bug" in prompt
    assert "grep for login" in prompt
    assert "3-6 words" in prompt


class _TitleModel:
    def decide(self, session: Session, user_input: str) -> Decision:
        return Decision(kind="final", assistant_message="Login Bug Fix")


def test_live_title_namer_returns_sanitized_title() -> None:
    session = Session(
        id="s1",
        goal="fix login",
        messages=[Message(role="user", content="fix login", session_id="s1")],
    )
    namer = LiveTitleNamer(_TitleModel())
    assert namer(session) == "Login Bug Fix"


class _ToolModel:
    def decide(self, session: Session, user_input: str) -> Decision:
        return Decision(kind="tool", tool_name="grep", tool_args={"pattern": "x"})


def test_live_title_namer_skips_tool_decisions() -> None:
    session = Session(id="s1", goal="x", messages=[])
    assert LiveTitleNamer(_ToolModel())(session) is None


def test_loop_auto_titles_after_first_turn(tmp_path) -> None:
    class FinalModel:
        def decide(self, session: Session, user_input: str) -> Decision:
            if session.goal == "(session-title)":
                return Decision(kind="final", assistant_message="Short Title Here")
            return Decision(kind="final", assistant_message="done")

    model = FinalModel()
    trace = ReplayTraceRecorder()
    loop = HarnessLoop(
        model=model,
        policy=DefaultPolicy(workspace_root=tmp_path),
        sessions=InMemorySessionStore(),
        tools=ToolRegistry(),
        trace=trace,
        title_namer=LiveTitleNamer(model),
    )
    session = loop.start(goal="explore codebase structure")
    loop.run_turn(session.id, "list python files")
    updated = loop._sessions.get(session.id)  # noqa: SLF001
    assert updated.title == "Short Title Here"
    titled = [e for e in trace.events if e.event_type == "session_titled"]
    assert len(titled) == 1
    assert titled[0].payload["source"] == "llm"


def test_loop_does_not_retitle_on_second_turn(tmp_path) -> None:
    calls = {"n": 0}

    class CountingNamer:
        def __call__(self, session: Session) -> str | None:
            calls["n"] += 1
            return "Named Once"

    loop = HarnessLoop(
        model=SimpleModel(),
        policy=DefaultPolicy(workspace_root=tmp_path),
        sessions=InMemorySessionStore(),
        tools=ToolRegistry(),
        trace=ReplayTraceRecorder(),
        title_namer=CountingNamer(),
    )
    session = loop.start(goal="a")
    loop.run_turn(session.id, "one")
    loop.run_turn(session.id, "two")
    assert calls["n"] == 1
