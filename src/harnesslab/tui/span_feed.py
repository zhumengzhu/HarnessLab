"""Format span records for TUI trace/activity panes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harnesslab.core.models import SpanRecord


@dataclass(frozen=True)
class SpanFeedLine:
    markup: str
    plain: str


class SpanFeedFormatter:
    """Track seen spans and emit Rich markup lines for new session spans."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def reset(self) -> None:
        self._seen.clear()

    def ingest(self, spans: list[SpanRecord], *, session_id: str) -> list[SpanFeedLine]:
        out: list[SpanFeedLine] = []
        for span in spans:
            if span.span_id in self._seen:
                continue
            attrs = span.attributes or {}
            if attrs.get("harnesslab.session.id") != session_id:
                continue
            self._seen.add(span.span_id)
            formatted = self._format_span(span, attrs)
            if formatted is not None:
                out.append(formatted)
            out.extend(self._format_events(span))
        return out

    def _format_span(
        self,
        span: SpanRecord,
        attrs: dict[str, Any],
        *,
        verbose: bool = False,
    ) -> SpanFeedLine | None:
        name = span.name
        metrics = span.metrics or {}

        if name.startswith("tool.hooks."):
            hook = attrs.get("harnesslab.hook.name", "hook")
            phase = attrs.get("harnesslab.hook.phase", "")
            return SpanFeedLine(
                markup=f"[yellow]hook[/yellow] {phase} · {hook}",
                plain=f"hook {phase} · {hook}",
            )

        if name.startswith("tool.") and not name.startswith("tool.hooks."):
            tool = attrs.get("harnesslab.tool.name", name[5:])
            ok = attrs.get("harnesslab.tool.ok", span.status == "ok")
            status = "ok" if ok else "error"
            duration = metrics.get("duration_ms")
            dur = f" · {int(duration)}ms" if isinstance(duration, (int, float)) else ""
            cap = 240 if verbose else 80
            preview = metrics.get("output_preview")
            preview_text = ""
            if isinstance(preview, str) and preview.strip():
                snippet = preview.replace("\n", " ").strip()[:cap]
                preview_text = f" — {snippet}"
            extra = ""
            if verbose:
                error = metrics.get("error")
                if not ok and isinstance(error, str) and error.strip():
                    extra += f" · [red]err:[/red] {error.strip()[:160]}"
                ref = metrics.get("artifact_ref")
                if isinstance(ref, str) and ref:
                    extra += f" · [dim]art:{ref}[/dim]"
            markup = f"[magenta]tool[/magenta] {tool} · {status}{dur}{preview_text}{extra}"
            plain = f"tool {tool} · {status}{dur}{preview_text}"
            return SpanFeedLine(markup=markup, plain=plain)

        if name == "llm.generate":
            parts: list[str] = []
            tokens = metrics.get("total_tokens")
            latency = metrics.get("latency_ms")
            if isinstance(tokens, int):
                parts.append(f"{tokens} tok")
            if isinstance(latency, (int, float)):
                parts.append(f"{int(latency)}ms")
            attempts = attrs.get("harnesslab.failover.attempts")
            if isinstance(attempts, int) and attempts > 1:
                backend = attrs.get("harnesslab.failover.backend", "?")
                parts.append(f"failover×{attempts}→{backend}")
            if verbose:
                parts.extend(_llm_verbose_parts(metrics))
            label = " · ".join(parts) if parts else "call"
            return SpanFeedLine(
                markup=f"[blue]llm[/blue] {label}",
                plain=f"llm {label}",
            )

        if name == "context.compact":
            trigger = attrs.get("harnesslab.compaction.trigger", "compact")
            return SpanFeedLine(
                markup=f"[cyan]compact[/cyan] · {trigger}",
                plain=f"compact · {trigger}",
            )

        if name == "sub_agent.run":
            goal = str(attrs.get("harnesslab.sub_agent.goal", ""))[:48]
            return SpanFeedLine(
                markup=f"[green]spawn[/green] sub-agent · {goal}",
                plain=f"spawn sub-agent · {goal}",
            )

        return None

    def _format_events(self, span: SpanRecord) -> list[SpanFeedLine]:
        lines: list[SpanFeedLine] = []
        for evt in span.events or []:
            attrs = evt.attributes or {}
            if evt.name == "tool.hook_blocked":
                hook = attrs.get("name", "hook")
                lines.append(
                    SpanFeedLine(
                        markup=f"[red]hook blocked[/red] · {hook}",
                        plain=f"hook blocked · {hook}",
                    )
                )
            elif evt.name == "tool.policy_denied":
                reason = attrs.get("reason", "denied")
                lines.append(
                    SpanFeedLine(
                        markup=f"[red]policy denied[/red] · {reason}",
                        plain=f"policy denied · {reason}",
                    )
                )
        return lines

    def render_session_tree(
        self, spans: list[SpanRecord], *, session_id: str, verbose: bool = False
    ) -> list[SpanFeedLine]:
        """Render a per-turn hierarchical span tree for the TUI trace pane."""

        session_spans = [
            span
            for span in spans
            if (span.attributes or {}).get("harnesslab.session.id") == session_id
        ]
        if not session_spans:
            return []

        by_trace: dict[str, list[SpanRecord]] = {}
        for span in session_spans:
            by_trace.setdefault(span.trace_id, []).append(span)

        trace_groups = sorted(
            by_trace.values(),
            key=lambda group: (
                min(span.turn_index for span in group),
                min(str(span.start_time) for span in group),
            ),
        )

        lines: list[SpanFeedLine] = []
        for group in trace_groups:
            turn = min(span.turn_index for span in group)
            lines.append(
                SpanFeedLine(
                    markup=f"[dim]── turn {turn} ──[/dim]",
                    plain=f"── turn {turn} ──",
                )
            )
            for span, depth in _preorder_tree(group):
                prefix = "  " * depth + ("├─ " if depth else "")
                attrs = span.attributes or {}
                formatted = self._format_span(span, attrs, verbose=verbose)
                if formatted is not None:
                    lines.append(
                        SpanFeedLine(
                            markup=f"{prefix}{formatted.markup}",
                            plain=f"{prefix}{formatted.plain}",
                        )
                    )
                for event_line in self._format_events(span):
                    event_prefix = "  " * (depth + 1)
                    lines.append(
                        SpanFeedLine(
                            markup=f"{event_prefix}{event_line.markup}",
                            plain=f"{event_prefix}{event_line.plain}",
                        )
                    )
        return lines


