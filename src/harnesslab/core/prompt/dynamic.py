"""Runtime-built prompt blocks.

These factories produce ``PromptBlock``s that the composer pastes
between the packaged static blocks and the conversation messages.
They are kept here (not in the composer or the adapters) so any
caller — DeepSeek today, future model adapters, the ``harnesslab
context`` CLI tomorrow — can share the same shape and labeling.

Conventions:

- All builders are pure functions; they take everything they need
  as arguments. This keeps the composer testable without monkey-
  patching ``os`` / ``subprocess``.
- ``build_agents_md_block`` / ``build_skills_block`` return ``None`` if
  no content exists so callers can skip the section instead of
  injecting empty blocks.
- Git inspection is best-effort and silently degrades when ``git`` is
  missing, when the workspace is not a git repo, or when the call
  times out.
"""

from __future__ import annotations

import platform
import subprocess
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harnesslab.core.prompt.block import PromptBlock

_GIT_TIMEOUT_SECONDS = 2.0


def build_env_block(
    workspace_root: Path,
    *,
    today: str | None = None,
    platform_str: str | None = None,
) -> PromptBlock:
    """Workspace metadata: cwd, platform, today, optional git summary."""

    cwd = str(workspace_root)
    today = today or datetime.now(UTC).date().isoformat()
    platform_str = platform_str or platform.platform()
    lines: list[str] = [
        "# Environment",
        "",
        f"- cwd: {cwd}",
        f"- platform: {platform_str}",
        f"- today: {today}",
    ]
    git_lines = _git_summary(workspace_root)
    if git_lines:
        lines.append("- git:")
        for entry in git_lines:
            lines.append(f"  - {entry}")
    return PromptBlock(name="env", content="\n".join(lines), origin="dynamic:env")


def build_agents_md_block(workspace_root: Path) -> PromptBlock | None:
    """Inject the workspace's ``AGENTS.md`` so it grounds the agent.

    Returns ``None`` when the file is missing or empty so the composer
    can skip the section cleanly.
    """

    candidate = workspace_root / "AGENTS.md"
    if not candidate.is_file():
        return None
    raw = candidate.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    return PromptBlock(
        name="agents_md",
        content=f"# AGENTS.md (workspace contract)\n\n{raw}",
        origin=f"dynamic:agents_md:{candidate.name}",
    )


def build_skills_block(workspace_root: Path) -> PromptBlock | None:
    """Inject workspace skill definitions from ``skills/*.md``.

    The block is intentionally read-only: it publishes skill names and
    markdown content as context, but does not execute anything.
    """

    skills_dir = workspace_root / "skills"
    if not skills_dir.is_dir():
        return None
    files = sorted(p for p in skills_dir.glob("*.md") if p.is_file())
    if not files:
        return None
    sections: list[str] = []
    for path in files:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            continue
        sections.append(f"## {path.stem}\n\n{raw}")
    if not sections:
        return None
    return PromptBlock(
        name="skills",
        content="# Skills\n\n" + "\n\n".join(sections),
        origin=f"dynamic:skills:{skills_dir.name}",
    )


def build_tool_guide_block(tools: Iterable[Any]) -> PromptBlock:
    """Plain-language summary of every tool the policy will admit.

    The OpenAI function-calling spec already goes into
    ``request_body["tools"]``; this block is intentionally
    redundant so models that don't parse the JSON spec well still
    see the tool surface in the system prompt.
    """

    lines: list[str] = ["# Tools available in this session"]
    for tool in tools:
        name = getattr(tool, "name", None)
        if not isinstance(name, str) or not name:
            continue
        description = getattr(tool, "description", "") or ""
        if not isinstance(description, str):
            description = ""
        lines.append(f"- `{name}`: {description.strip()}".rstrip())
    if len(lines) == 1:
        lines.append("- (no tools registered)")
    return PromptBlock(
        name="tool_guide",
        content="\n".join(lines),
        origin="dynamic:tool_guide",
    )


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


def _git_summary(workspace_root: Path) -> list[str]:
    """Return ``['branch: main', 'clean']`` or ``[]`` if unavailable."""

    git_dir = workspace_root / ".git"
    if not git_dir.exists():
        return []
    try:
        branch_proc = subprocess.run(
            ["git", "-C", str(workspace_root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
        status_proc = subprocess.run(
            ["git", "-C", str(workspace_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    branch = branch_proc.stdout.strip() or "(detached)"
    changes = sum(1 for line in status_proc.stdout.splitlines() if line.strip())
    return [
        f"branch: {branch}",
        "clean" if changes == 0 else f"{changes} change(s)",
    ]
