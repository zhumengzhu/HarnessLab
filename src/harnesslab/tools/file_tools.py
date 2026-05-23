from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

from harnesslab.core.config import RuntimeLimits
from harnesslab.core.models import ToolCall, ToolResult

# Directories that almost always belong to build/VCS metadata. The
# grep and glob tools skip these by default so the agent does not
# drown in noise from .git, virtualenvs, or compiled artifacts.
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        ".direnv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".harnesslab",
    }
)

_MAX_GREP_MATCHES_HARD_CAP = 1000
_MAX_GLOB_RESULTS_HARD_CAP = 5000


class ReadFileTool:
    name = "read_file"
    description = "Read a UTF-8 text file from inside the workspace."
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Workspace-relative file path."},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def __init__(self, workspace_root: Path, limits: RuntimeLimits | None = None) -> None:
        self._workspace_root = workspace_root
        self._limits = limits or RuntimeLimits()

    def execute(self, call: ToolCall) -> ToolResult:
        try:
            path = (self._workspace_root / str(call.args["path"])).resolve()
            content = path.read_text(encoding="utf-8")
            return ToolResult(ok=True, output=content[: self._limits.output_bytes_cap])
        except Exception as exc:
            return ToolResult(ok=False, output="", error=str(exc))


class WriteFileTool:
    name = "write_file"
    description = "Write a UTF-8 text file inside the workspace (creates parents)."
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Workspace-relative file path."},
            "content": {"type": "string", "description": "Text content to write."},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def __init__(self, workspace_root: Path, limits: RuntimeLimits | None = None) -> None:
        self._workspace_root = workspace_root
        self._limits = limits or RuntimeLimits()

    def execute(self, call: ToolCall) -> ToolResult:
        try:
            path = (self._workspace_root / str(call.args["path"])).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(call.args.get("content", "")), encoding="utf-8")
            return ToolResult(ok=True, output=f"wrote {path}")
        except Exception as exc:
            return ToolResult(ok=False, output="", error=str(exc))


class EditFileTool:
    """In-place string-replacement edit.

    Refuses to overwrite when ``old`` is not present, or when it
    appears more than once and ``replace_all`` is not set. This is the
    Phase 2.5 contract: the model must give us enough context that
    each edit targets exactly one location, otherwise the harness
    sends back a 'not unique' error and lets the model add more
    surrounding context.
    """

    name = "edit_file"
    description = (
        "Replace exactly one occurrence of ``old`` with ``new`` in a "
        "workspace file. Pass ``replace_all=true`` to replace every "
        "occurrence. Fails if ``old`` is missing or appears more than "
        "once and ``replace_all`` is not set."
    )
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Workspace-relative file path."},
            "old": {"type": "string", "description": "Text to find."},
            "new": {"type": "string", "description": "Text to write in its place."},
            "replace_all": {
                "type": "boolean",
                "description": "If true, replace every occurrence; default false.",
                "default": False,
            },
        },
        "required": ["path", "old", "new"],
        "additionalProperties": False,
    }

    def __init__(self, workspace_root: Path, limits: RuntimeLimits | None = None) -> None:
        self._workspace_root = workspace_root
        self._limits = limits or RuntimeLimits()

    def execute(self, call: ToolCall) -> ToolResult:
        try:
            path = (self._workspace_root / str(call.args["path"])).resolve()
            old = str(call.args["old"])
            new = str(call.args["new"])
            replace_all = bool(call.args.get("replace_all", False))
            if not old:
                return ToolResult(ok=False, output="", error="'old' must not be empty")
            if not path.is_file():
                return ToolResult(ok=False, output="", error=f"file not found: {path}")
            original = path.read_text(encoding="utf-8")
            occurrences = original.count(old)
            if occurrences == 0:
                return ToolResult(
                    ok=False, output="", error="'old' not found in file"
                )
            if occurrences > 1 and not replace_all:
                return ToolResult(
                    ok=False,
                    output="",
                    error=(
                        f"'old' is not unique ({occurrences} matches); "
                        "add more surrounding context or pass replace_all=true"
                    ),
                )
            replaced = (
                original.replace(old, new)
                if replace_all
                else original.replace(old, new, 1)
            )
            path.write_text(replaced, encoding="utf-8")
            return ToolResult(
                ok=True,
                output=(
                    f"edited {path} "
                    f"({occurrences if replace_all else 1} replacement"
                    f"{'s' if (occurrences if replace_all else 1) != 1 else ''})"
                ),
            )
        except Exception as exc:
            return ToolResult(ok=False, output="", error=str(exc))


