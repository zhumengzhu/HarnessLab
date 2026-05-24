"""Prompt composition layer.

The composer is the only place where a ``Session`` is turned into the
text that a model adapter actually sends. Static blocks live as
``.md`` files under :mod:`harnesslab.core.prompt.blocks` so they can
be edited like documentation and version-controlled per change.
Dynamic blocks (env, AGENTS.md, planning, skills, tool guide) are appended by callers
that have the right context — those land in Phase 2.2 commit 2.

Stable public API:

- :class:`PromptBlock` — one labeled chunk of prompt text
- :class:`ComposedPrompt` — the assembled prompt + a serializable
  snapshot of which blocks contributed what
- :class:`PromptComposer` — turns a ``Session`` (plus optional extra
  blocks and template variables) into a ``ComposedPrompt``
"""

from harnesslab.core.prompt.block import ComposedPrompt, PromptBlock
from harnesslab.core.prompt.composer import (
    DEFAULT_STATIC_BLOCKS,
    PromptComposer,
    load_default_static_blocks,
)
from harnesslab.core.prompt.dynamic import (
    build_agents_md_block,
    build_env_block,
    build_planning_block,
    build_skills_block,
    build_tool_guide_block,
)

__all__ = [
    "ComposedPrompt",
    "DEFAULT_STATIC_BLOCKS",
    "PromptBlock",
    "PromptComposer",
    "build_agents_md_block",
    "build_env_block",
    "build_planning_block",
    "build_skills_block",
    "build_tool_guide_block",
    "load_default_static_blocks",
]
