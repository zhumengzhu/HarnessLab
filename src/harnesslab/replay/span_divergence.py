"""Compare two span forests and report semantic divergence (Observability v2 D7).

Normalizations (semantic mode):

1. Strip ``trace_id``, ``span_id``, ``parent_span_id``, all of ``metrics.*``
2. Strip timing fields on spans and events
3. ID-prefix normalization for ``ses_*``, ``tool_*``, etc. in attributes
4. Compare each turn trace as a canonical preorder tree
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Any

from harnesslab.core.models import SpanRecord
from harnesslab.telemetry.span_attributes import SPAN_TURN

_ID_PATTERN = re.compile(r"\b(ses|msg|tool|run|cp|trace|span)_[A-Za-z0-9]+\b")
_VOLATILE_SPAN_KEYS = frozenset(
    {
        "trace_id",
        "span_id",
        "parent_span_id",
        "start_time",
        "end_time",
        "duration_ms",
        "metrics",
        "resource",
    }
)
_VOLATILE_EVENT_KEYS = frozenset({"time"})
_VOLATILE_EVENT_ATTRS = frozenset({"reasoning_text"})


@dataclass(frozen=True)
class Divergence:
    index: int
    kind: str  # length_mismatch | turn_count | node | turn_index
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
                f"({self.original_len} span(s))."
            )
        lines = [
            f"DIVERGED: {len(self.divergences)} difference(s) found "
            f"(original={self.original_len}, replayed={self.replayed_len})",
        ]
        for d in self.divergences:
            lines.append(f"  - [{d.index}] {d.kind}: {d.detail}")
        return "\n".join(lines)


NodeSurface = tuple[
    str,
    str,
    dict[str, Any],
    list[tuple[str, dict[str, Any]]],
    list["NodeSurface"],
]


def detect_divergence(
    original: list[SpanRecord],
    replayed: list[SpanRecord],
    *,
    strict: bool = False,
    ignore_span_names: frozenset[str] = frozenset(),
) -> DivergenceReport:
    """Compare two span lists for a single session (or mixed sessions)."""

    if ignore_span_names:
        original = [s for s in original if s.name not in ignore_span_names]
        replayed = [s for s in replayed if s.name not in ignore_span_names]

    if strict:
        orig_turns = [_span_to_jsonable(s) for s in original]
        repl_turns = [_span_to_jsonable(s) for s in replayed]
        return _compare_flat_lists(orig_turns, repl_turns, len(original), len(replayed))

    orig_turns = _partition_turns(original)
    repl_turns = _partition_turns(replayed)
    divergences: list[Divergence] = []

    if len(orig_turns) != len(repl_turns):
        divergences.append(
            Divergence(
                index=0,
                kind="turn_count",
                detail=(
                    f"original has {len(orig_turns)} turn(s), "
                    f"replayed has {len(repl_turns)}"
                ),
            )
        )

    for idx, (orig_bucket, repl_bucket) in enumerate(
        zip(orig_turns, repl_turns, strict=False)
    ):
        orig_tree = _build_turn_tree(orig_bucket)
        repl_tree = _build_turn_tree(repl_bucket)
        if orig_tree is None and repl_tree is None:
            continue
        if orig_tree is None or repl_tree is None:
            divergences.append(
                Divergence(
                    index=idx,
                    kind="node",
                    detail=(
                        f"turn[{idx}]: missing root span "
                        f"(original={orig_tree is not None}, "
                        f"replayed={repl_tree is not None})"
                    ),
                )
            )
            continue
        orig_norm = _normalize_tree(orig_tree)
        repl_norm = _normalize_tree(repl_tree)
        _compare_preorder(
            orig_norm,
            repl_norm,
            path=f"turn[{idx}]",
            divergences=divergences,
            index=idx,
        )

    return DivergenceReport(
        matched=not divergences,
        divergences=divergences,
        original_len=len(original),
        replayed_len=len(replayed),
    )


# ---------------------------------------------------------------------------
# Turn partitioning (D7 step 1)
# ---------------------------------------------------------------------------


def _partition_turns(spans: list[SpanRecord]) -> list[list[SpanRecord]]:
    """Bucket spans by ``(session_id, trace_id)`` sorted by ``turn_index``."""

    buckets: dict[tuple[str, str], list[SpanRecord]] = {}
    turn_index: dict[tuple[str, str], int] = {}
    for span in spans:
        key = (span.session_id, span.trace_id)
        buckets.setdefault(key, []).append(span)
        turn_index[key] = span.turn_index

    ordered_keys = sorted(
        buckets.keys(),
        key=lambda k: (k[0], turn_index[k], _first_position(buckets[k])),
    )
    return [buckets[k] for k in ordered_keys]


def _first_position(spans: list[SpanRecord]) -> int:
    return 0


# ---------------------------------------------------------------------------
# Tree build (D7 step 2)
# ---------------------------------------------------------------------------


def _build_turn_tree(spans: list[SpanRecord]) -> dict[str, Any] | None:
    if not spans:
        return None
    roots = [s for s in spans if s.parent_span_id is None]
    if len(roots) != 1:
        roots = [s for s in spans if s.name == SPAN_TURN and s.parent_span_id is None]
    if len(roots) != 1:
        return None
    root = roots[0]
    child_map: dict[str | None, list[SpanRecord]] = {}
    for span in spans:
        child_map.setdefault(span.parent_span_id, []).append(span)

    def attach(span: SpanRecord) -> dict[str, Any]:
        children = child_map.get(span.span_id, [])
        return {"span": span, "children": [attach(c) for c in children]}

    return attach(root)


# ---------------------------------------------------------------------------
# Normalize (D7 step 3)
# ---------------------------------------------------------------------------


def _normalize_tree(node: dict[str, Any]) -> NodeSurface:
    raw_spans = _collect_spans(node)
    id_map = _build_id_map(raw_spans)
    return _normalize_node(node, id_map)


def _collect_spans(node: dict[str, Any]) -> list[SpanRecord]:
    spans = [node["span"]]
    for child in node["children"]:
        spans.extend(_collect_spans(child))
    return spans


def _normalize_node(node: dict[str, Any], id_map: dict[str, str]) -> NodeSurface:
    span: SpanRecord = node["span"]
    attrs = _normalize_attrs(dict(span.attributes), id_map)
    links = _normalize_links(span, id_map)
    if links:
        attrs = {**attrs, "_links": links}
    events = [
        (
            ev.name,
            _normalize_attrs(
                {k: v for k, v in ev.attributes.items() if k not in _VOLATILE_EVENT_ATTRS},
                id_map,
            ),
        )
        for ev in span.events
    ]
    children = [_normalize_node(child, id_map) for child in node["children"]]
    return (span.name, span.kind, attrs, events, children)


def _normalize_attrs(attrs: dict[str, Any], id_map: dict[str, str]) -> dict[str, Any]:
    cleaned = copy.deepcopy(attrs)
    for key in list(cleaned.keys()):
        if key.startswith("metrics."):
            cleaned.pop(key, None)
    return _replace_ids(cleaned, id_map)


def _normalize_links(span: SpanRecord, id_map: dict[str, str]) -> list[dict[str, Any]]:
    if not span.links:
        return []
    out: list[dict[str, Any]] = []
    for link in span.links:
        entry = {
            "linked_trace_id": id_map.get(link.trace_id, link.trace_id),
            "linked_span_id": id_map.get(link.span_id, link.span_id),
            "attributes": _normalize_attrs(dict(link.attributes), id_map),
        }
        out.append(entry)
    return out


def _build_id_map(spans: list[SpanRecord]) -> dict[str, str]:
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

    for span in spans:
        visit(span.model_dump(mode="json"))
    return mapping


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


# ---------------------------------------------------------------------------
# Preorder compare (D7 step 4)
# ---------------------------------------------------------------------------


def _compare_preorder(
    orig: NodeSurface,
    repl: NodeSurface,
    *,
    path: str,
    divergences: list[Divergence],
    index: int,
) -> None:
    if orig[:3] != repl[:3] or orig[3] != repl[3]:
        divergences.append(
            Divergence(
                index=index,
                kind="node",
                detail=_node_diff(path, orig, repl),
            )
        )
        return

    orig_children, repl_children = orig[4], repl[4]
    if len(orig_children) != len(repl_children):
        divergences.append(
            Divergence(
                index=index,
                kind="length_mismatch",
                detail=(
                    f"{path}: child count "
                    f"original={len(orig_children)} replayed={len(repl_children)}"
                ),
            )
        )
        common = min(len(orig_children), len(repl_children))
    else:
        common = len(orig_children)

    for i in range(common):
        child_path = f"{path}/{orig_children[i][0]}[{i}]"
        _compare_preorder(
            orig_children[i],
            repl_children[i],
            path=child_path,
            divergences=divergences,
            index=index,
        )


def _node_diff(path: str, orig: NodeSurface, repl: NodeSurface) -> str:
    parts: list[str] = [path]
    if orig[0] != repl[0]:
        parts.append(f"name: {orig[0]!r} != {repl[0]!r}")
    if orig[1] != repl[1]:
        parts.append(f"kind: {orig[1]!r} != {repl[1]!r}")
    if orig[2] != repl[2]:
        parts.append(
            f"attrs: {json.dumps(orig[2], sort_keys=True)[:120]} != "
            f"{json.dumps(repl[2], sort_keys=True)[:120]}"
        )
    if orig[3] != repl[3]:
        parts.append("events differ")
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Strict mode
# ---------------------------------------------------------------------------


def _span_to_jsonable(span: SpanRecord) -> dict[str, Any]:
    return span.model_dump(mode="json")


def _compare_flat_lists(
    orig: list[dict[str, Any]],
    repl: list[dict[str, Any]],
    orig_len: int,
    repl_len: int,
) -> DivergenceReport:
    divergences: list[Divergence] = []
    common = min(len(orig), len(repl))
    for i in range(common):
        if orig[i] != repl[i]:
            divergences.append(
                Divergence(
                    index=i,
                    kind="node",
                    detail=f"span #{i} differs",
                )
            )
    if len(orig) != len(repl):
        divergences.append(
            Divergence(
                index=common,
                kind="length_mismatch",
                detail=f"original has {len(orig)} spans, replayed has {len(repl)}",
            )
        )
    return DivergenceReport(
        matched=not divergences,
        divergences=divergences,
        original_len=orig_len,
        replayed_len=repl_len,
    )
