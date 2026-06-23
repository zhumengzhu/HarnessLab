"""Load arms from accepted proposals."""

from __future__ import annotations

from pathlib import Path

from harnesslab.tune.online.loader import extract_suggested_prompt, load_online_arms


def test_extract_suggested_prompt_from_body() -> None:
    body = (
        "## Suggested prompt\n\n"
        "```text\n"
        "You are a terse assistant.\n"
        "```\n"
    )
    assert extract_suggested_prompt(body) == "You are a terse assistant."


def test_load_baseline_when_no_proposals(tmp_path: Path) -> None:
    arms = load_online_arms(proposals_dir=tmp_path / "missing", include_baseline=True)
    assert len(arms) == 1
    assert arms[0].source == "baseline"


def test_load_accepted_proposal(tmp_path: Path) -> None:
    props = tmp_path / "proposals"
    props.mkdir()
    (props / "prompt_test.md").write_text(
        "---\n"
        "id: prompt_test\n"
        "status: accepted\n"
        "kind: prompt_tuning\n"
        "best_id: cand_custom\n"
        "---\n\n"
        "## Suggested prompt\n\n"
        "```text\n"
        "Custom system prompt.\n"
        "```\n",
        encoding="utf-8",
    )
    arms = load_online_arms(proposals_dir=props, include_baseline=True)
    ids = {a.id for a in arms}
    assert "cand_custom" in ids
