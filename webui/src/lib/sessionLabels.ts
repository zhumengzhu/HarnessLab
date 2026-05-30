import type { SessionSummary } from "./schemas";

const STATUS_LABELS: Record<string, string> = {
  done: "已完成",
  running: "进行中",
  waiting_user: "等待回复",
};

export function sessionStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

/** Display title for a session row (sidebar / picker). */
export function sessionLabel(session: SessionSummary): string {
  return session.title?.trim() || session.goal?.trim() || session.id.slice(0, 8);
}

/** Human-readable session list meta: status + turns + persisted message rows. */
export function sessionListMeta(session: SessionSummary): string {
  const parts = [sessionStatusLabel(session.status)];
  if (session.turn_count > 0) {
    parts.push(`${session.turn_count} 轮`);
  }
  parts.push(`${session.message_count} 条消息`);
  if (session.parent_session_id) {
    parts.unshift("子会话");
  }
  return parts.join(" · ");
}
