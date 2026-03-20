# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Copilot runtime — scoped research workbench for world-model governance.

Core abstraction: target -> evidence -> claim -> optional delta.

Architecture invariants:
  1. Evidence comes from backend-known sources (chapters, world rows), never model invention.
  2. Suggestions are backend-compiled: model proposes claims, backend validates + assembles actions.
  3. Apply IS the approval boundary: copilot-applied rows become origin=manual, status=confirmed.
  4. Guardrails constrain the research protocol, not the novel's structure.
  5. Canonical names/labels stay in the novel's own language.
  6. Inquiry-only runs (answer + evidence, no suggestions) are a normal success outcome.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from app.core.ai_client import AIClient, ToolCallUnsupportedError
from app.core.auth import settle_quota_reservation
from app.core.copilot.apply import ApplyResult, apply_suggestions
from app.core.copilot.messages import CopilotTextKey, get_copilot_text
from app.language import normalize_copilot_interaction_locale
from app.core.copilot.prompting import (
    apply_quick_action_prompt,
    build_auto_preload as _build_auto_preload,
    build_copilot_system_prompt,
    build_tool_loop_system_prompt as _build_tool_loop_system_prompt,
    classify_turn_intent,
    should_preload_world_context as _should_preload_world_context,
)
from app.core.copilot.scope import (
    CopilotFocusVariant,
    CopilotRuntimeProfile,
    EvidenceItem,
    ScopeSnapshot,
    derive_focus_variant,
    derive_runtime_profile,
    gather_evidence,
    load_scope_snapshot,
)
from app.core.copilot.research_tools import (
    _TOOL_SCHEMAS,
    _deduplicate_packs,
    _find_from_chapters,
    _find_from_draft_auditors,
    _find_from_window_index,
    _find_from_world_rows,
    _tool_find,
    _tool_open,
    _tool_read,
    dispatch_tool as _dispatch_tool,
    tool_load_scope_snapshot as _tool_load_scope_snapshot,
)
from app.core.copilot.run_store import (
    persist_completed_run as _persist_completed_run,
    persist_preloaded_evidence as _persist_preloaded_evidence,
    persist_running_workspace as _persist_workspace,
    renew_run_lease as _renew_run_lease,
)
from app.core.copilot.suggestions import (
    compile_suggestions,
    dismiss_suggestions,
)
from app.core.copilot.tool_loop import (
    run_tool_loop as _run_tool_loop_impl,
    ToolLoopDeps,
)
from app.core.copilot.tracing import (
    build_tool_journal_entry as _build_tool_journal_entry,
)
from app.core.copilot.workspace import (
    EvidencePack,
    Workspace,
    build_follow_up_workspace_seed as _build_follow_up_workspace_seed,
    evidence_from_workspace as _evidence_from_workspace,
    make_pack_id as _make_pack_id,
)
from app.core.llm_semaphore import acquire_llm_slot, release_llm_slot
from app.models import (
    CopilotRun,
    CopilotSession,
    Novel,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ApplyResult",
    "CopilotError",
    "CopilotFocusVariant",
    "CopilotRuntimeProfile",
    "EvidencePack",
    "apply_suggestions",
    "derive_runtime_profile",
    "dismiss_suggestions",
    "_deduplicate_packs",
    "_find_from_chapters",
    "_find_from_draft_auditors",
    "_find_from_window_index",
    "_find_from_world_rows",
    "_make_pack_id",
    "_tool_find",
    "_tool_open",
    "_tool_read",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_ACTIVE_RUNS_PER_USER = 3
MAX_EVIDENCE_PACKS = 12
ACTIVE_RUN_STATUSES = frozenset({"queued", "running"})
# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CopilotError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class RunLeaseLostError(RuntimeError):
    """Raised when a worker no longer owns the run lease."""


def _resolve_run_interaction_locale(run: CopilotRun | None) -> str:
    if run is None:
        return "zh"
    session = getattr(run, "session", None)
    return normalize_copilot_interaction_locale(
        str(getattr(session, "interaction_locale", "zh") or "zh"),
    )


def _copilot_run_failed_message(interaction_locale: str) -> str:
    return get_copilot_text(
        CopilotTextKey.RUN_FAILED,
        locale=interaction_locale,
    )


def _copilot_run_interrupted_message(interaction_locale: str) -> str:
    return get_copilot_text(
        CopilotTextKey.RUN_INTERRUPTED,
        locale=interaction_locale,
    )


def _running_trace_summary(interaction_locale: str) -> str:
    return get_copilot_text(
        CopilotTextKey.RUN_RESEARCHING,
        locale=interaction_locale,
    )


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).astimezone(timezone.utc).replace(tzinfo=None)


