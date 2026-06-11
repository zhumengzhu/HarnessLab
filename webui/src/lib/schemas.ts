export type ComposerCommandItem = {
  name: string;
  usage: string;
  description: string;
  insert: string;
  kind?: string;
};

export type ComposerCommandsResponse = {
  commands: ComposerCommandItem[];
  skills: ComposerCommandItem[];
};

export type SkillRecord = {
  name: string;
  description: string;
  tags: string[];
  scope: string;
  path: string | null;
  catalog_id?: string | null;
};

export type SkillPreviewResponse = {
  markdown: string;
};

export type SkillsResponse = {
  skills: SkillRecord[];
};

export type HealthResponse = {
  ok: boolean;
  model: string;
  model_id?: string | null;
  model_label?: string | null;
  workspace: string;
  runtime_context_tokens?: number;
  version?: string;
  trace_path?: string | null;
  pricing_version?: string | null;
  pricing_fingerprint?: string | null;
};

export type SettingsResponse = {
  settings: Record<string, unknown>;
  config_source?: string | null;
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
  model_backend?: string | null;
  model_id?: string | null;
  model_effort?: string | null;
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

export type UsageTotals = {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  cost_display?: number | null;
  llm_calls: number;
  tool_calls: number;
  session_count: number;
  dimensions?: Record<string, number>;
};

export type UsageDailyBucket = {
  date: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  cost_display?: number | null;
  llm_calls: number;
  dimensions?: Record<string, number>;
};

export type UsageModelBucket = {
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  cost_display?: number | null;
  llm_calls: number;
  dimensions?: Record<string, number>;
};

export type UsageSessionRow = {
  session_id: string;
  title: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  cost_display?: number | null;
  llm_calls: number;
  tool_calls: number;
  last_activity_at: string | null;
  budget_status: string;
  dimensions?: Record<string, number>;
};

export type UsageResponse = {
  range: string;
  source: "trace" | "sessions" | "spans";
  display_currency?: string;
  currency_symbol?: string;
  totals: UsageTotals;
  daily: UsageDailyBucket[];
  by_model: UsageModelBucket[];
  sessions: UsageSessionRow[];
};

export type MessageItem = {
  id: string;
  role: string;
  content: string;
  created_at: string;
  reasoning_text?: string;
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

export type ContextSnapshot = {
  conversation_tokens?: number;
  message_count?: number;
  limit_tokens?: number;
  compaction_threshold_tokens?: number;
  usage_ratio?: number;
  prompt_tokens_estimate?: number;
  static_block_tokens?: number;
  dynamic_block_tokens?: number;
  prompt_block_names?: string[];
  context_breakdown_tokens?: Record<string, number>;
};

export type TurnPayload = {
  session: SessionSummary & { memory_notes?: string };
  reply: string;
  messages: MessageItem[];
  tool_cards: ToolCard[];
  context_snapshot?: ContextSnapshot | null;
};

export type ModelInfo = {
  id: string;
  provider: string;
  backend: string;
  label: string;
  context_window: number;
  context_label?: string;
  context_editable?: boolean;
  runtime_context_tokens?: number;
  reasoning_support: "native" | "proxy" | "none";
  thinking_schema: "none" | "budget" | "level" | "toggle";
  thinking_default: string;
  effort_levels: string[];
  configured: boolean;
  current: boolean;
  current_effort: string | null;
};

export type ModelsResponse = {
  models: ModelInfo[];
};

export type ContextResponse = {
  context: ContextSnapshot | null;
};

export type ModelSwitchRequest = {
  backend?: string;
  model_id?: string;
  effort?: string;
};

export type ForkResponse = {
  session: SessionSummary;
};

export type PatchSessionResponse = {
  session: SessionSummary;
};

export type CheckpointSummary = {
  id: string;
  session_id: string;
  tool_name: string;
  created_at: string;
};

export type CheckpointsResponse = {
  session_id: string;
  checkpoints: CheckpointSummary[];
};

export type CheckpointPreviewResponse = {
  session_id: string;
  checkpoint: {
    id: string;
    tool_name: string;
    tool_args: Record<string, unknown>;
    created_at: string;
  };
  changes: Array<{
    path: string;
    current: string | null;
    restore_to: string | null;
  }>;
};

export type SpanEventItem = {
  name: string;
  time: string;
  attributes?: Record<string, unknown>;
};

export type SpanLinkItem = {
  linked_trace_id: string;
  linked_span_id: string;
  attributes?: Record<string, unknown>;
};

export type SpanRecordItem = {
  resource?: Record<string, unknown>;
  trace_id: string;
  span_id: string;
  parent_span_id?: string | null;
  name: string;
  kind?: string;
  session_id: string;
  turn_index: number;
  start_time: string;
  end_time: string;
  duration_ms: number;
  status?: string;
  status_message?: string | null;
  attributes: Record<string, unknown>;
  events?: SpanEventItem[];
  metrics?: Record<string, unknown>;
  links?: SpanLinkItem[];
  /** SSE fan-in when span belongs to a child session. */
  child_session_id?: string;
};

export type SpanStartedPayload = {
  trace_id: string;
  span_id: string;
  parent_span_id?: string | null;
  name: string;
  kind?: string;
  session_id: string;
  turn_index?: number;
  attributes?: Record<string, unknown>;
  child_session_id?: string;
};

export type SpanEventPayload = {
  trace_id: string;
  span_id: string;
  name: string;
  attributes?: Record<string, unknown>;
};

export type SpanLinkPayload = {
  trace_id: string;
  span_id: string;
  linked_trace_id: string;
  linked_span_id: string;
  attributes?: Record<string, unknown>;
};

export type TraceResponse = {
  session_id: string;
  spans: SpanRecordItem[];
};

export type TraceJsonlResponse = {
  session_id: string;
  spans_path?: string | null;
  trace_path?: string | null;
  line_count: number;
  jsonl: string;
};

export type ArtifactResponse = {
  id: string;
  session_id: string;
  mime: string;
  size_bytes: number;
  sha256: string;
  encoding: "utf-8" | "base64";
  content: string;
};

export type ProposalSummary = {
  id: string;
  status: "open" | "accepted" | "rejected" | "superseded";
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
  status: "open" | "accepted" | "rejected" | "superseded";
  kind: string;
  cluster_signature: string;
  occurrences: number;
  generated_at: string;
  superseded_by?: string | null;
  related_files: string[];
  body_markdown: string;
};

export type ProposalDetailResponse = {
  proposal: ProposalDetail;
};

export type ProposalStatusUpdateRequest = {
  status: "open" | "accepted" | "rejected" | "superseded";
  decision_note?: string;
  superseded_by?: string;
  confirm_reviewed?: boolean;
  confirm_pytest_green?: boolean;
  confirm_eval_no_regression?: boolean;
};

export type ProposalGateRunRequest = {
  gate: "pytest" | "eval";
};

export type ProposalGateRunResult = {
  gate: "pytest" | "eval";
  ok: boolean;
  exit_code: number | null;
  elapsed_ms: number;
  command: string[];
  stdout: string;
  stderr: string;
  stdout_truncated: boolean;
  stderr_truncated: boolean;
  timed_out?: boolean;
};

export type ProposalGateRunResponse = {
  result: ProposalGateRunResult;
};