class GrepTool:
    """Regex search across workspace files.

    Walks the workspace, opens each file as UTF-8 (binary files are
    skipped silently), and reports every line that matches the
    pattern. Designed to be a cheap structured search the agent can
    call without having to know which grep variant ships on the host.
    """

    name = "grep"
    description = (
        "Search workspace files for a regex pattern. "
        "Returns matches as ``path:lineno: line``. "
        "Use ``glob`` to narrow the file set, ``max_matches`` to "
        "bound the result size (default 50, hard cap 1000)."
    )
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Python regex."},
            "path": {
                "type": "string",
                "description": "Workspace-relative starting path (default: workspace root).",
            },
            "glob": {
                "type": "string",
                "description": "Optional fnmatch filter, e.g. '*.py'.",
            },
            "max_matches": {
                "type": "integer",
                "description": "Max matches to return (default 50, hard cap 1000).",
            },
        },
        "required": ["pattern"],
        "additionalProperties": False,
    }

    def __init__(self, workspace_root: Path, limits: RuntimeLimits | None = None) -> None:
        self._workspace_root = workspace_root
        self._limits = limits or RuntimeLimits()

    def execute(self, call: ToolCall) -> ToolResult:
        try:
            pattern_src = str(call.args["pattern"])
            try:
                pattern = re.compile(pattern_src)
            except re.error as exc:
                return ToolResult(
                    ok=False, output="", error=f"invalid regex: {exc}"
                )

            start = self._resolve_under_workspace(call.args.get("path"))
            if start is None:
                return ToolResult(ok=False, output="", error="path out of workspace")

            file_glob = call.args.get("glob")
            file_glob_str = str(file_glob) if file_glob else None
            requested = int(call.args.get("max_matches") or 50)
            max_matches = max(1, min(requested, _MAX_GREP_MATCHES_HARD_CAP))

            results: list[str] = []
            truncated = False
            for file_path in _iter_files(start, file_glob_str):
                try:
                    with file_path.open("r", encoding="utf-8") as fh:
                        for lineno, line in enumerate(fh, start=1):
                            if pattern.search(line):
                                rel = file_path.relative_to(self._workspace_root)
                                results.append(
                                    f"{rel}:{lineno}: {line.rstrip()}"
                                )
                                if len(results) >= max_matches:
                                    truncated = True
                                    break
                except (UnicodeDecodeError, OSError):
                    continue
                if truncated:
                    break

            if not results:
                return ToolResult(ok=True, output="(no matches)")
            output = "\n".join(results)
            if truncated:
                output += f"\n(truncated at {max_matches} matches)"
            output = output[: self._limits.output_bytes_cap]
            return ToolResult(ok=True, output=output)
        except Exception as exc:
            return ToolResult(ok=False, output="", error=str(exc))

    def _resolve_under_workspace(self, raw: object) -> Path | None:
        target = self._workspace_root if not raw else (
            self._workspace_root / str(raw)
        ).resolve()
        try:
            target.relative_to(self._workspace_root)
        except ValueError:
            return None
        return target


class GlobTool:
    """List files matching a glob pattern, scoped to the workspace."""

    name = "glob"
    description = (
        "List workspace files matching a glob pattern, e.g. ``**/*.py`` "
        "or ``src/**/test_*.ts``. Returns workspace-relative paths, "
        "one per line. Skips noisy build/VCS directories."
    )
    args_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern."},
            "path": {
                "type": "string",
                "description": "Workspace-relative starting path (default: workspace root).",
            },
            "max_results": {
                "type": "integer",
                "description": "Max paths to return (default 100, hard cap 5000).",
            },
        },
        "required": ["pattern"],
        "additionalProperties": False,
    }

    def __init__(self, workspace_root: Path, limits: RuntimeLimits | None = None) -> None:
        self._workspace_root = workspace_root
        self._limits = limits or RuntimeLimits()

    def execute(self, call: ToolCall) -> ToolResult:
        try:
            pattern = str(call.args["pattern"]).strip()
            if not pattern:
                return ToolResult(ok=False, output="", error="pattern is required")

            start = self._resolve_under_workspace(call.args.get("path"))
            if start is None:
                return ToolResult(ok=False, output="", error="path out of workspace")

            requested = int(call.args.get("max_results") or 100)
            max_results = max(1, min(requested, _MAX_GLOB_RESULTS_HARD_CAP))

            results: list[str] = []
            truncated = False
            for match in start.glob(pattern):
                if _has_skipped_parent(match, self._workspace_root):
                    continue
                if not match.is_file():
                    continue
                results.append(str(match.relative_to(self._workspace_root)))
                if len(results) >= max_results:
                    truncated = True
                    break

            if not results:
                return ToolResult(ok=True, output="(no matches)")
            results.sort()
            output = "\n".join(results)
            if truncated:
                output += f"\n(truncated at {max_results} results)"
            return ToolResult(ok=True, output=output[: self._limits.output_bytes_cap])
        except Exception as exc:
            return ToolResult(ok=False, output="", error=str(exc))

    def _resolve_under_workspace(self, raw: object) -> Path | None:
        target = self._workspace_root if not raw else (
            self._workspace_root / str(raw)
        ).resolve()
        try:
            target.relative_to(self._workspace_root)
        except ValueError:
            return None
        return target


# ---------------------------------------------------------------------------
# walk helpers shared by grep/glob
# ---------------------------------------------------------------------------


def _iter_files(start: Path, file_glob: str | None) -> list[Path]:
    """Walk ``start`` recursively, skipping noisy directories.

    Returned in sorted order for deterministic grep output.
    """

    out: list[Path] = []
    if start.is_file():
        if file_glob and not fnmatch.fnmatchcase(start.name, file_glob):
            return out
        out.append(start)
        return out
    for path in sorted(start.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if file_glob and not fnmatch.fnmatchcase(path.name, file_glob):
            continue
        out.append(path)
    return out


def _has_skipped_parent(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    return any(part in _SKIP_DIRS for part in rel.parts)