def _normalize_utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _run_settings():
    from app.config import get_settings

    return get_settings()


def _load_session_by_signature(
    db: Session,
    *,
    novel_id: int,
    user_id: int,
    signature: str,
) -> CopilotSession | None:
    return (
        db.query(CopilotSession)
        .filter(
            CopilotSession.novel_id == novel_id,
            CopilotSession.user_id == user_id,
            CopilotSession.signature == signature,
        )
        .first()
    )


def _is_active_session_run_conflict(exc: IntegrityError) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return (
        "copilot_runs.copilot_session_id" in message
        or "uq_copilot_runs_active_session" in message
    )


def _is_session_signature_conflict(exc: IntegrityError) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return (
        "copilot_sessions.novel_id, copilot_sessions.user_id, copilot_sessions.signature" in message
        or "uq_copilot_sessions_lookup" in message
    )


def is_active_run_status(status: str | None) -> bool:
    return status in ACTIVE_RUN_STATUSES


def _resolve_queue_lease_expiry(now: datetime, queue_timeout_seconds: int) -> datetime | None:
    if queue_timeout_seconds <= 0:
        return None
    return now + timedelta(seconds=queue_timeout_seconds)


def _resolve_running_lease_expiry(now: datetime, lease_seconds: int) -> datetime | None:
    if lease_seconds <= 0:
        return None
    return now + timedelta(seconds=lease_seconds)


def _interrupt_run(
    run: CopilotRun,
    *,
    message: str,
    now: datetime,
) -> None:
    run.status = "interrupted"
    run.error = message
    run.lease_owner = None
    run.lease_expires_at = None
    run.finished_at = now


def _mark_run_error(
    run: CopilotRun,
    *,
    message: str,
    now: datetime,
) -> None:
    run.status = "error"
    run.error = message
    run.lease_owner = None
    run.lease_expires_at = None
    run.finished_at = now


def _settle_run_quota(
    db: Session,
    run: CopilotRun,
    *,
    charge_count: int = 0,
) -> None:
    reservation_id = getattr(run, "quota_reservation_id", None)
    if reservation_id is None:
        return
    settle_quota_reservation(db, reservation_id, charge_count=charge_count, commit=False)


def _settle_attached_run_quota(
    run: CopilotRun,
    *,
    charge_count: int = 0,
) -> None:
    db = object_session(run)
    if db is None:
        return
    _settle_run_quota(db, run, charge_count=charge_count)


def is_stale_run(
    run: CopilotRun,
    *,
    now: datetime | None = None,
    stale_after_seconds: int | None = None,
) -> bool:
    if not is_active_run_status(run.status):
        return False

    current_time = _normalize_utc_naive(now) or _utcnow_naive()
    lease_expires_at = _normalize_utc_naive(run.lease_expires_at)
    if lease_expires_at is not None:
        return lease_expires_at <= current_time

    settings = _run_settings()
    stale_timeout = (
        settings.copilot_run_stale_timeout_seconds
        if stale_after_seconds is None
        else stale_after_seconds
    )
    if stale_timeout <= 0:
        return False

    updated_at = _normalize_utc_naive(run.updated_at) or _normalize_utc_naive(run.created_at)
    if updated_at is None:
        return False
    return updated_at <= (current_time - timedelta(seconds=stale_timeout))


def reclaim_stale_runs(
    db: Session,
    *,
    run_ids: list[str] | None = None,
    user_id: int | None = None,
    copilot_session_id: int | None = None,
    message: str | None = None,
) -> list[str]:
    """Interrupt stale queued/running runs and return reclaimed run_ids."""
    query = db.query(CopilotRun).filter(CopilotRun.status.in_(tuple(ACTIVE_RUN_STATUSES)))
    if run_ids:
        query = query.filter(CopilotRun.run_id.in_(run_ids))
    if user_id is not None:
        query = query.filter(CopilotRun.user_id == user_id)
    if copilot_session_id is not None:
        query = query.filter(CopilotRun.copilot_session_id == copilot_session_id)

    now = _utcnow_naive()
    reclaimed: list[str] = []
    for run in query.all():
        if not is_stale_run(run, now=now):
            continue
        logger.warning(
            "Reclaiming stale copilot run",
            extra={"run_id": run.run_id, "status": run.status, "user_id": run.user_id},
        )
        _interrupt_run(
            run,
            message=message or _copilot_run_interrupted_message(_resolve_run_interaction_locale(run)),
            now=now,
        )
        _settle_run_quota(db, run)
        reclaimed.append(run.run_id)

    if reclaimed:
        db.commit()

    return reclaimed


