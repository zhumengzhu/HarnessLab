export type HealthResponse = {
  ok: boolean;
  model: string;
  workspace: string;
};

export type SettingsResponse = {
  settings: Record<string, unknown>;
};

export type SessionSummary = {
  id: string;
  goal: string;
  title: string | null;
  status: string;
  turn_count: number;
  step_count: number;
  created_at: string;
  last_step_at: string | null;
  parent_session_id: string | null;
  message_count: number;
  budget_usage?: {
    llm_calls_total: number;
    tool_calls_total: number;
    tokens_total: number;
    wall_time_ms_total: number;
    cost_usd_total: number;
    last_budget_status: "ok" | "soft_exceeded" | "hard_exceeded";
  };
};

export type SessionsResponse = {
  sessions: SessionSummary[];
};

export type MessageItem = {
  id: string;
  role: string;
  content: string;
  created_at: string;
};

export type SessionDetailResponse = {
  session: SessionSummary & { memory_notes?: string };
  messages: MessageItem[];
};

export type ToolCard = {
  tool: string;
  ok: boolean;
  error?: string | null;
  output_preview?: string;
  output_truncated?: boolean;
  duration_ms?: number | null;
};

export type TurnPayload = {
  session: SessionSummary & { memory_notes?: string };
  reply: string;
  messages: MessageItem[];
  tool_cards: ToolCard[];
};

export type ForkResponse = {
  session: SessionSummary;
};

export type TraceEventItem = {
  run_id: string;
  session_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type TraceResponse = {
  session_id: string;
  events: TraceEventItem[];
};

export type ProposalSummary = {
  id: string;
  status: string;
  kind: string;
  cluster_signature: string;
  occurrences: number;
  generated_at: string;
};

export type ProposalsResponse = {
  proposals: ProposalSummary[];
};

export type ProposalDetail = {
  id: string;
  status: string;
  kind: string;
  cluster_signature: string;
  occurrences: number;
  generated_at: string;
  related_files: string[];
  body_markdown: string;
};

export type ProposalDetailResponse = {
  proposal: ProposalDetail;
};
