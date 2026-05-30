"""Per-session model override helpers for the Web UI runtime."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from harnesslab.core.models import Session
from harnesslab.providers.deepseek_config import apply_deepseek_ui_effort

_PROVIDER_TO_BACKEND: dict[str, str] = {
    "deepseek": "deepseek",
    "anthropic": "anthropic",
    "openai": "openai",
    "google": "gemini",
    "gemini": "gemini",
}


def resolve_target_backend(
    *,
    backend: str | None,
    model_id: str | None,
) -> str:
    """Resolve a normalized backend id from explicit backend and/or catalog model_id."""

    from harnesslab.providers.catalog import ModelCatalog  # noqa: PLC0415
    from harnesslab.providers.registry import normalize_backend  # noqa: PLC0415

    if backend:
        return normalize_backend(backend)
    if model_id:
        try:
            entry = ModelCatalog().get(model_id)
        except KeyError as exc:
            raise ValueError(f"unknown model: {model_id}") from exc
        return _PROVIDER_TO_BACKEND.get(entry.provider, entry.provider)
    raise ValueError("either 'backend' or 'model_id' must be provided")


def config_changes_for_model_selection(
    norm: str,
    *,
    model_id: str | None,
    effort: str | None,
) -> dict[str, Any]:
    """Return ``OperatorConfig`` field overrides for a backend/model/effort choice."""

    changes: dict[str, Any] = {"model_backend": norm}
    if norm == "deepseek":
        if model_id:
            changes["deepseek_model_name"] = model_id
        if effort:
            thinking, reasoning = apply_deepseek_ui_effort(effort)
            changes["deepseek_thinking"] = thinking
            changes["deepseek_reasoning_effort"] = reasoning
    elif norm == "anthropic":
        if model_id:
            changes["anthropic_model_name"] = model_id
        if effort:
            changes["anthropic_thinking_effort"] = effort
            changes["anthropic_thinking"] = "enabled"
    elif norm == "openai":
        if model_id:
            changes["openai_model_name"] = model_id
        if effort:
            changes["openai_reasoning_effort"] = effort
    elif norm == "gemini":
        if model_id:
            changes["gemini_model_name"] = model_id
        if effort:
            changes["gemini_thinking_level"] = effort
    return changes


def effective_operator_config_for_session(
    base_config: Any,
    session: Session,
) -> Any:
    """Overlay session model override onto operator config without persisting."""

    if session.model_backend is None or base_config is None:
        return base_config
    changes = config_changes_for_model_selection(
        session.model_backend,
        model_id=session.model_id,
        effort=session.model_effort,
    )
    return replace(base_config, **changes)


def apply_session_model_patch(session: Session, body: dict[str, Any]) -> None:
    """Apply model override fields from a PATCH body onto ``session``."""

    if "model_backend" in body and body["model_backend"] is None:
        session.model_backend = None
        session.model_id = None
        session.model_effort = None
        return

    backend_raw = body.get("model_backend")
    backend = str(backend_raw).strip() if backend_raw is not None else None
    if backend == "":
        backend = None

    model_id_raw = body.get("model_id")
    model_id = str(model_id_raw).strip() if model_id_raw is not None else None
    if model_id == "":
        model_id = None

    effort_raw = body.get("effort", body.get("model_effort"))
    effort = str(effort_raw).strip() if effort_raw is not None else None
    if effort == "":
        effort = None

    has_model_keys = any(
        key in body for key in ("model_backend", "model_id", "effort", "model_effort")
    )
    if not has_model_keys:
        return

    if backend is None and model_id is None and effort is None:
        session.model_backend = None
        session.model_id = None
        session.model_effort = None
        return

    if backend is None and model_id is None and session.model_backend is None:
        raise ValueError("model_backend or model_id is required")

    norm = resolve_target_backend(
        backend=backend or session.model_backend,
        model_id=model_id,
    )
    if model_id:
        from harnesslab.providers.catalog import ModelCatalog  # noqa: PLC0415

        ModelCatalog().get(model_id)

    session.model_backend = norm
    if "model_id" in body:
        session.model_id = model_id
    elif model_id is not None:
        session.model_id = model_id
    if "effort" in body or "model_effort" in body:
        session.model_effort = effort
    elif effort is not None:
        session.model_effort = effort
