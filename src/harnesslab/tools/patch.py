"""Unified-diff patch parsing and application."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.models import ToolCall, ToolResult

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

@dataclass(frozen=True)
class PatchHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[str, ...]


def parse_unified_patch(patch: str) -> list[PatchHunk]:
    """Parse unified-diff hunks from ``patch`` text.

    ``---`` / ``+++`` file headers are ignored. Only ``@@`` hunks are
    required (matching the common ``apply_patch`` tool contract where
    ``path`` is passed separately).
    """

    hunks: list[PatchHunk] = []
    current_lines: list[str] | None = None
    header: re.Match[str] | None = None

    def flush() -> None:
        nonlocal current_lines, header
        if header is None or current_lines is None:
            return
        old_start = int(header.group(1))
        old_count = int(header.group(2) or "1")
        new_start = int(header.group(3))
        new_count = int(header.group(4) or "1")
        hunks.append(
            PatchHunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                lines=tuple(current_lines),
            )
        )
        current_lines = None
        header = None

    for raw in patch.splitlines():
        if raw.startswith("--- ") or raw.startswith("+++ "):
            continue
        match = _HUNK_HEADER.match(raw)
        if match:
            flush()
            header = match
            current_lines = []
            continue
        if current_lines is None:
            if not raw.strip():
                continue
            raise ValueError(f"patch line outside hunk: {raw!r}")
        if not raw:
            raise ValueError("empty line inside hunk (use ' ' prefix for context)")
        prefix = raw[0]
        if prefix not in {" ", "+", "-"}:
            raise ValueError(f"invalid hunk line prefix: {raw!r}")
        current_lines.append(raw)

    flush()
    if not hunks:
        raise ValueError("patch contains no hunks")
    return hunks


def apply_unified_patch(original: str, patch: str) -> str:
    """Return file text after applying ``patch`` hunks."""

    lines = original.splitlines()
    hunks = parse_unified_patch(patch)
    for hunk in sorted(hunks, key=lambda h: h.old_start, reverse=True):
        lines = _apply_hunk(lines, hunk)
    trailing_newline = original.endswith("\n")
    out = "\n".join(lines)
    if trailing_newline and out:
        out += "\n"
    return out


def _apply_hunk(lines: list[str], hunk: PatchHunk) -> list[str]:
    old_chunk: list[str] = []
    new_chunk: list[str] = []
    for row in hunk.lines:
        kind = row[0]
        text = row[1:]
        if kind in {" ", "-"}:
            old_chunk.append(text)
        if kind in {" ", "+"}:
            new_chunk.append(text)

    if len(old_chunk) != hunk.old_count:
        raise ValueError(
            f"hunk declares old_count={hunk.old_count} but has {len(old_chunk)} old lines"
        )
    if len(new_chunk) != hunk.new_count:
        raise ValueError(
            f"hunk declares new_count={hunk.new_count} but has {len(new_chunk)} new lines"
        )

    start = hunk.old_start - 1
    end = start + hunk.old_count
    if start < 0 or end > len(lines):
        raise ValueError(f"hunk range {hunk.old_start},{hunk.old_count} out of file bounds")

    actual = lines[start:end]
    if actual != old_chunk:
        raise ValueError("hunk context does not match file contents")

    return lines[:start] + new_chunk + lines[end:]


class ApplyPatchTool:
    """Apply a unified-diff hunk to a workspace file.

    Expects ``path`` plus a ``patch`` body containing one or more
    ``@@`` hunks (``---``/``+++`` headers optional). Context lines
    must match exactly; mismatch is a hard error so the model can
    refresh and retry — same contract as :class:`EditFileTool`.
    """

    name = "apply_patch"
    description = (
        "Apply a unified-diff patch to a workspace file. "
        "Pass ``path`` and ``patch`` with ``@@ -start,count +start,count @@`` "
        "hunks using ' ', '-', '+' line prefixes. Fails when context "
        "does not match."
    )
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Workspace-relative file path."},
            "patch": {
                "type": "string",
                "description": "Unified diff hunks to apply.",
            },
        },
        "required": ["path", "patch"],
        "additionalProperties": False,
    }

    def __init__(self, workspace_root: Path, limits: RuntimeLimits | None = None) -> None:
        self._workspace_root = workspace_root
        self._limits = limits or RuntimeLimits()

    def execute(self, call: ToolCall) -> ToolResult:
        try:
            path = (self._workspace_root / str(call.args["path"])).resolve()
            patch = str(call.args["patch"])
            if not patch.strip():
                return ToolResult(ok=False, output="", error="'patch' must not be empty")
            if not path.is_file():
                return ToolResult(ok=False, output="", error=f"file not found: {path}")
            original = path.read_text(encoding="utf-8")
            try:
                updated = apply_unified_patch(original, patch)
            except ValueError as exc:
                return ToolResult(ok=False, output="", error=str(exc))
            path.write_text(updated, encoding="utf-8")
            hunk_count = len(parse_unified_patch(patch))
            return ToolResult(
                ok=True,
                output=f"patched {path} ({hunk_count} hunk{'s' if hunk_count != 1 else ''})",
            )
        except Exception as exc:
            return ToolResult(ok=False, output="", error=str(exc))
