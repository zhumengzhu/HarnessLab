import type { HealthResponse, ModelInfo, SessionSummary } from "./schemas";

export function resolveEffectiveModel(
  session: SessionSummary | undefined,
  health: HealthResponse | undefined,
  models: ModelInfo[]
): { modelId: string | null; backend: string | null; effort: string | null; label: string } {
  const globalCurrent = models.find((m) => m.current);
  const backend = session?.model_backend ?? health?.model ?? globalCurrent?.backend ?? null;
  const modelId =
    session?.model_id ??
    (session?.model_backend
      ? models.find((m) => m.backend === session.model_backend)?.id ?? null
      : health?.model_id ?? globalCurrent?.id ?? null);
  const effort =
    session?.model_effort ??
    (session?.model_backend ? null : globalCurrent?.current_effort ?? null);
  const matched = models.find((m) => m.id === modelId);
  const label = matched?.label ?? health?.model_label ?? health?.model ?? "–";
  return {
    modelId,
    backend,
    effort: effort ?? matched?.current_effort ?? null,
    label,
  };
}

export function modelsForSessionPicker(
  models: ModelInfo[],
  effectiveModelId: string | null,
  effectiveEffort: string | null,
  effectiveBackend: string | null
): ModelInfo[] {
  return models.map((m) => ({
    ...m,
    current:
      Boolean(effectiveModelId && m.id === effectiveModelId) &&
      (!effectiveBackend || m.backend === effectiveBackend),
    current_effort: m.id === effectiveModelId ? effectiveEffort : m.current_effort,
  }));
}
