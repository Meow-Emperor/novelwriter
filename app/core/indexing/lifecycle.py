# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import logging
from threading import Lock
from typing import Callable

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Novel

from .rebuild import build_window_index_artifacts, load_chapter_texts

WINDOW_INDEX_STATUS_MISSING = "missing"
WINDOW_INDEX_STATUS_STALE = "stale"
WINDOW_INDEX_STATUS_FRESH = "fresh"
WINDOW_INDEX_STATUS_FAILED = "failed"
KNOWN_WINDOW_INDEX_STATUSES = frozenset(
    {
        WINDOW_INDEX_STATUS_MISSING,
        WINDOW_INDEX_STATUS_STALE,
        WINDOW_INDEX_STATUS_FRESH,
        WINDOW_INDEX_STATUS_FAILED,
    }
)
WINDOW_INDEX_REBUILD_FAILED_MESSAGE = "窗口索引重建失败，请稍后重试"

logger = logging.getLogger(__name__)

_window_index_rebuild_locks_guard = Lock()
_window_index_rebuild_locks: dict[int, Lock] = {}


def normalize_window_index_status(raw_status: str | None, *, has_payload: bool) -> str:
    value = (raw_status or "").strip().lower()
    if value in KNOWN_WINDOW_INDEX_STATUSES:
        return value
    return WINDOW_INDEX_STATUS_FRESH if has_payload else WINDOW_INDEX_STATUS_MISSING


def resolve_window_index_target_revision(
    novel: Novel,
    *,
    has_source_text: bool,
) -> int:
    current_revision = max(
        int(getattr(novel, "window_index_revision", 0) or 0),
        int(getattr(novel, "window_index_built_revision", 0) or 0),
        0,
    )
    if has_source_text and current_revision <= 0:
        return 1
    return current_revision


def mark_window_index_inputs_changed(novel: Novel) -> int:
    new_revision = resolve_window_index_target_revision(
        novel,
        has_source_text=bool(getattr(novel, "window_index_revision", 0) or getattr(novel, "window_index_built_revision", 0)),
    ) + 1
    novel.window_index_revision = new_revision
    novel.window_index = None
    novel.window_index_error = None
    novel.window_index_status = (
        WINDOW_INDEX_STATUS_STALE
        if getattr(novel, "window_index_built_revision", None) is not None
        else WINDOW_INDEX_STATUS_MISSING
    )
    return new_revision


def mark_window_index_missing(novel: Novel, *, revision: int | None = None) -> int:
    target_revision = max(
        int(revision if revision is not None else getattr(novel, "window_index_revision", 0) or 0),
        0,
    )
    novel.window_index_revision = target_revision
    novel.window_index_status = WINDOW_INDEX_STATUS_MISSING
    novel.window_index = None
    novel.window_index_error = None
    return target_revision


def mark_window_index_build_succeeded(
    novel: Novel,
    *,
    index_payload: bytes,
    revision: int | None = None,
) -> int:
    target_revision = max(
        int(revision if revision is not None else getattr(novel, "window_index_revision", 0) or 0),
        1,
    )
    novel.window_index_revision = target_revision
    novel.window_index_built_revision = target_revision
    novel.window_index_status = WINDOW_INDEX_STATUS_FRESH
    novel.window_index = index_payload
    novel.window_index_error = None
    return target_revision


def mark_window_index_build_failed(
    novel: Novel,
    *,
    error: str,
    revision: int | None = None,
) -> int:
    target_revision = max(
        int(revision if revision is not None else getattr(novel, "window_index_revision", 0) or 0),
        1,
    )
    novel.window_index_revision = target_revision
    novel.window_index_status = WINDOW_INDEX_STATUS_FAILED
    novel.window_index = None
    novel.window_index_error = error
    return target_revision


def _get_window_index_rebuild_lock(novel_id: int) -> Lock:
    with _window_index_rebuild_locks_guard:
        lock = _window_index_rebuild_locks.get(novel_id)
        if lock is None:
            lock = Lock()
            _window_index_rebuild_locks[novel_id] = lock
        return lock


def _finalize_missing_revision(
    *,
    session_factory: Callable[[], Session],
    novel_id: int,
    target_revision: int,
) -> bool:
    db = session_factory()
    try:
        novel = db.query(Novel).filter(Novel.id == novel_id).first()
        if novel is None:
            return False
        current_revision = resolve_window_index_target_revision(novel, has_source_text=False)
        if current_revision > target_revision:
            return True
        mark_window_index_missing(novel, revision=target_revision)
        db.commit()
        return False
    finally:
        db.close()


def _finalize_failed_revision(
    *,
    session_factory: Callable[[], Session],
    novel_id: int,
    target_revision: int,
    error: str,
) -> bool:
    db = session_factory()
    try:
        novel = db.query(Novel).filter(Novel.id == novel_id).first()
        if novel is None:
            return False
        current_revision = int(getattr(novel, "window_index_revision", 0) or 0)
        if current_revision > target_revision:
            return True
        mark_window_index_build_failed(
            novel,
            error=error,
            revision=max(target_revision, current_revision, 1),
        )
        db.commit()
        return False
    finally:
        db.close()


def _finalize_success_revision(
    *,
    session_factory: Callable[[], Session],
    novel_id: int,
    target_revision: int,
    index_payload: bytes,
) -> bool:
    db = session_factory()
    try:
        novel = db.query(Novel).filter(Novel.id == novel_id).first()
        if novel is None:
            return False
        current_revision = int(getattr(novel, "window_index_revision", 0) or 0)
        if current_revision > target_revision:
            return True
        mark_window_index_build_succeeded(
            novel,
            index_payload=index_payload,
            revision=max(target_revision, current_revision, 1),
        )
        db.commit()
        return False
    finally:
        db.close()


def run_window_index_rebuild_for_latest_revision(
    novel_id: int,
    *,
    session_factory: Callable[[], Session],
    settings: Settings | None = None,
) -> None:
    rebuild_lock = _get_window_index_rebuild_lock(novel_id)
    if not rebuild_lock.acquire(blocking=False):
        return

    resolved_settings = settings or get_settings()
    try:
        while True:
            db = session_factory()
            try:
                novel = db.query(Novel).filter(Novel.id == novel_id).first()
                if novel is None:
                    return
                chapters = load_chapter_texts(db, novel_id)
                target_revision = resolve_window_index_target_revision(
                    novel,
                    has_source_text=bool(chapters),
                )
                novel_language = getattr(novel, "language", None)
            finally:
                db.close()

            if not chapters:
                if _finalize_missing_revision(
                    session_factory=session_factory,
                    novel_id=novel_id,
                    target_revision=target_revision,
                ):
                    continue
                return

            try:
                artifacts = build_window_index_artifacts(
                    chapters,
                    novel_language=novel_language,
                    settings=resolved_settings,
                    include_cooccurrence=False,
                )
            except Exception:
                logger.exception(
                    "window_index[%s]: rebuild failed for revision %s",
                    novel_id,
                    target_revision,
                )
                if _finalize_failed_revision(
                    session_factory=session_factory,
                    novel_id=novel_id,
                    target_revision=target_revision,
                    error=WINDOW_INDEX_REBUILD_FAILED_MESSAGE,
                ):
                    continue
                return

            if _finalize_success_revision(
                session_factory=session_factory,
                novel_id=novel_id,
                target_revision=target_revision,
                index_payload=artifacts.index.to_msgpack(),
            ):
                continue
            return
    finally:
        rebuild_lock.release()
