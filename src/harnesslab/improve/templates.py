"""Static templates for suggested actions and related-files hints.

Suggestions are deterministic strings keyed by cluster ``kind``. There
is no LLM call here — proposals are advisory text generated from
templates, consistent with the project Non-Goal of "fully automated
self-modifying code paths".
"""

from __future__ import annotations

_SUGGESTIONS: dict[str, list[str]] = {
    "tool_failure": [
        "Investigate the failing tool's input handling: are the args "
        "from the model well-formed for this call shape?",
        "Consider adding a defensive check in the tool implementation, "
        "or improving the tool's error message so a future model can "
        "recover instead of looping.",
        "If the failure is environmental (missing file, network), "
        "consider whether the tool should fail loudly or degrade gracefully.",
    ],
    "policy_denial": [
        "If the denied tool/command is legitimately needed in this "
        "workspace, extend the allowlist (e.g. "
        "`DefaultPolicy.shell_allowlist`) with a narrowly-scoped entry.",
        "Otherwise, improve the assistant-visible reply so the model "
        "learns to avoid this call shape on the next turn.",
        "Confirm the denylist still wins over the new allowlist entry; "
        "denylist must remain the final word for destructive commands.",
    ],
    "invalid_args": [
        "Check whether the SimpleModel command parser is producing the "
        "shape the tool's `args_schema` expects.",
        "If the schema is overly strict for a legitimate call shape, "
        "consider relaxing it. If the schema is right, the issue is "
        "upstream in the model.",
        "Add an eval task covering this args shape so the regression "
        "gate keeps the fix in place.",
    ],
    "eval_regression": [
        "Read the failing task's YAML to confirm the expected behavior.",
        "If the new behavior is correct and intentional, refresh the "
        "baseline via `harnesslab eval --update-baseline` (in its own "
        "reviewed commit).",
        "Otherwise, treat the failure as a bug and patch the loop; the "
        "task itself is the regression guard.",
    ],
}

_RELATED_FILES: dict[str, list[str]] = {
    "tool_failure": [
        "src/harnesslab/tools/",
        "src/harnesslab/core/loop.py",
    ],
    "policy_denial": [
        "src/harnesslab/policy/default_policy.py",
    ],
    "invalid_args": [
        "src/harnesslab/tools/",
        "src/harnesslab/core/simple_model.py",
    ],
    "eval_regression": [
        "eval/tasks/",
        "eval/baseline.json",
    ],
}

_DEFAULT_SUGGESTIONS = [
    "Investigate this failure manually; no template suggestion is "
    "available for this cluster kind yet.",
]


def suggestions_for(kind: str) -> list[str]:
    return list(_SUGGESTIONS.get(kind, _DEFAULT_SUGGESTIONS))


def related_files_for(kind: str) -> list[str]:
    return list(_RELATED_FILES.get(kind, []))
