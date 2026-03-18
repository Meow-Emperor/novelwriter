# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from sqlalchemy.orm import Session

from app.core.derived_assets import (
    DERIVED_ASSET_KIND_WINDOW_INDEX,
    DerivedAssetJobSnapshot,
    DerivedAssetPersistResult,
    enqueue_derived_asset_job,
    inspect_derived_asset_job,
    inspect_derived_asset_jobs,
    run_derived_asset_job_until_idle,
)
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

WINDOW_INDEX_JOB_RESULT_STATE_KEY = "asset_state"


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


@dataclass(slots=True)
class WindowIndexBuildOutput:
    asset_state: str
    index_payload: bytes | None = None


@dataclass(slots=True)
class WindowIndexLifecycleSnapshot:
    status: str
    revision: int
    built_revision: int | None
    error: str | None
    has_payload: bool
    job: DerivedAssetJobSnapshot | None = None


def inspect_window_index_lifecycle(
    novel: Novel,
    *,
    db: Session | None = None,
    has_payload_override: bool | None = None,
) -> WindowIndexLifecycleSnapshot:
    job_snapshot = None
    novel_id = getattr(novel, "id", None)
    if db is not None and isinstance(novel_id, int):
        job_snapshot = inspect_window_index_rebuild_job(db, novel_id=novel_id)
    return _build_window_index_lifecycle_snapshot(
        novel,
        job_snapshot=job_snapshot,
        has_payload_override=has_payload_override,
    )


def _build_window_index_lifecycle_snapshot(
    novel: Novel,
    *,
    job_snapshot: DerivedAssetJobSnapshot | None = None,
    has_payload_override: bool | None = None,
) -> WindowIndexLifecycleSnapshot:
    has_payload = (
        bool(has_payload_override)
        if has_payload_override is not None
        else bool(getattr(novel, "window_index", None))
    )
    built_revision = getattr(novel, "window_index_built_revision", None)
    normalized_status = normalize_window_index_status(
        getattr(novel, "window_index_status", None),
        has_payload=has_payload,
    )
    return WindowIndexLifecycleSnapshot(
        status=normalized_status,
        revision=int(getattr(novel, "window_index_revision", 0) or 0),
        built_revision=int(built_revision) if built_revision is not None else None,
        error=getattr(novel, "window_index_error", None),
        has_payload=has_payload,
        job=job_snapshot,
    )


def inspect_window_index_lifecycles(
    novels: Iterable[Novel],
    *,
    db: Session | None = None,
    has_payload_overrides: Mapping[int, bool] | None = None,
) -> dict[int, WindowIndexLifecycleSnapshot]:
    novel_list = list(novels)
    if not novel_list:
        return {}

    job_snapshots: dict[int, DerivedAssetJobSnapshot] = {}
    if db is not None:
        job_snapshots = inspect_window_index_rebuild_jobs(
            db,
            novel_ids=[
                novel_id
                for novel in novel_list
                if isinstance((novel_id := getattr(novel, "id", None)), int)
            ],
        )

    return {
        novel_id: _build_window_index_lifecycle_snapshot(
            novel,
            job_snapshot=job_snapshots.get(novel_id),
            has_payload_override=(
                bool(has_payload_overrides[novel_id])
                if has_payload_overrides is not None and novel_id in has_payload_overrides
                else None
            ),
        )
        for novel in novel_list
        if isinstance((novel_id := getattr(novel, "id", None)), int)
    }


