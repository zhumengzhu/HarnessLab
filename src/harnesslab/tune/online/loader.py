"""Load bandit arms from accepted proposals and the baseline prompt."""

from __future__ import annotations

import re
from pathlib import Path

from harnesslab.tune.online.models import OnlineArm
from harnesslab.tune.prompt.candidate import baseline_candidate

_PROMPT_FENCE = re.compile(
    r"## Suggested prompt\s*\n+```(?:text)?\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)


def extract_suggested_prompt(body: str) -> str | None:
    match = _PROMPT_FENCE.search(body)
    if not match:
        return None
    text = match.group(1).strip()
    if text.endswith("…(truncated)"):
        return None
    return text or None


def _parse_proposal_front_matter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}
    parsed: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        parsed[key.strip()] = raw.strip().strip('"')
    parsed["_body"] = "\n".join(lines[end + 1 :])
    return parsed


def load_online_arms(
    *,
    proposals_dir: Path,
    include_baseline: bool = True,
) -> list[OnlineArm]:
    """Return deduped arms: baseline (optional) + accepted ``prompt_tuning`` proposals."""

    arms: list[OnlineArm] = []
    seen: set[str] = set()

    if include_baseline:
        base = baseline_candidate()
        arms.append(
            OnlineArm(
                id=base.id,
                label=base.label or "baseline",
                system_prompt=base.system_prompt,
                source="baseline",
            )
        )
        seen.add(base.id)

    if proposals_dir.is_dir():
        for path in sorted(proposals_dir.glob("prompt_*.md")):
            meta = _parse_proposal_front_matter(path)
            if meta.get("status") != "accepted":
                continue
            if meta.get("kind") != "prompt_tuning":
                continue
            prompt = extract_suggested_prompt(meta.get("_body", ""))
            if not prompt:
                continue
            arm_id = meta.get("best_id") or meta.get("id") or path.stem
            if arm_id in seen:
                continue
            seen.add(arm_id)
            arms.append(
                OnlineArm(
                    id=arm_id,
                    label=path.stem,
                    system_prompt=prompt,
                    source="proposal",
                )
            )

    return arms