def _llm_verbose_parts(metrics: dict[str, Any]) -> list[str]:
    """Extra detail appended to an ``llm.generate`` line in verbose mode."""

    parts: list[str] = []
    inp = metrics.get("input_tokens")
    out = metrics.get("output_tokens")
    if isinstance(inp, int) and isinstance(out, int):
        parts.append(f"in {inp}/out {out}")
    cost = metrics.get("cost_usd")
    if isinstance(cost, (int, float)) and cost:
        parts.append(f"${cost:.4f}")
    context = metrics.get("context")
    if isinstance(context, dict):
        ratio = context.get("usage_ratio")
        conv = context.get("conversation_tokens")
        if isinstance(conv, int):
            ctx = f"ctx {conv} tok"
            if isinstance(ratio, (int, float)):
                ctx += f" ({ratio * 100:.0f}%)"
            parts.append(ctx)
    return parts


def _preorder_tree(spans: list[SpanRecord]) -> list[tuple[SpanRecord, int]]:
    by_id = {span.span_id: span for span in spans}
    children: dict[str, list[SpanRecord]] = {span.span_id: [] for span in spans}
    roots: list[SpanRecord] = []
    for span in spans:
        parent_id = span.parent_span_id
        if parent_id and parent_id in by_id:
            children[parent_id].append(span)
        else:
            roots.append(span)

    for child_list in children.values():
        child_list.sort(key=lambda row: (row.start_time, row.name))

    roots.sort(key=lambda row: (row.start_time, row.name))

    rows: list[tuple[SpanRecord, int]] = []

    def walk(node: SpanRecord, depth: int) -> None:
        rows.append((node, depth))
        for child in children.get(node.span_id, []):
            walk(child, depth + 1)

    for root in roots:
        walk(root, 0)
    return rows
