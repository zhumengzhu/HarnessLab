export type ActivityDisplayMode = "compact" | "detailed";
export type ChatTextSize = "sm" | "md" | "lg";

const CHAT_TEXT_SIZES: ChatTextSize[] = ["sm", "md", "lg"];

export function stepChatTextSize(current: ChatTextSize, delta: -1 | 1): ChatTextSize {
  const index = CHAT_TEXT_SIZES.indexOf(current);
  const next = Math.min(CHAT_TEXT_SIZES.length - 1, Math.max(0, index + delta));
  return CHAT_TEXT_SIZES[next] ?? "md";
}
