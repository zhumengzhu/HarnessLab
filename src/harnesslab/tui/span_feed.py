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

    def _format_span(self, span: SpanRecord, attrs: dict[str, Any]) -> SpanFeedLine | None:
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
            preview = metrics.get("output_preview")
            preview_text = ""
            if isinstance(preview, str) and preview.strip():
                snippet = preview.replace("\n", " ").strip()[:80]
                preview_text = f" — {snippet}"
            return SpanFeedLine(
                markup=f"[magenta]tool[/magenta] {tool} · {status}{dur}{preview_text}",
                plain=f"tool {tool} · {status}{dur}{preview_text}",
            )

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
