"""Live-model benchmark for prompt candidates.

This path is **deliberately isolated from ``eval`` / ``replay``**: it drives the
production loop with a real (non-deterministic) model and scores the final
reply with the prompt-quality checks in ``suite.py`` (instruction following,
conciseness, format, optional LLM-judge). It must never be wired into the
deterministic eval/replay paths.

The model is supplied by an injectable ``ModelFactory`` so the benchmark is
fully testable with a fake model (no network) and the live provider is opt-in
at the call site.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from harnesslab.core.budget import BudgetLimits
from harnesslab.core.config import RuntimeLimits
from harnesslab.core.contracts import ModelPort
from harnesslab.core.loop import HarnessLoop
from harnesslab.core.replay import ReplaySpanRecorder
from harnesslab.core.runtime import DEFAULT_REPLAY_CLOCK_START, FrozenClock, SeqIdProvider
from harnesslab.eval.runner import _build_tool_registry
from harnesslab.memory.in_memory import InMemoryMemoryStore
from harnesslab.policy.default_policy import DefaultPolicy
from harnesslab.session.in_memory import InMemorySessionStore
from harnesslab.tools.spawn_sub_agent import SpawnSubAgentTool
from harnesslab.tune.prompt.candidate import PromptCandidate
from harnesslab.tune.prompt.judge import Judge
from harnesslab.tune.prompt.suite import (
    PromptBenchmarkSuite,
    PromptBenchmarkTask,
    score_reply,
)

# candidate -> a fresh ModelPort whose composer reflects the candidate prompt.
ModelFactory = Callable[[PromptCandidate], ModelPort]


@dataclass(frozen=True)
class BenchmarkResult:
    """Aggregate pass count for one candidate across the suite (× repeats)."""

    candidate_id: str
    passes: int
    trials: int

    @property
    def pass_rate(self) -> float:
        return self.passes / self.trials if self.trials else 0.0


class PromptBenchmark:
    """Score prompt candidates by running the loop against a benchmark suite."""

    def __init__(
        self,
        suite: PromptBenchmarkSuite,
        model_factory: ModelFactory,
        *,
        repeats: int = 1,
        base_limits: RuntimeLimits | None = None,
        judge: Judge | None = None,
        clock_start: datetime | None = None,
    ) -> None:
        if repeats < 1:
            raise ValueError("repeats must be >= 1")
        self._suite = suite
        self._model_factory = model_factory
        self._repeats = repeats
        self._base_limits = base_limits or RuntimeLimits()
        self._judge = judge
        self._clock_start = clock_start or DEFAULT_REPLAY_CLOCK_START

    def run(self, candidate: PromptCandidate) -> BenchmarkResult:
        passes = 0
        trials = 0
        for _ in range(self._repeats):
            for task in self._suite.tasks:
                reply = self._drive(candidate, task)
                trials += 1
                if score_reply(task, reply, judge=self._judge):
                    passes += 1
        return BenchmarkResult(candidate_id=candidate.id, passes=passes, trials=trials)

    def _drive(self, candidate: PromptCandidate, task: PromptBenchmarkTask) -> str:
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            tools = _build_tool_registry(workspace, self._base_limits)
            model = self._model_factory(candidate)

            loop_holder: list[HarnessLoop] = []
            tools.register(SpawnSubAgentTool(lambda: loop_holder[0]))
            loop = HarnessLoop(
                model=model,
                policy=DefaultPolicy(
                    workspace_root=workspace, enable_spawn_sub_agent=True
                ),
                sessions=InMemorySessionStore(),
                tools=tools,
                spans=ReplaySpanRecorder(),
                clock=FrozenClock(start=self._clock_start),
                ids=SeqIdProvider(),
                limits=self._base_limits,
                memory=InMemoryMemoryStore(),
                workspace_root=workspace,
                budget_limits=BudgetLimits(enabled=False),
            )
            loop_holder.append(loop)

            session = loop.start(goal=task.id)
            return loop.run_session(session.id, task.input, max_steps=task.max_steps)