class _WindowIndexJobAdapter:
    asset_kind = DERIVED_ASSET_KIND_WINDOW_INDEX

    def build(
        self,
        *,
        novel_id: int,
        target_revision: int,
        session_factory: Callable[[], Session],
        settings: Settings,
    ) -> WindowIndexBuildOutput:
        db = session_factory()
        try:
            novel = db.query(Novel).filter(Novel.id == novel_id).first()
            if novel is None:
                return WindowIndexBuildOutput(asset_state=WINDOW_INDEX_STATUS_MISSING)
            chapters = load_chapter_texts(db, novel_id)
            novel_language = getattr(novel, "language", None)
        finally:
            db.close()

        if not chapters:
            return WindowIndexBuildOutput(asset_state=WINDOW_INDEX_STATUS_MISSING)

        artifacts = build_window_index_artifacts(
            chapters,
            novel_language=novel_language,
            settings=settings,
            include_cooccurrence=False,
            # Background rebuilds run inside the live web app process.
            # Keep them on the pure-Python matcher path instead of the
            # native automaton path to avoid crashing the server.
            use_automaton=False,
        )
        return WindowIndexBuildOutput(
            asset_state=WINDOW_INDEX_STATUS_FRESH,
            index_payload=artifacts.index.to_msgpack(),
        )

    def persist_success(
        self,
        *,
        db: Session,
        job,
        target_revision: int,
        build_output: WindowIndexBuildOutput,
    ) -> DerivedAssetPersistResult:
        novel = db.query(Novel).filter(Novel.id == job.novel_id).first()
        if novel is None:
            return DerivedAssetPersistResult(superseded=True)

        current_revision = int(getattr(novel, "window_index_revision", 0) or 0)
        if current_revision > target_revision:
            return DerivedAssetPersistResult(
                superseded=True,
                next_target_revision=current_revision,
            )

        target = max(target_revision, current_revision, 1)
        if build_output.asset_state == WINDOW_INDEX_STATUS_MISSING:
            mark_window_index_missing(novel, revision=target_revision)
            return DerivedAssetPersistResult(
                completed_revision=target_revision,
                result={WINDOW_INDEX_JOB_RESULT_STATE_KEY: WINDOW_INDEX_STATUS_MISSING},
            )

        mark_window_index_build_succeeded(
            novel,
            index_payload=build_output.index_payload or b"",
            revision=target,
        )
        return DerivedAssetPersistResult(
            completed_revision=target,
            result={WINDOW_INDEX_JOB_RESULT_STATE_KEY: WINDOW_INDEX_STATUS_FRESH},
        )

    def persist_failure(
        self,
        *,
        db: Session,
        job,
        target_revision: int,
        error: str,
    ) -> bool:
        novel = db.query(Novel).filter(Novel.id == job.novel_id).first()
        if novel is None:
            return True

        current_revision = int(getattr(novel, "window_index_revision", 0) or 0)
        if current_revision > target_revision:
            job.target_revision = max(int(job.target_revision or 0), current_revision)
            return True

        mark_window_index_build_failed(
            novel,
            error=error,
            revision=max(target_revision, current_revision, 1),
        )
        return False

    def sanitize_error(self, exc: Exception) -> str:
        _ = exc
        return WINDOW_INDEX_REBUILD_FAILED_MESSAGE


WINDOW_INDEX_JOB_ADAPTER = _WindowIndexJobAdapter()


def enqueue_window_index_rebuild_job(
    db: Session,
    *,
    novel_id: int,
    target_revision: int,
    settings: Settings | None = None,
):
    return enqueue_derived_asset_job(
        db,
        novel_id=novel_id,
        asset_kind=DERIVED_ASSET_KIND_WINDOW_INDEX,
        target_revision=target_revision,
        settings=settings,
    )


def inspect_window_index_rebuild_job(
    db: Session,
    *,
    novel_id: int,
) -> DerivedAssetJobSnapshot | None:
    return inspect_derived_asset_job(
        db,
        novel_id=novel_id,
        asset_kind=DERIVED_ASSET_KIND_WINDOW_INDEX,
    )


def inspect_window_index_rebuild_jobs(
    db: Session,
    *,
    novel_ids: Iterable[int],
) -> dict[int, DerivedAssetJobSnapshot]:
    return inspect_derived_asset_jobs(
        db,
        novel_ids=novel_ids,
        asset_kind=DERIVED_ASSET_KIND_WINDOW_INDEX,
    )


def run_window_index_rebuild_for_latest_revision(
    novel_id: int,
    *,
    session_factory: Callable[[], Session],
    settings: Settings | None = None,
) -> None:
    resolved_settings = settings or get_settings()
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
        enqueue_window_index_rebuild_job(
            db,
            novel_id=novel_id,
            target_revision=target_revision,
            settings=resolved_settings,
        )
        db.commit()
    finally:
        db.close()

    run_derived_asset_job_until_idle(
        novel_id=novel_id,
        adapter=WINDOW_INDEX_JOB_ADAPTER,
        session_factory=session_factory,
        settings=resolved_settings,
    )
