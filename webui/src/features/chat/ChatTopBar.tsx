import type { SessionSummary } from "../../lib/schemas";
import { SessionPicker } from "../sessions/SessionPicker";

type ChatTopBarProps = {
  sessions: SessionSummary[];
  selectedSessionId: string | null;
  sending: boolean;
  sessionsLoading: boolean;
  sessionsError: string | null;
  sessionActionError: string | null;
  onSelectSession: (id: string | null) => void;
  onForkCurrentSession: () => void;
};

export function ChatTopBar(props: ChatTopBarProps) {
  return (
    <div className="chat-top-bar">
      <SessionPicker
        sessions={props.sessions}
        selectedSessionId={props.selectedSessionId}
        sending={props.sending}
        loading={props.sessionsLoading}
        error={props.sessionsError}
        sessionActionError={props.sessionActionError}
        onSelectSession={props.onSelectSession}
        onForkCurrentSession={props.onForkCurrentSession}
      />
    </div>
  );
}
