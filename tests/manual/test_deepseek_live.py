"""Optional live DeepSeek tests (real API, not in default CI).

Requires ``DEEPSEEK_API_KEY`` and explicit opt-in:

    RUN_DEEPSEEK_LIVE=1 DEEPSEEK_API_KEY=... \\
      uv run pytest tests/manual/test_deepseek_live.py -m network -v

Default model: ``deepseek-v4-flash``. Covers thinking disabled/enabled and
tool-loop ``reasoning_content`` replay (P2). Skips when the API key is
missing or when the model does not return a tool call (replay test only).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from harnesslab.cli import build_runtime
from harnesslab.core.config import RuntimeLimits
from harnesslab.core.models import Message, Session
from harnesslab.core.operator_config import OperatorConfig
from harnesslab.providers.deepseek import DeepSeekModel, tool_specs_from_registry
from harnesslab.session.sqlite_store import SqliteSessionStore
from harnesslab.tools.file_tools import ReadFileTool

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        os.getenv("RUN_DEEPSEEK_LIVE") != "1",
        reason="set RUN_DEEPSEEK_LIVE=1 to enable live DeepSeek tests",
    ),
]

_LIVE_MODEL = "deepseek-v4-flash"
_READ_FILE_PROMPT = (
    'You must call the read_file tool exactly once with path "ping.txt". '
    "Do not answer with plain text before calling the tool."
)


def _require_api_key() -> None:
    if not os.getenv("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY missing")


def _live_model(
    *,
    thinking: str,
    tool_specs_provider,
) -> DeepSeekModel:
    return DeepSeekModel(
        tool_specs_provider=tool_specs_provider,
        model_name=_LIVE_MODEL,
        thinking_mode=thinking,
    )


def _read_file_specs(tmp_path: Path) -> list[dict]:
    tool = ReadFileTool(tmp_path, limits=RuntimeLimits())
    return tool_specs_from_registry([tool])


def _session_with_tool_result(
    *,
    session_id: str,
    tool_call_id: str,
    tool_output: str,
    reasoning_text: str | None,
) -> Session:
    return Session(
        id=session_id,
        goal="live replay",
        created_at=datetime.now(UTC),
        messages=[
            Message(
                id="msg_user",
                role="user",
                content=_READ_FILE_PROMPT,
                created_at=datetime.now(UTC),
                session_id=session_id,
            ),
            Message(
                id="msg_asst",
                role="assistant",
                content="",
                created_at=datetime.now(UTC),
                session_id=session_id,
                tool_calls=[
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"path": "ping.txt"}),
                        },
                    }
                ],
                reasoning_text=reasoning_text,
            ),
            Message(
                id="msg_tool",
                role="tool",
                content=tool_output,
                created_at=datetime.now(UTC),
                session_id=session_id,
                tool_call_id=tool_call_id,
            ),
        ],
    )


def test_live_deepseek_v4_flash_final_thinking_disabled() -> None:
    """Smoke: default agent setting (thinking off) returns a final reply."""

    _require_api_key()
    model = _live_model(thinking="disabled", tool_specs_provider=lambda: [])
    session = Session(id="ses_live_off", goal="smoke", created_at=datetime.now(UTC))
    decision = model.decide(session, "Reply with exactly one short English sentence.")
    assert decision.kind == "final"
    assert decision.assistant_message
    assert model.last_call_meta()["model_name"] == _LIVE_MODEL
    assert "reasoning_text" not in model.last_call_meta()


def test_live_deepseek_v4_flash_final_thinking_enabled() -> None:
    """Smoke: thinking mode on still completes a simple final turn."""

    _require_api_key()
    model = _live_model(thinking="enabled", tool_specs_provider=lambda: [])
    session = Session(id="ses_live_on", goal="smoke", created_at=datetime.now(UTC))
    decision = model.decide(
        session,
        "Reply with exactly one short English sentence. No tools.",
    )
    assert decision.kind == "final"
    assert decision.assistant_message
    meta = model.last_call_meta()
    assert meta["model_name"] == _LIVE_MODEL
    if meta.get("reasoning_text"):
        assert isinstance(meta["reasoning_text"], str)


def test_live_deepseek_v4_flash_tool_call_thinking_enabled(tmp_path: Path) -> None:
    """Live tool call with thinking enabled (no replay yet)."""

    _require_api_key()
    (tmp_path / "ping.txt").write_text("live-ok", encoding="utf-8")
    specs = _read_file_specs(tmp_path)
    model = _live_model(thinking="enabled", tool_specs_provider=lambda: specs)
    session = Session(id="ses_live_tool", goal="read", created_at=datetime.now(UTC))
    decision = model.decide(session, _READ_FILE_PROMPT)
    if decision.kind != "tool":
        pytest.skip("live API did not return a tool call (model non-determinism)")
    assert decision.tool_name == "read_file"
    assert decision.tool_args.get("path") == "ping.txt"


def test_live_deepseek_tool_loop_reasoning_replay(tmp_path: Path) -> None:
    """After a tool result, a second call must accept replayed reasoning_content."""

    _require_api_key()
    (tmp_path / "ping.txt").write_text("live-ok", encoding="utf-8")
    specs = _read_file_specs(tmp_path)
    model = _live_model(thinking="enabled", tool_specs_provider=lambda: specs)
    session = Session(id="ses_live_replay", goal="replay", created_at=datetime.now(UTC))
    first = model.decide(session, _READ_FILE_PROMPT)
    if first.kind != "tool":
        pytest.skip("live API did not return a tool call on step 1")
    reasoning = model.last_call_meta().get("reasoning_text")
    if not reasoning:
        pytest.skip("live API did not return reasoning_content on tool step")

    replay_session = _session_with_tool_result(
        session_id="ses_live_replay",
        tool_call_id="call_live_1",
        tool_output="[tool:read_file] live-ok",
        reasoning_text=str(reasoning),
    )
    second = model.decide(replay_session, _READ_FILE_PROMPT)
    assert second.kind in {"final", "tool", "assistant"}
    assert not (second.assistant_message or "").startswith("DeepSeek request failed")


def test_live_deepseek_loop_tool_then_final_thinking_enabled(tmp_path: Path) -> None:
    """End-to-end: HarnessLoop + DeepSeek + read_file (best-effort)."""

    _require_api_key()
    (tmp_path / "ping.txt").write_text("live-loop-ok", encoding="utf-8")
    db_path = tmp_path / "live.sqlite"
    config = OperatorConfig(
        deepseek_model_name=_LIVE_MODEL,
        deepseek_thinking="enabled",
    )
    loop = build_runtime(
        tmp_path,
        model_backend="deepseek",
        storage_backend="sqlite",
        sqlite_path=db_path,
        operator_config=config,
    )
    session = loop.start(goal="read ping.txt via tool")
    response = loop.run_session(
        session.id,
        'Use read_file on "ping.txt", then reply with only the file content.',
        max_steps=3,
    )
    if "live-loop-ok" not in response:
        pytest.skip(
            "live loop did not finish with file content (model non-determinism): "
            f"{response!r}"
        )

    store = SqliteSessionStore(db_path)
    try:
        loaded = store.get(session.id)
    finally:
        store.close()
    tool_assistant = [m for m in loaded.messages if m.role == "assistant" and m.tool_calls]
    if tool_assistant and config.deepseek_thinking == "enabled":
        assert tool_assistant[0].reasoning_text is None or isinstance(
            tool_assistant[0].reasoning_text, str
        )
