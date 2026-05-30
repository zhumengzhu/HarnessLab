import { describe, expect, it } from "vitest";
import { modelsForSessionPicker, resolveEffectiveModel } from "./sessionModel";
import type { HealthResponse, ModelInfo, SessionSummary } from "./schemas";

const models: ModelInfo[] = [
  {
    id: "deepseek-v4-flash",
    provider: "deepseek",
    backend: "deepseek",
    label: "DeepSeek V4 Flash",
    context_window: 128000,
    reasoning_support: "native",
    thinking_schema: "toggle",
    thinking_default: "disabled",
    effort_levels: ["disabled", "high", "max"],
    configured: true,
    current: true,
    current_effort: "disabled",
  },
  {
    id: "deepseek-v4-pro",
    provider: "deepseek",
    backend: "deepseek",
    label: "DeepSeek V4 Pro",
    context_window: 128000,
    reasoning_support: "native",
    thinking_schema: "toggle",
    thinking_default: "disabled",
    effort_levels: ["disabled", "high", "max"],
    configured: true,
    current: false,
    current_effort: null,
  },
];

const health: HealthResponse = {
  ok: true,
  model: "deepseek",
  model_id: "deepseek-v4-flash",
  model_label: "DeepSeek V4 Flash",
  workspace: "/tmp",
};

describe("sessionModel", () => {
  it("uses session override when present", () => {
    const session: SessionSummary = {
      id: "ses_1",
      goal: "g",
      title: null,
      status: "running",
      turn_count: 0,
      step_count: 0,
      created_at: "2026-01-01T00:00:00Z",
      last_step_at: null,
      parent_session_id: null,
      message_count: 0,
      model_backend: "deepseek",
      model_id: "deepseek-v4-pro",
      model_effort: "max",
    };
    const effective = resolveEffectiveModel(session, health, models);
    expect(effective.modelId).toBe("deepseek-v4-pro");
    expect(effective.effort).toBe("max");
    const picker = modelsForSessionPicker(
      models,
      effective.modelId,
      effective.effort,
      effective.backend
    );
    expect(picker.find((m) => m.id === "deepseek-v4-pro")?.current).toBe(true);
    expect(picker.find((m) => m.id === "deepseek-v4-flash")?.current).toBe(false);
  });

  it("falls back to health when session has no override", () => {
    const effective = resolveEffectiveModel(undefined, health, models);
    expect(effective.modelId).toBe("deepseek-v4-flash");
  });
});
