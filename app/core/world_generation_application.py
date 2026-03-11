# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Application orchestration for text-to-world generation."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ai_client import LLMUnavailableError, StructuredOutputParseError
from app.core.events import record_event
from app.core.world_crud import load_novel
from app.core.world_gen import generate_world_drafts
from app.core.world_use_case_errors import WorldUseCaseError, detail_error_from_http_exception
from app.core.auth import refund_quota, reserve_quota
from app.core.llm_semaphore import acquire_llm_slot, release_llm_slot
from app.models import User
from app.schemas import WorldGenerateResponse

logger = logging.getLogger(__name__)
_world_generate_locks: dict[int, asyncio.Lock] = {}
_world_generate_locks_guard = asyncio.Lock()


async def generate_world_from_text(
    novel_id: int,
    *,
    text: str,
    db: Session,
    current_user: User,
    llm_config: dict | None,
    request_id: str | None = None,
    generate_world_drafts_fn: Callable[..., Awaitable[WorldGenerateResponse]] | None = None,
    acquire_llm_slot_fn: Callable[[], Awaitable[None]] | None = None,
    release_llm_slot_fn: Callable[[], None] | None = None,
    reserve_quota_fn: Callable[[Session, int, int], None] | None = None,
    refund_quota_fn: Callable[[Session, int, int], None] | None = None,
    record_event_fn: Callable[..., None] | None = None,
) -> WorldGenerateResponse:
    generation_runner = generate_world_drafts_fn or generate_world_drafts
    acquire_slot = acquire_llm_slot_fn or acquire_llm_slot
    release_slot = release_llm_slot_fn or release_llm_slot
    reserve_quota_write = reserve_quota_fn or reserve_quota
    refund_quota_write = refund_quota_fn or refund_quota
    record_generate_event = record_event_fn or record_event

    lock = await _get_world_generate_lock(novel_id)
    async with lock:
        load_novel(novel_id, db)
        extra = {
            "request_id": request_id,
            "novel_id": novel_id,
            "user_id": current_user.id,
        }

        try:
            await acquire_slot()
        except HTTPException as exc:
            raise detail_error_from_http_exception(exc) from exc

        reserved = False
        try:
            try:
                reserve_quota_write(db, current_user.id, 1)
                reserved = True
                result = await generation_runner(
                    db=db,
                    novel_id=novel_id,
                    text=text,
                    llm_config=llm_config,
                    user_id=current_user.id,
                )
            except HTTPException as exc:
                if reserved:
                    refund_quota_write(db, current_user.id, 1)
                raise detail_error_from_http_exception(exc) from exc
            except StructuredOutputParseError as exc:
                if reserved:
                    refund_quota_write(db, current_user.id, 1)
                logger.warning("world.generate invalid LLM output", exc_info=True, extra=extra)
                raise WorldUseCaseError(
                    code="world_generate_llm_schema_invalid",
                    message="LLM schema invalid",
                    status_code=502,
                ) from exc
            except LLMUnavailableError as exc:
                if reserved:
                    refund_quota_write(db, current_user.id, 1)
                logger.warning("world.generate LLM unavailable", exc_info=True, extra=extra)
                raise WorldUseCaseError(
                    code="world_generate_llm_unavailable",
                    message="LLM unavailable",
                    status_code=503,
                ) from exc
            except IntegrityError as exc:
                if reserved:
                    refund_quota_write(db, current_user.id, 1)
                raise WorldUseCaseError(
                    code="world_generate_conflict",
                    message="World generation conflict",
                    status_code=409,
                ) from exc
            except Exception as exc:
                if reserved:
                    refund_quota_write(db, current_user.id, 1)
                logger.exception("world.generate failed", extra=extra)
                raise WorldUseCaseError(
                    code="world_generate_failed",
                    message="World generation failed",
                    status_code=500,
                ) from exc
        finally:
            release_slot()

        record_generate_event(db, current_user.id, "world_generate", novel_id=novel_id)
        return result


async def _get_world_generate_lock(novel_id: int) -> asyncio.Lock:
    async with _world_generate_locks_guard:
        lock = _world_generate_locks.get(novel_id)
        if lock is None:
            lock = asyncio.Lock()
            _world_generate_locks[novel_id] = lock
        return lock
