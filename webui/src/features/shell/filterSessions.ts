import type { SessionSummary } from "../../lib/schemas";
import { sessionLabel, sessionStatusLabel } from "../../lib/sessionLabels";

export type SessionStatusFilter = "all" | "running" | "done" | "waiting_user" | "child";

export type SessionFilterOptions = {
  query?: string;
  status?: SessionStatusFilter;
  /** Keep this session visible even when filters would hide it. */
  pinSessionId?: string | null;
};

function matchesQuery(session: SessionSummary, rawQuery: string): boolean {
  const query = rawQuery.trim().toLowerCase();
  if (!query) {
    return true;
  }
  const haystack = [
    session.id,
    session.title ?? "",
    session.goal,
    sessionLabel(session),
    sessionStatusLabel(session.status),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function matchesStatus(session: SessionSummary, status: SessionStatusFilter): boolean {
  if (status === "all") {
    return true;
  }
  if (status === "child") {
    return session.parent_session_id !== null;
  }
  return session.status === status;
}

export function filterSessions(
  sessions: SessionSummary[],
  options: SessionFilterOptions = {}
): SessionSummary[] {
  const { query = "", status = "all", pinSessionId = null } = options;
  const filtered = sessions.filter(
    (session) => matchesQuery(session, query) && matchesStatus(session, status)
  );

  if (!pinSessionId || filtered.some((session) => session.id === pinSessionId)) {
    return filtered;
  }

  const pinned = sessions.find((session) => session.id === pinSessionId);
  return pinned ? [pinned, ...filtered] : filtered;
}
