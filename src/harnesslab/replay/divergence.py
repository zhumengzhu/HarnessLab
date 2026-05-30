"""Compare two trace event lists and report semantic divergence.

Three normalizations are applied before comparison (semantic mode):

1. **ID normalization.** Every `prefix_<...>` id (ses_*, msg_*, tool_*,
   run_*) in payloads is replaced by `<prefix>_001`, `<prefix>_002`, …
   in the order each id first appears in the trace. The same mapping
   rule is applied to both traces independently, so two traces that
   use the same prefix-ordering for the same logical entities
   normalize to the same string.

2. **Timestamp scrubbing.** `created_at`, `started_at`, `ended_at`,
   and `duration_ms` are removed from the comparison surface so a
   trace produced by `SystemClock` can still match a replay produced
   by `FrozenClock`.

3. **Tool-output scrubbing.** `output_preview`, `output_size`, and
   `output_truncated` are removed because they reflect IO side effects
   (e.g. absolute paths inside tmp workspaces) that vary across runs
   but do not change loop behavior. Whether the tool was called, with
   which args, with what policy decision, and whether it succeeded
   (`ok` / `error`) are still compared.

Strict mode (`strict=True`) skips all normalizations and compares the
event lists byte-for-byte. Strict mode is only useful when both traces
were produced by the same deterministic clock + id + workspace.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass

from harnesslab.core.models import TraceEvent

_ID_PATTERN = re.compile(r"\b(ses|msg|tool|run)_[A-Za-z0-9]+\b")
_VOLATILE_FIELDS = (
    "created_at",
    "started_at",
    "ended_at",
    "duration_ms",
    "latency_ms",
    "request_tokens",
    "response_tokens",
    "total_tokens",
    "model_name",
    "provider",
    "output_preview",
    "output_size",
    "output_truncated",
    # The Phase 2.6 ContextSnapshot is informational telemetry: it
    # captures conversation/prompt token estimates that vary with
    # workspace paths embedded in tool outputs (e.g. tmp dirs). It is
    # not a behavioral signal so the replay/divergence detector
    # ignores it.
    "context",
)


@dataclass(frozen=True)
class Divergence:
    index: int
    kind: str  # "length_mismatch" | "event_type" | "payload"
    detail: str


@dataclass(frozen=True)
class DivergenceReport:
    matched: bool
    divergences: list[Divergence]
    original_len: int
    replayed_len: int

    def render(self) -> str:
        if self.matched:
            return (
                f"OK: replay matches original "
                f"({self.original_len} events)."
            )
        lines = [
            f"DIVERGED: {len(self.divergences)} difference(s) found "
            f"(original={self.original_len}, replayed={self.replayed_len})",
        ]
        for d in self.divergences:
            lines.append(f"  - [{d.index}] {d.kind}: {d.detail}")
        return "\n".join(lines)


def detect_divergence(
    original: list[TraceEvent],
    replayed: list[TraceEvent],
    *,
    strict: bool = False,
    ignore_event_types: frozenset[str] = frozenset(),
) -> DivergenceReport:
    """Return a DivergenceReport comparing the two event sequences."""

    if ignore_event_types:
        original = [e for e in original if e.event_type not in ignore_event_types]
        replayed = [e for e in replayed if e.event_type not in ignore_event_types]

    if strict:
        norm_orig = [_to_jsonable(e) for e in original]
        norm_repl = [_to_jsonable(e) for e in replayed]
    else:
        norm_orig = _normalize(original)
        norm_repl = _normalize(replayed)

    divergences: list[Divergence] = []
    common_len = min(len(norm_orig), len(norm_repl))

    for i in range(common_len):
        o, r = norm_orig[i], norm_repl[i]
        if o.get("event_type") != r.get("event_type"):
            divergences.append(
                Divergence(
                    index=i,
                    kind="event_type",
                    detail=f"original={o.get('event_type')!r} replayed={r.get('event_type')!r}",
                )
            )
            continue
        if o != r:
            divergences.append(
                Divergence(
                    index=i,
                    kind="payload",
                    detail=_diff_summary(o, r),
                )
            )

    if len(norm_orig) != len(norm_repl):
        divergences.append(
            Divergence(
                index=common_len,
                kind="length_mismatch",
                detail=f"original has {len(norm_orig)} events, replayed has {len(norm_repl)}",
            )
        )

    return DivergenceReport(
        matched=not divergences,
        divergences=divergences,
        original_len=len(original),
        replayed_len=len(replayed),
    )


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


def _to_jsonable(event: TraceEvent) -> dict:
    return event.model_dump(mode="json")


def _normalize(events: list[TraceEvent]) -> list[dict]:
    """Dump → normalize ids → scrub timestamps."""

    raw = [_to_jsonable(e) for e in events]
    id_map = _build_id_map(raw)
    return [_apply_normalization(e, id_map) for e in raw]


def _build_id_map(events: list[dict]) -> dict[str, str]:
    """Walk every string in every event, collecting prefix_<...> ids in
    first-appearance order and assigning each a stable `<prefix>_NNN`
    canonical form."""

    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}

    def visit(value: object) -> None:
        if isinstance(value, str):
            for match in _ID_PATTERN.finditer(value):
                full = match.group(0)
                if full in mapping:
                    continue
                prefix = match.group(1)
                counters[prefix] = counters.get(prefix, 0) + 1
                mapping[full] = f"{prefix}_{counters[prefix]:03d}"
        elif isinstance(value, dict):
            for v in value.values():
                visit(v)
        elif isinstance(value, list):
            for v in value:
                visit(v)

    for event in events:
        visit(event)
    return mapping


def _apply_normalization(event: dict, id_map: dict[str, str]) -> dict:
    cleaned = copy.deepcopy(event)
    for field in _VOLATILE_FIELDS:
        cleaned.pop(field, None)
    payload = cleaned.get("payload")
    if isinstance(payload, dict):
        for field in _VOLATILE_FIELDS:
            payload.pop(field, None)
    return _replace_ids(cleaned, id_map)


def _replace_ids(value: object, id_map: dict[str, str]) -> object:
    if isinstance(value, str):
        if not id_map:
            return value
        return _ID_PATTERN.sub(lambda m: id_map.get(m.group(0), m.group(0)), value)
    if isinstance(value, dict):
        return {k: _replace_ids(v, id_map) for k, v in value.items()}
    if isinstance(value, list):
        return [_replace_ids(v, id_map) for v in value]
    return value


def _diff_summary(orig: dict, repl: dict) -> str:
    """Compact JSON diff useful for humans reading divergence output."""

    o_json = json.dumps(orig, sort_keys=True)
    r_json = json.dumps(repl, sort_keys=True)
    if len(o_json) <= 200 and len(r_json) <= 200:
        return f"original={o_json} replayed={r_json}"
    diffs = []
    for key in sorted(set(orig.keys()) | set(repl.keys())):
        if orig.get(key) != repl.get(key):
            diffs.append(f"{key}: {orig.get(key)!r} != {repl.get(key)!r}")
    return "; ".join(diffs)
