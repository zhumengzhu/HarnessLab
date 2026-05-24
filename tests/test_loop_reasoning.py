"""Loop persistence of provider reasoning on tool turns (Post-MVP P2)."""

from __future__ import annotations

from pathlib import Path

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.models import Decision, Session
from harnesslab.core.replay import ReplayTraceRecorder
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.tools.file_tools import WriteFileTool
from harnesslab.tools.registry import ToolRegistry


class _ReasoningThenFinalModel:
    """Stub adapter exposing ``last_call_meta`` like DeepSeekModel."""

    def __init__(self) -> None:
        self._meta: dict[str, str] = {}

    def decide(self, session: Session, user_input: str) -> Decision:
        _ = session, user_input
        if not self._meta:
            self._meta = {"reasoning_text": "internal chain-of-thought"}
            return Decision(
                kind="tool",
                tool_name="write_file",
                tool_args={"path": "out.txt", "content": "x"},
            )
        return Decision(kind="final", assistant_message="done")

    def last_call_meta(self) -> dict[str, str]:
        return dict(self._meta)


def test_loop_persists_reasoning_on_tool_assistant_message(tmp_path: Path) -> None:
    limits = RuntimeLimits()
    tools = ToolRegistry()
    tools.register(WriteFileTool(tmp_path, limits=limits))
    model = _ReasoningThenFinalModel()
    store = InMemorySessionStore()
    loop = HarnessLoop(
        model=model,
        policy=DefaultPolicy(workspace_root=tmp_path),
        sessions=store,
        tools=tools,
        trace=ReplayTraceRecorder(),
    )
    session = loop.start(goal="reasoning tool turn")
    loop.run_session(session.id, "write out.txt")

    loaded = store.get(session.id)
    assistant_tool_msgs = [
        m for m in loaded.messages if m.role == "assistant" and m.tool_calls
    ]
    assert len(assistant_tool_msgs) == 1
    assert assistant_tool_msgs[0].reasoning_text == "internal chain-of-thought"
