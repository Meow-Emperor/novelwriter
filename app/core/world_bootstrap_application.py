# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Application orchestration for bootstrap trigger and status flows."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.core.auth import decrement_quota
from app.core.bootstrap import (
    BOOTSTRAP_MODE_INDEX_REFRESH,
    BOOTSTRAP_MODE_INITIAL,
    BOOTSTRAP_MODE_REEXTRACT,
    BootstrapRunSummary,
    find_legacy_manual_draft_ambiguity,
    is_running_status,
    is_stale_running_job,
    resolve_reextract_draft_policy,
    run_bootstrap_job,
)
from app.core.events import record_event
from app.core.world_crud import load_novel
from app.core.world_use_case_errors import WorldUseCaseError, detail_error_from_http_exception
from app.models import BootstrapJob, Chapter, User
from app.schemas import BootstrapDraftPolicy, BootstrapTriggerRequest

logger = logging.getLogger(__name__)
_bootstrap_trigger_locks: dict[int, asyncio.Lock] = {}
_bootstrap_trigger_locks_guard = asyncio.Lock()
_LEGACY_REPAIR_SCRIPT = "scripts/fix_legacy_bootstrap_origin.py"

def is_bootstrap_initialized(job: BootstrapJob | None) -> bool:
    if job is None:
        return False

    if bool(getattr(job, "initialized", False)):
        return True

    result = job.result or {}
    if bool(result.get("initialized", False)):
        return True

    if str(job.status) != "completed":
        return False

    if "index_refresh_only" in result:
        return not bool(result.get("index_refresh_only"))

    return True


async def trigger_bootstrap(
    novel_id: int,
    *,
    body: BootstrapTriggerRequest | None,
    db: Session,
    current_user: User,
    llm_config: dict | None,
    settings: Settings | None = None,
    launch_bootstrap_job_fn: Callable[..., None] | None = None,
) -> BootstrapJob:
    resolved_settings = settings or get_settings()
    launcher = launch_bootstrap_job_fn or launch_bootstrap_job
    lock = await _get_bootstrap_trigger_lock(novel_id)

    async with lock:
        load_novel(novel_id, db)
        try:
            decrement_quota(db, current_user, count=1)
        except HTTPException as exc:
            raise detail_error_from_http_exception(exc) from exc

        if not _has_non_empty_chapter_text(novel_id, db):
            raise WorldUseCaseError(
                code="bootstrap_no_text",
                message="Novel has no non-empty chapter text to bootstrap",
                status_code=400,
            )

        job = db.query(BootstrapJob).filter(BootstrapJob.novel_id == novel_id).first()
        if job and is_running_status(job.status):
            if is_stale_running_job(
                job,
                stale_after_seconds=resolved_settings.bootstrap_stale_job_timeout_seconds,
            ):
                logger.warning(
                    "Reclaiming stale bootstrap job before retrigger",
                    extra={"novel_id": novel_id, "job_id": job.id, "status": job.status},
                )
            else:
                raise WorldUseCaseError(
                    code="bootstrap_already_running",
                    message="Bootstrap already running for this novel",
                    status_code=409,
                )

        bootstrap_initialized = is_bootstrap_initialized(job)
        mode, draft_policy = _resolve_trigger_params(body, bootstrap_initialized=bootstrap_initialized)

        if (
            mode == BOOTSTRAP_MODE_REEXTRACT
            and draft_policy == BootstrapDraftPolicy.REPLACE_BOOTSTRAP_DRAFTS
        ):
            legacy = find_legacy_manual_draft_ambiguity(db, novel_id=novel_id)
            if legacy.has_any():
                raise WorldUseCaseError(
                    code="bootstrap_legacy_ambiguity_conflict",
                    message=(
                        "Legacy ambiguity detected for reextract replacement: "
                        f"{len(legacy.entity_ids)} draft entities and {len(legacy.relationship_ids)} "
                        "draft relationships still use origin=manual from pre-origin-tracking data. "
                        f"Run `python3 {_LEGACY_REPAIR_SCRIPT} --novel-id {novel_id} --dry-run`, "
                        "review the output, then rerun with `--apply` before retrying."
                    ),
                    status_code=409,
                )

        if mode == BOOTSTRAP_MODE_INITIAL and bootstrap_initialized:
            raise WorldUseCaseError(
                code="bootstrap_initial_mode_not_allowed",
                message="initial mode is only allowed before bootstrap initialization",
                status_code=409,
            )

        if not job:
            job = BootstrapJob(novel_id=novel_id)
            db.add(job)

        job.mode = mode
        job.draft_policy = draft_policy.value if draft_policy else None
        job.status = "pending"
        job.progress = {"step": 0, "detail": "queued"}
        job.result = {
            "entities_found": 0,
            "relationships_found": 0,
            "index_refresh_only": mode == BOOTSTRAP_MODE_INDEX_REFRESH,
        }
        job.error = None

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            existing_job = db.query(BootstrapJob).filter(BootstrapJob.novel_id == novel_id).first()
            if existing_job and is_running_status(existing_job.status):
                raise WorldUseCaseError(
                    code="bootstrap_already_running",
                    message="Bootstrap already running for this novel",
                    status_code=409,
                ) from exc
            raise WorldUseCaseError(
                code="bootstrap_trigger_conflict",
                message="Bootstrap trigger conflict, please retry",
                status_code=409,
            ) from exc

        db.refresh(job)

        launcher(
            db=db,
            job_id=job.id,
            user_id=current_user.id,
            llm_config=llm_config,
        )

        return job


