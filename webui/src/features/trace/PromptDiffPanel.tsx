import { useMemo, useState } from "react";
import type { SpanRecordItem } from "../../lib/schemas";
import { collectLlmPromptSnapshots } from "../../lib/traceMetrics";
import { diffApiMessageLines } from "../../lib/promptLineDiff";
import { useI18n } from "../../lib/i18n";

type PromptBlock = { name: string; content: string };

function blockMap(blocks: unknown[]): Map<string, string> {
  const map = new Map<string, string>();
  for (const raw of blocks) {
    if (!raw || typeof raw !== "object") continue;
    const block = raw as PromptBlock;
    if (typeof block.name === "string" && typeof block.content === "string") {
      map.set(block.name, block.content);
    }
  }
  return map;
}

function diffBlocks(before: Map<string, string>, after: Map<string, string>): string[] {
  const names = new Set([...before.keys(), ...after.keys()]);
  const lines: string[] = [];
  for (const name of [...names].sort()) {
    const a = before.get(name) ?? "";
    const b = after.get(name) ?? "";
    if (a === b) continue;
    if (!a) {
      lines.push(`+ block ${name} (${b.length} chars)`);
      continue;
    }
    if (!b) {
      lines.push(`- block ${name} (${a.length} chars)`);
      continue;
    }
    lines.push(`~ block ${name}: ${a.length} → ${b.length} chars`);
  }
  return lines;
}

function summarizeMessage(message: unknown): string {
  if (!message || typeof message !== "object") return "?";
  const row = message as { role?: string; content?: unknown };
  const role = typeof row.role === "string" ? row.role : "?";
  const content = row.content;
  if (typeof content === "string") return `${role} (${content.length} chars)`;
  if (Array.isArray(content)) return `${role} (${content.length} parts)`;
  return role;
}

function diffApiMessages(before: unknown[], after: unknown[]): string[] {
  const maxLen = Math.max(before.length, after.length);
  const lines: string[] = [];
  for (let index = 0; index < maxLen; index += 1) {
    const left = before[index];
    const right = after[index];
    if (JSON.stringify(left) === JSON.stringify(right)) continue;
    if (index >= before.length) {
      lines.push(`+ api_messages[${index}]: ${summarizeMessage(right)}`);
    } else if (index >= after.length) {
      lines.push(`- api_messages[${index}]: ${summarizeMessage(left)}`);
    } else {
      lines.push(
        `~ api_messages[${index}]: ${summarizeMessage(left)} → ${summarizeMessage(right)}`
      );
    }
  }
  return lines;
}

type PromptDiffPanelProps = {
  spans: SpanRecordItem[];
};

export function PromptDiffPanel({ spans }: PromptDiffPanelProps) {
  const { t } = useI18n();
  const snapshots = useMemo(() => collectLlmPromptSnapshots(spans), [spans]);
  const [leftIdx, setLeftIdx] = useState(Math.max(0, snapshots.length - 2));
  const [rightIdx, setRightIdx] = useState(Math.max(0, snapshots.length - 1));

  if (snapshots.length < 2) return null;

  const left = snapshots[leftIdx];
  const right = snapshots[rightIdx];
  const lines = diffBlocks(blockMap(left.promptBlocks), blockMap(right.promptBlocks));
  const messageLines = diffApiMessages(left.apiMessages, right.apiMessages);
  const messageDetailLines = diffApiMessageLines(left.apiMessages, right.apiMessages);
  const messageDelta = right.apiMessages.length - left.apiMessages.length;

  return (
    <details className="trace-prompt-diff">
      <summary>{t("trace.promptDiffTitle")}</summary>
      <div className="trace-prompt-diff-controls">
        <label>
          {t("trace.promptDiffLeft")}
          <select value={leftIdx} onChange={(e) => setLeftIdx(Number(e.target.value))}>
            {snapshots.map((row, index) => (
              <option key={row.spanId} value={index}>
                turn {row.turnIndex} · {row.spanId.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("trace.promptDiffRight")}
          <select value={rightIdx} onChange={(e) => setRightIdx(Number(e.target.value))}>
            {snapshots.map((row, index) => (
              <option key={row.spanId} value={index}>
                turn {row.turnIndex} · {row.spanId.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <ul className="trace-prompt-diff-list">
        {messageDelta !== 0 ? (
          <li>
            api_messages count: {left.apiMessages.length} → {right.apiMessages.length}
          </li>
        ) : null}
        {messageLines.map((line) => (
          <li key={line}>{line}</li>
        ))}
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
        {!messageLines.length && !lines.length && messageDelta === 0 ? (
          <li>{t("trace.promptDiffEmpty")}</li>
        ) : null}
      </ul>
      {messageDetailLines.length ? (
        <details className="trace-prompt-diff-detail">
          <summary>{t("trace.promptDiffLineDetail")}</summary>
          <pre>{messageDetailLines.join("\n")}</pre>
        </details>
      ) : null}
    </details>
  );
}