def _claim_run_for_execution(
    db: Session,
    *,
    run_id: str,
    worker_id: str,
) -> CopilotRun | None:
    """Claim a queued run for one worker and move it to running."""
    run = db.query(CopilotRun).filter(CopilotRun.run_id == run_id).first()
    if run is None:
        return None
    if run.status != "queued":
        return None
    if is_stale_run(run):
        _interrupt_run(
            run,
            message=_copilot_run_interrupted_message(_resolve_run_interaction_locale(run)),
            now=_utcnow_naive(),
        )
        _settle_run_quota(db, run)
        db.commit()
        return None

    settings = _run_settings()
    now = _utcnow_naive()
    claimed = (
        db.query(CopilotRun)
        .filter(CopilotRun.run_id == run_id, CopilotRun.status == "queued")
        .update(
            {
                CopilotRun.status: "running",
                CopilotRun.error: None,
                CopilotRun.started_at: run.started_at or now,
                CopilotRun.finished_at: None,
                CopilotRun.lease_owner: worker_id,
                CopilotRun.lease_expires_at: _resolve_running_lease_expiry(now, settings.copilot_run_lease_seconds),
                CopilotRun.trace_json: [{
                    "step_id": "session_start",
                    "kind": "tool_mode",
                    "status": "running",
                    "summary": _running_trace_summary(_resolve_run_interaction_locale(run)),
                }],
                CopilotRun.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    if claimed != 1:
        db.rollback()
        return None
    db.commit()
    run = db.query(CopilotRun).filter(CopilotRun.run_id == run_id).first()
    if run is None:
        return None
    db.refresh(run)
    return run


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

_ATLAS_STAGE_TABS = frozenset({"entities", "relationships", "systems", "review"})


def canonicalize_session_context(context: dict | None) -> dict[str, Any] | None:
    """Return the canonical stored UI context for a copilot session/run.

    Atlas continuity is tab-based. Legacy plural atlas stages are tolerated as
    aliases, then collapsed into ``tab`` so the stored contract stays
    surface-appropriate and frontend route label drift does not leak into
    durable runtime state.
    """
    if not context:
        return None

    normalized = {
        key: deepcopy(value)
        for key, value in context.items()
        if value is not None
    }
    if not normalized:
        return None

    raw_stage = normalized.get("stage")
    raw_tab = normalized.get("tab")
    if raw_tab is None and raw_stage in _ATLAS_STAGE_TABS:
        normalized["tab"] = raw_stage

    if normalized.get("surface") == "atlas" or raw_stage in _ATLAS_STAGE_TABS:
        normalized.pop("stage", None)

    return normalized or None


def normalize_session_identity_context(
    mode: str,
    scope: str,
    context: dict | None,
) -> dict[str, Any] | None:
    """Return the normalized session-identity context.

    Surface/stage are UI-only continuity hints and must not split the durable
    copilot session. Keep only the context fields that materially change the
    research workbench identity.
    """
    context = canonicalize_session_context(context) or {}

    if scope == "whole_book":
        return None

    if scope == "current_entity":
        entity_id = context.get("entity_id")
        if entity_id is None:
            return None
        return {"entity_id": entity_id}

    normalized: dict[str, Any] = {}
    tab = context.get("tab")
    if tab is not None:
        normalized["tab"] = tab
    entity_id = context.get("entity_id")
    if entity_id is not None:
        normalized["entity_id"] = entity_id

    return normalized or None


def build_session_signature(
    mode: str,
    scope: str,
    context: dict | None,
    interaction_locale: str,
) -> str:
    """Deterministic signature for session dedup."""
    normalized_context = normalize_session_identity_context(mode, scope, context)
    normalized_interaction_locale = normalize_copilot_interaction_locale(interaction_locale)
    payload = json.dumps(
        {
            "mode": mode,
            "scope": scope,
            "entity_id": (normalized_context or {}).get("entity_id"),
            "tab": (normalized_context or {}).get("tab"),
            "locale": normalized_interaction_locale,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def open_or_reuse_session(
    db: Session,
    novel_id: int,
    user_id: int,
    mode: str,
    scope: str,
    context: dict | None,
    interaction_locale: str,
    display_title: str,
) -> tuple[CopilotSession, bool]:
    """Return (session, created).  Reuses existing unexpired session if signature matches."""
    context = canonicalize_session_context(context)
    normalized_interaction_locale = normalize_copilot_interaction_locale(interaction_locale)
    sig = build_session_signature(mode, scope, context, normalized_interaction_locale)

    existing = _load_session_by_signature(
        db,
        novel_id=novel_id,
        user_id=user_id,
        signature=sig,
    )

    if existing is not None:
        existing.last_active_at = func.now()
        existing.context_json = context
        existing.interaction_locale = normalized_interaction_locale
        if display_title:
            existing.display_title = display_title
        db.commit()
        db.refresh(existing)
        return existing, False

    session = CopilotSession(
        session_id=str(uuid.uuid4()),
        novel_id=novel_id,
        user_id=user_id,
        mode=mode,
        scope=scope,
        context_json=context,
        interaction_locale=normalized_interaction_locale,
        signature=sig,
        display_title=display_title or "",
    )
    db.add(session)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if not _is_session_signature_conflict(exc):
            raise CopilotError(
                code="copilot_session_conflict",
                message="Copilot session creation conflict, please retry",
                status_code=409,
            ) from exc

        existing = _load_session_by_signature(
            db,
            novel_id=novel_id,
            user_id=user_id,
            signature=sig,
        )
        if existing is None:
            raise CopilotError(
                code="copilot_session_conflict",
                message="Copilot session creation conflict, please retry",
                status_code=409,
            ) from exc
        existing.last_active_at = func.now()
        existing.context_json = context
        if display_title:
            existing.display_title = display_title
        db.commit()
        db.refresh(existing)
        return existing, False
    db.refresh(session)
    return session, True


def load_session(db: Session, novel_id: int, user_id: int, session_id: str) -> CopilotSession:
    """Load session with strict novel + user scoping."""
    session = (
        db.query(CopilotSession)
        .filter(
            CopilotSession.session_id == session_id,
            CopilotSession.novel_id == novel_id,
            CopilotSession.user_id == user_id,
        )
        .first()
    )
    if session is None:
        raise CopilotError(code="session_not_found", message="Copilot session not found", status_code=404)
    return session


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------

def _count_active_runs(db: Session, user_id: int) -> int:
    return (
        db.query(CopilotRun)
        .filter(CopilotRun.user_id == user_id, CopilotRun.status.in_(tuple(ACTIVE_RUN_STATUSES)))
        .count()
    )


def _count_active_runs_in_session(db: Session, copilot_session_id: int) -> int:
    return (
        db.query(CopilotRun)
        .filter(CopilotRun.copilot_session_id == copilot_session_id, CopilotRun.status.in_(tuple(ACTIVE_RUN_STATUSES)))
        .count()
    )


def create_run(
    db: Session,
    session: CopilotSession,
    user_id: int,
    prompt: str,
    *,
    quick_action_id: str | None = None,
    resume_run_id: str | None = None,
    quota_reservation_id: int | None = None,
) -> CopilotRun:
    """Create a new copilot run, enforcing admission control."""
    settings = _run_settings()
    reclaim_stale_runs(db)
    run_context = canonicalize_session_context(session.context_json)

    if _count_active_runs_in_session(db, session.id) >= settings.copilot_max_runs_per_session:
        raise CopilotError(code="session_run_active", message="Session already has an active run", status_code=409)

    copilot_user_limit = settings.copilot_max_runs_per_user
    if _count_active_runs(db, user_id) >= copilot_user_limit:
        raise CopilotError(code="too_many_active_runs", message=f"Too many active copilot runs (max {copilot_user_limit})", status_code=429)

    global_limit = settings.copilot_max_runs_global
    global_active = (
        db.query(CopilotRun)
        .filter(CopilotRun.status.in_(tuple(ACTIVE_RUN_STATUSES)))
        .count()
    )
    if global_active >= global_limit:
        raise CopilotError(code="too_many_global_runs", message=f"Server busy — too many copilot runs (max {global_limit})", status_code=503)

    inherited_workspace = None
    if resume_run_id:
        resume_run = (
            db.query(CopilotRun)
            .filter(
                CopilotRun.copilot_session_id == session.id,
                CopilotRun.user_id == user_id,
                CopilotRun.run_id == resume_run_id,
            )
            .first()
        )
        if resume_run is None:
            raise CopilotError(
                code="resume_run_not_found",
                message="Interrupted run to resume was not found",
                status_code=404,
            )
        if resume_run.status != "interrupted":
            raise CopilotError(
                code="resume_run_not_interrupted",
                message="Only interrupted runs can be resumed",
                status_code=409,
            )
        if (resume_run.prompt or "").strip() != prompt.strip():
            raise CopilotError(
                code="resume_prompt_mismatch",
                message="Resume prompt must match the interrupted run prompt",
                status_code=409,
            )
        if not resume_run.workspace_json or not resume_run.workspace_json.get("messages"):
            raise CopilotError(
                code="resume_run_not_resumable",
                message="Interrupted run has no resumable workspace",
                status_code=409,
            )
        inherited_workspace = resume_run.workspace_json

    now = _utcnow_naive()
    run = CopilotRun(
        run_id=str(uuid.uuid4()),
        copilot_session_id=session.id,
        novel_id=session.novel_id,
        user_id=user_id,
        quota_reservation_id=quota_reservation_id,
        quick_action_id=quick_action_id,
        status="queued",
        prompt=prompt,
        context_json=run_context,
        trace_json=[],
        evidence_json=[],
        suggestions_json=[],
        workspace_json=inherited_workspace,
        lease_owner=None,
        lease_expires_at=_resolve_queue_lease_expiry(now, settings.copilot_run_queue_timeout_seconds),
        started_at=None,
        finished_at=None,
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if (
            _is_active_session_run_conflict(exc)
            or _count_active_runs_in_session(db, session.id) >= settings.copilot_max_runs_per_session
        ):
            raise CopilotError(
                code="session_run_active",
                message="Session already has an active run",
                status_code=409,
            ) from exc
        raise CopilotError(
            code="copilot_run_conflict",
            message="Copilot run creation conflict, please retry",
            status_code=409,
        ) from exc
    db.refresh(run)
    return run


def load_run(db: Session, novel_id: int, user_id: int, session_id: str, run_id: str) -> CopilotRun:
    """Load run with strict novel + user + session scoping."""
    run = (
        db.query(CopilotRun)
        .join(CopilotSession, CopilotRun.copilot_session_id == CopilotSession.id)
        .filter(
            CopilotSession.session_id == session_id,
            CopilotSession.novel_id == novel_id,
            CopilotSession.user_id == user_id,
            CopilotRun.run_id == run_id,
        )
        .first()
    )
    if run is None:
        raise CopilotError(code="run_not_found", message="Copilot run not found", status_code=404)
    return run


def load_latest_run(db: Session, copilot_session_id: int) -> CopilotRun:
    """Load the most recent run for a session (any status)."""
    run = (
        db.query(CopilotRun)
        .filter(CopilotRun.copilot_session_id == copilot_session_id)
        .order_by(CopilotRun.created_at.desc(), CopilotRun.id.desc())
        .first()
    )
    if run is None:
        raise CopilotError(code="run_not_found", message="No runs in this session", status_code=404)
    return run


def list_session_runs(db: Session, copilot_session_id: int) -> list[CopilotRun]:
    """List session runs oldest-first for conversation/thread recovery."""
    return (
        db.query(CopilotRun)
        .filter(CopilotRun.copilot_session_id == copilot_session_id)
        .order_by(CopilotRun.created_at.asc(), CopilotRun.id.asc())
        .all()
    )


def _build_follow_up_conversation_messages(prior_runs: list[CopilotRun]) -> list[dict[str, str]]:
    """Convert prior completed runs into reusable user/assistant turns."""
    messages: list[dict[str, str]] = []
    for prior_run in prior_runs:
        if prior_run.status != "completed":
            continue
        prompt = (prior_run.prompt or "").strip()
        if prompt:
            messages.append({"role": "user", "content": prompt})
        answer = (prior_run.answer or "").strip()
        if answer:
            messages.append({"role": "assistant", "content": answer})
    return messages

# ---------------------------------------------------------------------------
# Scenario derivation (clean separation from mode/scope)
# ---------------------------------------------------------------------------

def derive_scenario(mode: str, scope: str, context: dict | None) -> str:
    """Derive the research scenario from mode/scope/context.

    Backward-compatible detailed workbench lens. The runtime isolation itself
    is now driven by the coarser 3-profile model returned by
    ``derive_runtime_profile``.
    """
    focus_variant = derive_focus_variant(mode, scope, context)
    if focus_variant == "draft":
        return "draft_cleanup"
    if focus_variant == "whole_book":
        return "whole_book"
    if focus_variant == "relationship":
        return "relationships"
    return "current_entity"

# ---------------------------------------------------------------------------
# Run execution (three-state degradation)
# ---------------------------------------------------------------------------

async def execute_copilot_run(
    run_id: str,
    novel_id: int,
    user_id: int,
    llm_config: dict[str, Any] | None,
) -> None:
    """Execute a copilot run in the background.

    Session lifecycle:
    - One main DB session for run state transitions (load, mark running, store results).
    - Separate short-lived sessions only for tool dispatch inside the loop.
    - The main session never crosses an ``await`` boundary holding uncommitted state.

    Degradation: tool-loop → one-shot-with-evidence (if tools unsupported).
    """
    from app.database import SessionLocal

    worker_id = uuid.uuid4().hex
    db = SessionLocal()
    try:
        run = _claim_run_for_execution(db, run_id=run_id, worker_id=worker_id)
        if not run:
            logger.info("Copilot run %s was not claimable for execution", run_id)
            return

        session = run.session
        if not session:
            _fail_run(db, run, "session_not_found", "Session not found", worker_id=worker_id)
            return

        novel = db.get(Novel, novel_id)
        if not novel:
            _fail_run(db, run, "novel_not_found", "Novel not found", worker_id=worker_id)
            return

        # --- load scope + evidence (sync, safe on same session) ---
        run_context = canonicalize_session_context(run.context_json) or canonicalize_session_context(session.context_json)
        snapshot = load_scope_snapshot(db, novel, session.mode, session.scope, run_context)
        scenario = derive_scenario(session.mode, session.scope, run_context)
        raw_prompt = run.prompt
        effective_prompt = apply_quick_action_prompt(
            raw_prompt,
            run.quick_action_id,
            session.interaction_locale,
        )
        turn_intent = classify_turn_intent(raw_prompt)
        evidence = (
            gather_evidence(
                db,
                novel,
                snapshot,
                run_context,
                interaction_locale=session.interaction_locale,
            )
            if _should_preload_world_context(turn_intent)
            else []
        )

        _persist_preloaded_evidence(db, run, evidence)

        # Capture session data we need across await — after this point we don't
        # touch the ORM session objects across awaits.
        session_data = {
            "mode": session.mode, "scope": session.scope,
            "context_json": run_context, "interaction_locale": session.interaction_locale,
            "display_title": session.display_title,
        }
        prompt = effective_prompt

        # Capture inherited workspace before crossing await boundary.
        inherited_workspace = run.workspace_json
        prior_completed_runs = []
        follow_up_messages: list[dict[str, str]] = []
        follow_up_workspace_seed: dict[str, Any] | None = None
        if inherited_workspace is None:
            prior_completed_runs = (
                db.query(CopilotRun)
                .filter(
                    CopilotRun.copilot_session_id == session.id,
                    CopilotRun.id != run.id,
                    CopilotRun.status == "completed",
                )
                .order_by(CopilotRun.created_at.asc(), CopilotRun.id.asc())
                .all()
            )
            follow_up_messages = _build_follow_up_conversation_messages(prior_completed_runs)
            if prior_completed_runs:
                follow_up_workspace_seed = _build_follow_up_workspace_seed(
                    prior_completed_runs[-1].workspace_json,
                )

        def db_factory() -> Session:
            return SessionLocal()

        # --- LLM phase (async) ---
        parsed: dict[str, Any] | None = None
        final_evidence: list[EvidenceItem] = evidence
        workspace: Workspace | None = None
        execution_mode = "tool_loop"
        degraded_reason: str | None = None

        try:
            parsed, final_evidence, workspace = await _run_tool_loop(
                db_factory, novel_id, session_data, prompt, llm_config, user_id,
                snapshot, scenario, evidence, turn_intent, run_id=run_id,
                worker_id=worker_id,
                inherited_workspace=inherited_workspace,
                prior_messages=follow_up_messages,
                workspace_seed=follow_up_workspace_seed,
            )
        except ToolCallUnsupportedError:
            logger.info("Tool calls unsupported, degrading to one-shot")
            execution_mode = "one_shot_unsupported"
            degraded_reason = "tools_not_supported"
            parsed, final_evidence = await _run_one_shot(
                snapshot, evidence, scenario, session_data, turn_intent, prompt, llm_config, user_id,
                run_id=run_id, worker_id=worker_id, db_factory=db_factory,
            )
        except RunLeaseLostError:
            logger.info("Copilot run %s lost lease during tool execution", run_id)
            return
        except Exception as tool_loop_exc:
            # Tool loop failed (LLM error, timeout, etc.) — try one-shot as fallback.
            # If one-shot also fails, re-raise the original error.
            logger.warning("Tool loop failed (%s), attempting one-shot fallback", type(tool_loop_exc).__name__)
            try:
                execution_mode = "one_shot_fallback"
                degraded_reason = type(tool_loop_exc).__name__
                parsed, final_evidence = await _run_one_shot(
                    snapshot, evidence, scenario, session_data, turn_intent, prompt, llm_config, user_id,
                    run_id=run_id, worker_id=worker_id, db_factory=db_factory,
                )
            except RunLeaseLostError:
                logger.info("Copilot run %s lost lease during fallback execution", run_id)
                return
            except Exception:
                raise tool_loop_exc from None

        if parsed is None:
            parsed = {"answer": "", "suggestions": []}

        # --- compile against fresh snapshot (sync) ---
        db_compile = db_factory()
        try:
            fresh_novel = db_compile.get(Novel, novel_id)
            fresh_snapshot = load_scope_snapshot(
                db_compile, fresh_novel or novel,
                session_data["mode"], session_data["scope"], session_data["context_json"],
            )
            compiled = compile_suggestions(
                parsed.get("suggestions", []) if _should_preload_world_context(turn_intent) else [],
                final_evidence, fresh_snapshot,
                session_data["mode"], scenario,
                interaction_locale=session_data["interaction_locale"],
            )
        finally:
            db_compile.close()

        if not _persist_completed_run(
            db_factory,
            run_id=run_id,
            worker_id=worker_id,
            answer=parsed.get("answer", ""),
            evidence=final_evidence,
            compiled_suggestions=compiled,
            workspace=workspace,
            execution_mode=execution_mode,
            degraded_reason=degraded_reason,
        ):
            logger.warning("Skipping result persistence for run %s after lease loss", run_id)

    except Exception:
        logger.exception("Copilot run %s failed", run_id)
        try:
            err_db = SessionLocal()
            try:
                err_run = err_db.query(CopilotRun).filter(CopilotRun.run_id == run_id).first()
                if err_run:
                    _fail_run(
                        err_db,
                        err_run,
                        "run_execution_error",
                        _copilot_run_failed_message(_resolve_run_interaction_locale(err_run)),
                        worker_id=worker_id,
                    )
            finally:
                err_db.close()
        except Exception:
            logger.exception("Failed to mark run %s as errored", run_id)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tool loop
# ---------------------------------------------------------------------------

async def _run_tool_loop(
    db_factory: Callable[[], Session],
    novel_id: int,
    session_data: dict[str, Any],
    prompt: str,
    llm_config: dict[str, Any] | None,
    user_id: int,
    snapshot: ScopeSnapshot,
    scenario: str,
    evidence: list[EvidenceItem],
    turn_intent: str,
    run_id: str = "",
    worker_id: str = "",
    inherited_workspace: dict[str, Any] | None = None,
    prior_messages: list[dict[str, str]] | None = None,
    workspace_seed: dict[str, Any] | None = None,
):
    deps = ToolLoopDeps(
        tool_schemas=_TOOL_SCHEMAS,
        acquire_llm_slot=acquire_llm_slot,
        release_llm_slot=release_llm_slot,
        build_system_prompt=_build_tool_loop_system_prompt,
        build_auto_preload=_build_auto_preload,
        should_preload_world_context=_should_preload_world_context,
        load_scope_snapshot=load_scope_snapshot,
        dispatch_tool=_dispatch_tool,
        tool_load_scope_snapshot=_tool_load_scope_snapshot,
        persist_workspace=_persist_workspace,
        renew_run_lease=_renew_run_lease,
        extract_llm_kwargs=_extract_llm_kwargs,
        parse_llm_response=_parse_llm_response,
        evidence_from_workspace=_evidence_from_workspace,
        lease_lost_error_factory=RunLeaseLostError,
    )
    return await _run_tool_loop_impl(
        deps=deps,
        db_factory=db_factory,
        novel_id=novel_id,
        session_data=session_data,
        prompt=prompt,
        llm_config=llm_config,
        user_id=user_id,
        snapshot=snapshot,
        scenario=scenario,
        evidence=evidence,
        turn_intent=turn_intent,
        run_id=run_id,
        worker_id=worker_id,
        inherited_workspace=inherited_workspace,
        prior_messages=prior_messages,
        workspace_seed=workspace_seed,
        build_tool_journal_entry=_build_tool_journal_entry,
    )


# ---------------------------------------------------------------------------
# Degraded mode: one-shot with pre-gathered evidence (no tool calls)
# ---------------------------------------------------------------------------

async def _run_one_shot(
    snapshot: ScopeSnapshot,
    evidence: list[EvidenceItem],
    scenario: str,
    session_data: dict[str, Any],
    turn_intent: str,
    prompt: str,
    llm_config: dict[str, Any] | None,
    user_id: int,
    *,
    run_id: str = "",
    worker_id: str = "",
    db_factory: Callable[[], Session] | None = None,
) -> tuple[dict[str, Any], list[EvidenceItem]]:
    """Single LLM call with all evidence pre-loaded in the prompt."""
    system_prompt = build_copilot_system_prompt(
        snapshot, evidence, scenario, session_data["interaction_locale"], session_data, turn_intent,
    )

    if run_id and worker_id and db_factory and not _renew_run_lease(db_factory, run_id=run_id, worker_id=worker_id):
        raise RunLeaseLostError(run_id)
    await acquire_llm_slot()
    try:
        response_text = await _call_copilot_llm(system_prompt, prompt, llm_config, user_id)
    finally:
        release_llm_slot()
    if run_id and worker_id and db_factory and not _renew_run_lease(db_factory, run_id=run_id, worker_id=worker_id):
        raise RunLeaseLostError(run_id)

    parsed = _parse_llm_response(response_text)
    return parsed, evidence

# Stale run detection
# ---------------------------------------------------------------------------

def check_stale_run(run: CopilotRun) -> bool:
    """Check if an active run is stale and mark it interrupted. Returns True if stale."""
    if not is_stale_run(run):
        return False
    _interrupt_run(
        run,
        message=_copilot_run_interrupted_message(_resolve_run_interaction_locale(run)),
        now=_utcnow_naive(),
    )
    _settle_attached_run_quota(run)
    return True


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _extract_llm_kwargs(llm_config: dict[str, Any] | None) -> dict[str, Any]:
    """Extract LLM kwargs from config dict."""
    kwargs: dict[str, Any] = {}
    if llm_config:
        kwargs["base_url"] = llm_config.get("base_url")
        kwargs["api_key"] = llm_config.get("api_key")
        kwargs["model"] = llm_config.get("model")
        kwargs["billing_source_hint"] = llm_config.get("billing_source_hint", "selfhost")
    return kwargs


def _fail_run(
    db: Session,
    run: CopilotRun,
    code: str,
    message: str,
    *,
    worker_id: str | None = None,
) -> None:
    if worker_id is not None and run.lease_owner != worker_id:
        logger.warning("Skipping fail_run for %s after lease loss", run.run_id)
        return
    _mark_run_error(run, message=message, now=_utcnow_naive())
    _settle_run_quota(db, run)
    db.commit()


async def _call_copilot_llm(system_prompt: str, user_prompt: str, llm_config: dict[str, Any] | None, user_id: int) -> str:
    client = AIClient()
    kwargs: dict[str, Any] = {}
    if llm_config:
        kwargs["base_url"] = llm_config.get("base_url")
        kwargs["api_key"] = llm_config.get("api_key")
        kwargs["model"] = llm_config.get("model")
        kwargs["billing_source_hint"] = llm_config.get("billing_source_hint", "selfhost")

    return await client.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        max_tokens=4000,
        temperature=0.4,
        role="default",
        user_id=user_id,
        **kwargs,
    )


def _parse_llm_response(text: str) -> dict[str, Any]:
    """Parse the LLM's final response into structured output.

    Handles common LLM formatting quirks:
    1. Pure JSON
    2. JSON wrapped in ```json ... ``` code blocks (possibly with text before/after)
    3. Raw JSON object embedded in natural language text
    4. Fallback: treat entire text as the answer (no suggestions)
    """
    import re

    stripped = text.strip()

    # 1. Try direct JSON parse
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 2. Extract JSON from ```json ... ``` or ``` ... ``` code block
    #    The block can appear anywhere in the response.
    code_block_match = re.search(r"```(?:json)?\s*\n(\{.*?\})\s*\n```", stripped, re.DOTALL)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Find the outermost { ... } that parses as valid JSON.
    #    Scan for opening brace, try to parse from there.
    first_brace = stripped.find("{")
    if first_brace >= 0:
        # Find the matching close brace from the end
        last_brace = stripped.rfind("}")
        if last_brace > first_brace:
            candidate = stripped[first_brace:last_brace + 1]
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict) and "answer" in parsed:
                    return parsed
            except json.JSONDecodeError:
                pass

    # 4. Fallback: entire text becomes the answer, no suggestions
    logger.warning("Failed to parse copilot LLM response as JSON, using text as answer")
    return {"answer": text, "cited_evidence_indices": [], "suggestions": []}
