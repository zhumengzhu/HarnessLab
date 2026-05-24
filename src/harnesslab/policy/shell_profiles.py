"""Named shell allowlist profiles for ``run_shell_safe``.

``dev`` (default) matches the historical Phase 2.5 expanded allowlist.
``read_only`` drops dev runners (``python``, ``pytest``, ``uv``, …).
``strict`` keeps a minimal inspection set plus read-only ``git``.
"""

from __future__ import annotations

# Commands the agent is permitted to invoke through ``run_shell_safe``.
#
# Scope: this allowlist defends against the agent issuing a single
# obviously-destructive command directly. It does NOT promise that
# ``python``/``pytest``/``uv run`` invocations cannot run arbitrary
# code — a malicious or buggy script can. The workspace sandbox
# (``cwd``) and the file tools' path checks remain the primary
# defenses for that. Add commands here only when they are clearly
# read-only or scoped to the workspace.
DEFAULT_SHELL_ALLOWLIST: frozenset[str] = frozenset(
    {
        "ls",
        "pwd",
        "echo",
        "cat",
        "head",
        "tail",
        "wc",
        "file",
        "du",
        "df",
        "stat",
        "which",
        "env",
        "date",
        "whoami",
        "hostname",
        "uname",
        "find",
        "tree",
        "python",
        "python3",
        "pytest",
        "ruff",
        "mypy",
        "uv",
        "git",
    }
)

PROFILE_DEV = DEFAULT_SHELL_ALLOWLIST

PROFILE_READ_ONLY: frozenset[str] = frozenset(
    {
        "ls",
        "pwd",
        "echo",
        "cat",
        "head",
        "tail",
        "wc",
        "file",
        "du",
        "df",
        "stat",
        "which",
        "env",
        "date",
        "whoami",
        "hostname",
        "uname",
        "find",
        "tree",
        "git",
    }
)

PROFILE_STRICT: frozenset[str] = frozenset(
    {
        "ls",
        "pwd",
        "echo",
        "cat",
        "head",
        "tail",
        "wc",
        "git",
    }
)

SHELL_PROFILES: dict[str, frozenset[str]] = {
    "dev": PROFILE_DEV,
    "default": PROFILE_DEV,
    "read_only": PROFILE_READ_ONLY,
    "strict": PROFILE_STRICT,
}

DEFAULT_SHELL_PROFILE = "dev"


def resolve_shell_profile(name: str | None) -> frozenset[str]:
    """Return the allowlist for ``name``; unknown names raise ``ValueError``."""

    key = (name or DEFAULT_SHELL_PROFILE).strip().lower()
    if key not in SHELL_PROFILES:
        known = ", ".join(sorted(SHELL_PROFILES))
        raise ValueError(f"unknown shell profile {name!r} (known: {known})")
    return SHELL_PROFILES[key]
