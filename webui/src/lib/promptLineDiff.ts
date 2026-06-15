/** Line-oriented diff helpers for adjacent llm.generate api_messages. */

export function messageTextContent(message: unknown): string {
  if (!message || typeof message !== "object") return "";
  const content = (message as { content?: unknown }).content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (!part || typeof part !== "object") return "";
        const row = part as { type?: string; text?: string };
        if (row.type === "text" && typeof row.text === "string") return row.text;
        return JSON.stringify(part);
      })
      .join("\n");
  }
  if (content == null) return "";
  return JSON.stringify(content);
}

export function diffTextLines(before: string, after: string): string[] {
  const left = before.split("\n");
  const right = after.split("\n");
  const maxLen = Math.max(left.length, right.length);
  const lines: string[] = [];
  for (let index = 0; index < maxLen; index += 1) {
    const a = left[index];
    const b = right[index];
    if (a === b) {
      if (a !== undefined) lines.push(`  ${a}`);
      continue;
    }
    if (index >= left.length) {
      lines.push(`+ ${b}`);
      continue;
    }
    if (index >= right.length) {
      lines.push(`- ${a}`);
      continue;
    }
    lines.push(`- ${a}`);
    lines.push(`+ ${b}`);
  }
  return lines;
}

export function diffApiMessageLines(before: unknown[], after: unknown[]): string[] {
  const maxLen = Math.max(before.length, after.length);
  const lines: string[] = [];
  for (let index = 0; index < maxLen; index += 1) {
    const left = before[index];
    const right = after[index];
    if (JSON.stringify(left) === JSON.stringify(right)) continue;
    lines.push(`--- api_messages[${index}] ---`);
    lines.push(...diffTextLines(messageTextContent(left), messageTextContent(right)));
  }
  return lines;
}
