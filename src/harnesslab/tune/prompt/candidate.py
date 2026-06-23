"""Frozen prompt candidates + candidate generators.

A ``PromptCandidate`` is the *whole* system prompt for one benchmark run. The
baseline candidate is the project's default composed system prompt; alternative
candidates replace it wholesale. Candidates are serialized to a JSON artifact
(``freeze_candidates``) **before** scoring — that frozen file is the boundary
between (possibly LLM-driven) generation and the live-model benchmark.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from hashlib import sha1
from pathlib import Path
from typing import Protocol

import json5
from pydantic import BaseModel

from harnesslab.core.contracts import ModelPort
from harnesslab.core.models import Message, Session
from harnesslab.core.prompt import PromptBlock, PromptComposer
from harnesslab.core.prompt.composer import DEFAULT_STATIC_BLOCKS

GENERATION_SYSTEM_PROMPT = (
    "You are a prompt-engineering assistant. Follow the user's instruction "
    "exactly and respond with ONLY the requested JSON. Do not call tools."
)


def default_system_prompt() -> str:
    """The project's default composed system prompt (baseline)."""

    return "\n\n".join(b.content for b in DEFAULT_STATIC_BLOCKS if b.content)


def _candidate_id(system_prompt: str) -> str:
    return "cand_" + sha1(system_prompt.encode("utf-8")).hexdigest()[:10]


class PromptCandidate(BaseModel):
    id: str
    label: str = ""
    system_prompt: str
    source: str = "manual"

    @classmethod
    def from_text(
        cls, system_prompt: str, *, label: str = "", source: str = "manual"
    ) -> PromptCandidate:
        text = system_prompt.strip()
        return cls(
            id=_candidate_id(text),
            label=label,
            system_prompt=text,
            source=source,
        )

    def to_blocks(self) -> list[PromptBlock]:
        return [
            PromptBlock(
                name="identity",
                content=self.system_prompt,
                origin=f"tune:{self.id}",
                role="system",
            )
        ]

    def composer(self) -> PromptComposer:
        return PromptComposer(static_blocks=self.to_blocks())


def baseline_candidate() -> PromptCandidate:
    return PromptCandidate.from_text(
        default_system_prompt(), label="baseline", source="baseline"
    )


def freeze_candidates(candidates: list[PromptCandidate], path: Path) -> Path:
    """Serialize candidates to a JSON artifact (the generation/scoring boundary)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [c.model_dump(mode="json") for c in candidates]
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def load_candidates(path: Path) -> list[PromptCandidate]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"candidates file must be a JSON array: {path}")
    return [PromptCandidate.model_validate(item) for item in data]


class CandidateGenerator(Protocol):
    def generate(
        self, *, base_prompt: str, instruction: str, n: int
    ) -> list[PromptCandidate]: ...


class StaticCandidateGenerator:
    """Wrap a fixed set of prompt texts as candidates (manual / tests)."""

    def __init__(self, prompts: list[str]) -> None:
        self._prompts = list(prompts)

    def generate(
        self, *, base_prompt: str, instruction: str, n: int
    ) -> list[PromptCandidate]:
        return [
            PromptCandidate.from_text(p, source="manual")
            for p in self._prompts[:n]
        ]


# A text-completion callable: prompt string -> raw completion text. Kept as a
# plain Callable so the LLM dependency is injectable and the generator is
# testable without any network.
TextGenerator = Callable[[str], str]


def generation_composer() -> PromptComposer:
    """A minimal composer for the candidate-generation model call.

    Uses only the neutral ``GENERATION_SYSTEM_PROMPT`` (not the agent's full
    identity prompt) so the generation request is not biased by the very
    prompt we are trying to improve.
    """

    return PromptComposer(
        static_blocks=[
            PromptBlock(
                name="identity",
                content=GENERATION_SYSTEM_PROMPT,
                origin="tune:generation",
                role="system",
            )
        ]
    )


def make_model_text_generator(model: ModelPort) -> TextGenerator:
    """Wrap any ``ModelPort`` as a one-shot ``TextGenerator``.

    Providers read the prompt from ``session.messages`` (the loop appends the
    user turn before calling ``decide``), so we stage a single user message and
    return the model's assistant text. Pair with a model built with empty tool
    specs so it answers directly instead of trying to call a tool.
    """

    def generate(prompt: str) -> str:
        session = Session(goal="prompt-candidate-generation")
        session.messages.append(Message(role="user", content=prompt))
        decision = model.decide(session, prompt)
        return decision.assistant_message or ""

    return generate

_META_PROMPT = """\
You are improving the system prompt of a coding agent. Produce {n} distinct
candidate system prompts that follow this instruction:

{instruction}

Base system prompt:
---
{base_prompt}
---

Respond with ONLY a JSON array of {n} strings (each a complete system prompt).
"""


class ModelCandidateGenerator:
    """Ask a ``TextGenerator`` (an LLM) for candidate prompt variants.

    The completion is parsed as a JSON array of strings. Generation happens
    offline; callers ``freeze_candidates`` the result before scoring.
    """

    def __init__(self, generate_text: TextGenerator) -> None:
        self._generate_text = generate_text

    def generate(
        self, *, base_prompt: str, instruction: str, n: int
    ) -> list[PromptCandidate]:
        meta = _META_PROMPT.format(
            n=n, instruction=instruction.strip(), base_prompt=base_prompt.strip()
        )
        raw = self._generate_text(meta)
        variants = _parse_string_list(raw)
        return [
            PromptCandidate.from_text(v, source="model")
            for v in variants[:n]
            if v.strip()
        ]


class CandidateParseError(ValueError):
    """Raised when an LLM completion is not a usable JSON array of strings."""


def _parse_string_list(raw: str) -> list[str]:
    text = raw.strip()
    if text.startswith("```"):
        # Strip a fenced code block (```json ... ```), keep the inner body.
        inner = text.split("```", 2)
        text = inner[1] if len(inner) >= 2 else text
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json5.loads(text)
    except ValueError as exc:
        raise CandidateParseError(f"completion is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise CandidateParseError("completion JSON is not an array")
    return [str(item) for item in data]
