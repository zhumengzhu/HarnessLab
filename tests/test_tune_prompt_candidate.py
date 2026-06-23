"""Unit tests for prompt candidates + candidate generators (Layer B2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from harnesslab.core.models import Decision
from harnesslab.tune.prompt.candidate import (
    CandidateParseError,
    ModelCandidateGenerator,
    PromptCandidate,
    StaticCandidateGenerator,
    baseline_candidate,
    default_system_prompt,
    freeze_candidates,
    load_candidates,
    make_model_text_generator,
)


def test_from_text_id_is_stable_and_content_addressed() -> None:
    a = PromptCandidate.from_text("  hello world  ")
    b = PromptCandidate.from_text("hello world")
    assert a.id == b.id
    assert a.id.startswith("cand_")
    assert a.system_prompt == "hello world"


def test_different_text_different_id() -> None:
    a = PromptCandidate.from_text("one")
    b = PromptCandidate.from_text("two")
    assert a.id != b.id


def test_default_system_prompt_non_empty() -> None:
    assert default_system_prompt().strip()


def test_baseline_candidate_uses_default_prompt() -> None:
    base = baseline_candidate()
    assert base.source == "baseline"
    assert base.system_prompt == default_system_prompt().strip()


def test_candidate_composer_uses_single_system_block() -> None:
    cand = PromptCandidate.from_text("be terse")
    blocks = cand.to_blocks()
    assert len(blocks) == 1
    assert blocks[0].role == "system"
    assert blocks[0].content == "be terse"
    assert blocks[0].origin == f"tune:{cand.id}"


def test_freeze_and_load_round_trip(tmp_path: Path) -> None:
    cands = [
        baseline_candidate(),
        PromptCandidate.from_text("variant A", label="a", source="model"),
    ]
    path = freeze_candidates(cands, tmp_path / "cands.json")
    loaded = load_candidates(path)
    assert [c.id for c in loaded] == [c.id for c in cands]
    assert loaded[1].source == "model"


def test_load_rejects_non_array(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"id": "x"}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_candidates(path)


def test_static_generator_truncates_to_n() -> None:
    gen = StaticCandidateGenerator(["a", "b", "c"])
    out = gen.generate(base_prompt="base", instruction="x", n=2)
    assert [c.system_prompt for c in out] == ["a", "b"]
    assert all(c.source == "manual" for c in out)


def test_model_generator_parses_json_array() -> None:
    def fake_llm(_prompt: str) -> str:
        return '["prompt one", "prompt two"]'

    gen = ModelCandidateGenerator(fake_llm)
    out = gen.generate(base_prompt="base", instruction="improve", n=5)
    assert [c.system_prompt for c in out] == ["prompt one", "prompt two"]
    assert all(c.source == "model" for c in out)


def test_model_generator_strips_code_fence() -> None:
    def fake_llm(_prompt: str) -> str:
        return '```json\n["only one"]\n```'

    gen = ModelCandidateGenerator(fake_llm)
    out = gen.generate(base_prompt="base", instruction="improve", n=3)
    assert [c.system_prompt for c in out] == ["only one"]


def test_model_generator_raises_on_non_json() -> None:
    gen = ModelCandidateGenerator(lambda _p: "not json at all")
    with pytest.raises(CandidateParseError):
        gen.generate(base_prompt="b", instruction="i", n=1)


def test_make_model_text_generator_returns_assistant_message() -> None:
    seen: dict[str, str] = {}

    class _Model:
        def decide(self, session, user_input):  # noqa: ANN001, ANN201
            seen["staged"] = session.messages[-1].content
            return Decision(kind="final", assistant_message='["one", "two"]')

    text_gen = make_model_text_generator(_Model())
    out = text_gen("please generate")
    assert out == '["one", "two"]'
    assert seen["staged"] == "please generate"


def test_model_text_generator_feeds_model_candidate_generator() -> None:
    class _Model:
        def decide(self, session, user_input):  # noqa: ANN001, ANN201
            return Decision(kind="final", assistant_message='["alpha", "beta"]')

    gen = ModelCandidateGenerator(make_model_text_generator(_Model()))
    out = gen.generate(base_prompt="base", instruction="improve", n=5)
    assert [c.system_prompt for c in out] == ["alpha", "beta"]
    assert all(c.source == "model" for c in out)


def test_model_generator_passes_n_and_instruction_into_prompt() -> None:
    seen: dict[str, str] = {}

    def fake_llm(prompt: str) -> str:
        seen["prompt"] = prompt
        return '["x"]'

    ModelCandidateGenerator(fake_llm).generate(
        base_prompt="BASEPROMPT", instruction="be concise", n=4
    )
    assert "4" in seen["prompt"]
    assert "be concise" in seen["prompt"]
    assert "BASEPROMPT" in seen["prompt"]