def get_bootstrap_status(
    novel_id: int,
    *,
    db: Session,
    settings: Settings | None = None,
) -> BootstrapJob:
    load_novel(novel_id, db)
    job = db.query(BootstrapJob).filter(BootstrapJob.novel_id == novel_id).first()
    if not job:
        raise WorldUseCaseError(
            code="bootstrap_job_not_found",
            message="Bootstrap job not found",
            status_code=404,
        )

    resolved_settings = settings or get_settings()
    if is_stale_running_job(job, stale_after_seconds=resolved_settings.bootstrap_stale_job_timeout_seconds):
        job.status = "failed"
        job.error = "Bootstrap job stale after restart; please retry."
        db.commit()
        db.refresh(job)
    return job


def launch_bootstrap_job(
    *,
    db: Session,
    job_id: int,
    user_id: int | None,
    llm_config: dict | None,
    task_scheduler: Callable[[Awaitable[None]], object] = asyncio.create_task,
    background_job_runner: Callable[..., Awaitable[None]] | None = None,
) -> None:
    background_session_factory = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    runner = background_job_runner or run_bootstrap_background_job
    task_scheduler(
        runner(
            job_id,
            session_factory=background_session_factory,
            user_id=user_id,
            llm_config=llm_config,
        )
    )


async def run_bootstrap_background_job(
    job_id: int,
    *,
    session_factory: Callable[[], Session],
    user_id: int | None = None,
    llm_config: dict | None = None,
    bootstrap_runner: Callable[..., Awaitable[BootstrapRunSummary | None]] = run_bootstrap_job,
    record_event_fn: Callable[..., None] = record_event,
) -> None:
    summary = await bootstrap_runner(
        job_id,
        session_factory=session_factory,
        user_id=user_id,
        llm_config=llm_config,
    )
    if summary is None or user_id is None:
        return

    event_db = session_factory()
    try:
        record_event_fn(
            event_db,
            user_id,
            "bootstrap_run",
            novel_id=summary.novel_id,
            meta={
                "mode": summary.mode,
                "entities_found": summary.entities_found,
                "relationships_found": summary.relationships_found,
            },
        )
    finally:
        event_db.close()


async def _get_bootstrap_trigger_lock(novel_id: int) -> asyncio.Lock:
    async with _bootstrap_trigger_locks_guard:
        lock = _bootstrap_trigger_locks.get(novel_id)
        if lock is None:
            lock = asyncio.Lock()
            _bootstrap_trigger_locks[novel_id] = lock
        return lock


def _has_non_empty_chapter_text(novel_id: int, db: Session) -> bool:
    chapters = db.query(Chapter.content).filter(Chapter.novel_id == novel_id).all()
    return any((content or "").strip() for (content,) in chapters)


def _resolve_trigger_params(
    body: BootstrapTriggerRequest | None,
    *,
    bootstrap_initialized: bool,
) -> tuple[str, BootstrapDraftPolicy | None]:
    request = body or BootstrapTriggerRequest()
    mode_explicit = body is not None and "mode" in body.model_fields_set
    mode = request.mode.value
    if not mode_explicit:
        mode = BOOTSTRAP_MODE_INDEX_REFRESH if bootstrap_initialized else BOOTSTRAP_MODE_INITIAL

    if mode != BOOTSTRAP_MODE_REEXTRACT and request.draft_policy is not None:
        raise WorldUseCaseError(
            code="bootstrap_draft_policy_not_allowed",
            message="draft_policy is only supported for reextract mode",
            status_code=400,
        )

    if mode != BOOTSTRAP_MODE_REEXTRACT:
        return mode, None

    raw_policy = request.draft_policy.value if request.draft_policy else None
    policy = BootstrapDraftPolicy(resolve_reextract_draft_policy(raw_policy))
    if policy == BootstrapDraftPolicy.REPLACE_BOOTSTRAP_DRAFTS and not request.force:
        raise WorldUseCaseError(
            code="bootstrap_force_required",
            message="force=true is required for reextract with replace_bootstrap_drafts",
            status_code=400,
        )

    return mode, policy
