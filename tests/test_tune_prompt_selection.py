"""Tests for Beta-Binomial success-rate ranking of candidates."""

from __future__ import annotations

from harnesslab.tune.prompt.benchmark import BenchmarkResult
from harnesslab.tune.prompt.candidate import PromptCandidate
from harnesslab.tune.prompt.selection import rank_candidates


def _cand(text: str) -> PromptCandidate:
    return PromptCandidate.from_text(text)


def test_higher_pass_rate_ranks_first() -> None:
    good = _cand("good")
    bad = _cand("bad")
    rankings = rank_candidates(
        [
            (bad, BenchmarkResult(bad.id, passes=1, trials=10)),
            (good, BenchmarkResult(good.id, passes=9, trials=10)),
        ]
    )
    assert rankings[0].candidate.id == good.id
    assert rankings[0].success_rate > rankings[1].success_rate


def test_lcb_rewards_more_evidence_at_equal_rate() -> None:
    # Both went a perfect run, but 10/10 is far more evidence than 1/1, so its
    # lower credible bound is higher and it ranks first.
    tiny = _cand("tiny")
    solid = _cand("solid")
    rankings = rank_candidates(
        [
            (tiny, BenchmarkResult(tiny.id, passes=1, trials=1)),
            (solid, BenchmarkResult(solid.id, passes=10, trials=10)),
        ]
    )
    assert rankings[0].candidate.id == solid.id
    assert rankings[0].low > rankings[1].low


def test_ranking_is_deterministic() -> None:
    a = _cand("a")
    b = _cand("b")
    scored = [
        (a, BenchmarkResult(a.id, passes=5, trials=10)),
        (b, BenchmarkResult(b.id, passes=5, trials=10)),
    ]
    first = [r.candidate.id for r in rank_candidates(scored)]
    second = [r.candidate.id for r in rank_candidates(scored)]
    assert first == second
