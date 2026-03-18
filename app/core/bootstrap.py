# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Sequence

from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.ai_client import AIClient, StructuredOutputParseError, get_client
from app.core.indexing.lifecycle import (
    mark_window_index_build_failed,
    mark_window_index_build_succeeded,
    resolve_window_index_target_revision,
)
from app.core.indexing.rebuild import build_window_index_artifacts, load_chapter_texts
from app.core.llm_semaphore import acquire_llm_slot_blocking, release_llm_slot
from app.core.text import PromptKey, get_prompt
from app.core.world.write import (
    build_relationship_signature,
    relationship_signature_from_row,
)
from app.database import SessionLocal
from app.language import resolve_prompt_locale
from app.language_policy import get_language_policy
from app.models import BootstrapJob, Novel, WorldEntity, WorldRelationship

logger = logging.getLogger(__name__)

DEFAULT_MAX_CANDIDATES = 500
DEFAULT_LLM_TEMPERATURE = 0.3
DEFAULT_STALE_JOB_TIMEOUT_SECONDS = 900
BOOTSTRAP_PARSE_ERROR_MESSAGE = "AI 输出解析失败，请重试"
BOOTSTRAP_PARSE_ERROR_KEY = "bootstrap.error.parse_failed"
BOOTSTRAP_GENERIC_ERROR_MESSAGE = "引导扫描失败，请稍后重试"
BOOTSTRAP_GENERIC_ERROR_KEY = "bootstrap.error.generic"
BOOTSTRAP_MODE_INITIAL = "initial"
BOOTSTRAP_MODE_INDEX_REFRESH = "index_refresh"
BOOTSTRAP_MODE_REEXTRACT = "reextract"
BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS = "replace_bootstrap_drafts"
BOOTSTRAP_DRAFT_POLICY_MERGE = "merge"
LEGACY_ORIGIN_TRACKING_CUTOFF = datetime(2026, 2, 18, tzinfo=timezone.utc)

BOOTSTRAP_STATUS_SEQUENCE = (
    "pending",
    "tokenizing",
    "extracting",
    "windowing",
    "refining",
    "completed",
)
RUNNING_BOOTSTRAP_STATUSES = frozenset(BOOTSTRAP_STATUS_SEQUENCE[:-1])

_ALLOWED_TRANSITIONS = {
    "pending": {"tokenizing", "failed"},
    "tokenizing": {"extracting", "failed"},
    "extracting": {"windowing", "failed"},
    "windowing": {"refining", "failed"},
    "refining": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
}

_KNOWN_BOOTSTRAP_MODES = frozenset(
    {
        BOOTSTRAP_MODE_INITIAL,
        BOOTSTRAP_MODE_INDEX_REFRESH,
        BOOTSTRAP_MODE_REEXTRACT,
    }
)
_KNOWN_REEXTRACT_DRAFT_POLICIES = frozenset(
    {
        BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS,
        BOOTSTRAP_DRAFT_POLICY_MERGE,
    }
)


@dataclass(slots=True)
class LegacyDraftAmbiguity:
    entity_ids: list[int]
    relationship_ids: list[int]

    def has_any(self) -> bool:
        return bool(self.entity_ids or self.relationship_ids)


@dataclass(slots=True)
class BootstrapRunSummary:
    novel_id: int
    mode: str
    entities_found: int
    relationships_found: int


class RefinedEntity(BaseModel):
    name: str = Field(min_length=1)
    entity_type: str = "other"
    aliases: list[str] = Field(default_factory=list)


class RefinedRelationship(BaseModel):
    source_name: str = Field(min_length=1)
    target_name: str = Field(min_length=1)
    label: str = Field(min_length=1)


class BootstrapRefinementResult(BaseModel):
    entities: list[RefinedEntity] = Field(default_factory=list)
    relationships: list[RefinedRelationship] = Field(default_factory=list)


def is_running_status(status: str | None) -> bool:
    return status in RUNNING_BOOTSTRAP_STATUSES


def resolve_bootstrap_mode(raw_mode: str | None) -> str:
    mode = (raw_mode or BOOTSTRAP_MODE_INDEX_REFRESH).strip()
    if mode in _KNOWN_BOOTSTRAP_MODES:
        return mode
    return BOOTSTRAP_MODE_INDEX_REFRESH


def resolve_reextract_draft_policy(raw_policy: str | None) -> str:
    policy = (raw_policy or BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS).strip()
    if policy in _KNOWN_REEXTRACT_DRAFT_POLICIES:
        return policy
    return BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS


def is_stale_running_job(
    job: BootstrapJob,
    *,
    stale_after_seconds: int = DEFAULT_STALE_JOB_TIMEOUT_SECONDS,
    now: datetime | None = None,
) -> bool:
    if stale_after_seconds <= 0:
        return False
    if not is_running_status(job.status):
        return False

    updated_at = job.updated_at or job.created_at
    if updated_at is None:
        return False

    if updated_at.tzinfo is not None:
        updated_at = updated_at.astimezone(timezone.utc).replace(tzinfo=None)

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is not None:
        current_time = current_time.astimezone(timezone.utc).replace(tzinfo=None)

    return updated_at <= (current_time - timedelta(seconds=stale_after_seconds))


def transition_bootstrap_job(
    job: BootstrapJob,
    new_status: str,
    *,
    detail: str | None = None,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    current = str(job.status)
    allowed = _ALLOWED_TRANSITIONS.get(current)
    if allowed is None:
        raise ValueError(f"Unknown bootstrap status: {current}")
    if new_status not in allowed:
        raise ValueError(f"Invalid bootstrap transition: {current} -> {new_status}")

    current_progress = job.progress or {}
    if new_status in BOOTSTRAP_STATUS_SEQUENCE:
        step = BOOTSTRAP_STATUS_SEQUENCE.index(new_status)
    else:
        step = int(current_progress.get("step", 0))

    job.status = new_status
    job.progress = {"step": step, "detail": detail or new_status}

    if new_status == "completed":
        job.result = result or {
            "entities_found": 0,
            "relationships_found": 0,
            "index_refresh_only": False,
        }
        job.error = None
    elif new_status == "failed":
        job.error = error or "Bootstrap failed"


def _build_refinement_prompt(
    importance: dict[str, int],
    cooccurrence_pairs: Sequence[tuple[str, str, int]],
    *,
    max_candidates: int,
    prompt_locale: str | None = None,
) -> str:
    sorted_candidates = sorted(
        importance.items(), key=lambda item: (-item[1], item[0])
    )[:max_candidates]
    sorted_pairs = list(cooccurrence_pairs[: max_candidates * 2])

    candidate_lines = (
        "\n".join([f"- {name}: {count}" for name, count in sorted_candidates])
        or "- (none)"
    )
    pair_lines = (
        "\n".join(
            [f"- {left} -- {right}: {count}" for left, right, count in sorted_pairs]
        )
        or "- (none)"
    )

    locale = prompt_locale or "zh"
    return get_prompt(PromptKey.BOOTSTRAP_REFINEMENT, locale=locale).format(
        candidate_lines=candidate_lines,
        pair_lines=pair_lines,
    )


async def refine_candidates_with_llm(
    importance: dict[str, int],
    cooccurrence_pairs: Sequence[tuple[str, str, int]],
    *,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    temperature: float = DEFAULT_LLM_TEMPERATURE,
    client: AIClient | None = None,
    llm_config: dict | None = None,
    user_id: int | None = None,
    novel_language: str | None = None,
) -> BootstrapRefinementResult:
    if not importance:
        return BootstrapRefinementResult()

    prompt_locale = resolve_prompt_locale(novel_language=novel_language)
    prompt = _build_refinement_prompt(
        importance,
        cooccurrence_pairs,
        max_candidates=max_candidates,
        prompt_locale=prompt_locale,
    )
    llm_kwargs = llm_config or {}
    ai = client or get_client()
    return await ai.generate_structured(
        prompt=prompt,
        response_model=BootstrapRefinementResult,
        system_prompt="You are a precise information extraction assistant.",
        temperature=temperature,
        max_tokens=8000,
        role="editor",
        user_id=user_id,
        **llm_kwargs,
    )


def _normalize_aliases(raw_aliases: Sequence[str], canonical_name: str) -> list[str]:
    canonical_key = get_language_policy(
        sample_text=canonical_name
    ).normalize_for_matching(canonical_name.strip())
    seen = {canonical_key}
    aliases: list[str] = []
    for raw_alias in raw_aliases:
        alias = raw_alias.strip()
        if not alias:
            continue
        key = get_language_policy(sample_text=alias).normalize_for_matching(alias)
        if key in seen:
            continue
        seen.add(key)
        aliases.append(alias)
    return aliases


def _is_refinement_parse_error(exc: Exception) -> bool:
    return isinstance(exc, StructuredOutputParseError)


def _sanitize_bootstrap_error(exc: Exception) -> tuple[str, str]:
    """Return (user_message, message_key) for a bootstrap failure."""
    if _is_refinement_parse_error(exc):
        return BOOTSTRAP_PARSE_ERROR_MESSAGE, BOOTSTRAP_PARSE_ERROR_KEY
    return BOOTSTRAP_GENERIC_ERROR_MESSAGE, BOOTSTRAP_GENERIC_ERROR_KEY


def _normalize_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _is_legacy_manual_draft_row(
    *,
    created_at: datetime | None,
    updated_at: datetime | None,
    cutoff: datetime,
) -> bool:
    created = _normalize_timestamp(created_at)
    if created is None:
        return False

    normalized_cutoff = _normalize_timestamp(cutoff)
    if normalized_cutoff is None:
        return False

    if created >= normalized_cutoff:
        return False

    updated = _normalize_timestamp(updated_at)
    if updated is None:
        return True
    return updated <= normalized_cutoff


def find_legacy_manual_draft_ambiguity(
    db: Session,
    *,
    novel_id: int,
    cutoff: datetime = LEGACY_ORIGIN_TRACKING_CUTOFF,
) -> LegacyDraftAmbiguity:
    entity_ids = [
        row.id
        for row in db.query(
            WorldEntity.id,
            WorldEntity.created_at,
            WorldEntity.updated_at,
        )
        .filter(
            WorldEntity.novel_id == novel_id,
            WorldEntity.status == "draft",
            WorldEntity.origin == "manual",
        )
        .all()
        if _is_legacy_manual_draft_row(
            created_at=row.created_at,
            updated_at=row.updated_at,
            cutoff=cutoff,
        )
    ]

    relationship_ids = [
        row.id
        for row in db.query(
            WorldRelationship.id,
            WorldRelationship.created_at,
            WorldRelationship.updated_at,
        )
        .filter(
            WorldRelationship.novel_id == novel_id,
            WorldRelationship.status == "draft",
            WorldRelationship.origin == "manual",
        )
        .all()
        if _is_legacy_manual_draft_row(
            created_at=row.created_at,
            updated_at=row.updated_at,
            cutoff=cutoff,
        )
    ]

    return LegacyDraftAmbiguity(
        entity_ids=entity_ids,
        relationship_ids=relationship_ids,
    )


def _delete_bootstrap_origin_drafts(db: Session, *, novel_id: int) -> None:
    bootstrap_draft_entity_ids = [
        entity_id
        for (entity_id,) in db.query(WorldEntity.id)
        .filter(
            WorldEntity.novel_id == novel_id,
            WorldEntity.status == "draft",
            WorldEntity.origin == "bootstrap",
        )
        .all()
    ]

    db.query(WorldRelationship).filter(
        WorldRelationship.novel_id == novel_id,
        WorldRelationship.status == "draft",
        WorldRelationship.origin == "bootstrap",
    ).delete(synchronize_session=False)

    if not bootstrap_draft_entity_ids:
        return

    referenced_rows = (
        db.query(
            WorldRelationship.source_id,
            WorldRelationship.target_id,
        )
        .filter(
            WorldRelationship.novel_id == novel_id,
            or_(
                WorldRelationship.source_id.in_(bootstrap_draft_entity_ids),
                WorldRelationship.target_id.in_(bootstrap_draft_entity_ids),
            ),
        )
        .all()
    )
    referenced_entity_ids = {
        entity_id
        for row in referenced_rows
        for entity_id in row
        if entity_id in bootstrap_draft_entity_ids
    }
    deletable_entity_ids = [
        entity_id
        for entity_id in bootstrap_draft_entity_ids
        if entity_id not in referenced_entity_ids
    ]
    if deletable_entity_ids:
        db.query(WorldEntity).filter(
            WorldEntity.id.in_(deletable_entity_ids),
        ).delete(synchronize_session=False)


def persist_bootstrap_output(
    db: Session,
    *,
    novel_id: int,
    refinement: BootstrapRefinementResult,
    mode: str,
    draft_policy: str | None,
) -> tuple[int, int]:
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if novel is None:
        raise ValueError(f"Novel not found: {novel_id}")

    if mode == BOOTSTRAP_MODE_INDEX_REFRESH:
        db.flush()
        return 0, 0

    if (
        mode == BOOTSTRAP_MODE_REEXTRACT
        and draft_policy == BOOTSTRAP_DRAFT_POLICY_REPLACE_BOOTSTRAP_DRAFTS
    ):
        _delete_bootstrap_origin_drafts(db, novel_id=novel_id)

    existing_entities = {
        entity.name: entity
        for entity in db.query(WorldEntity)
        .filter(WorldEntity.novel_id == novel_id)
        .all()
    }
    entity_ids_by_name: dict[str, int] = {}
    entities_written = 0

    for refined_entity in refinement.entities:
        name = refined_entity.name.strip()
        if not name:
            continue

        aliases = _normalize_aliases(refined_entity.aliases, name)
        entity_type = (
            refined_entity.entity_type.strip()
            if refined_entity.entity_type
            else "other"
        )
        if not entity_type:
            entity_type = "other"

        entity = existing_entities.get(name)
        if entity is None:
            entity = WorldEntity(
                novel_id=novel_id,
                name=name,
                entity_type=entity_type,
                aliases=aliases,
                origin="bootstrap",
                status="draft",
            )
            db.add(entity)
            db.flush()
            existing_entities[name] = entity
            entities_written += 1
        elif entity.status == "draft" and entity.origin == "bootstrap":
            entity.entity_type = entity_type
            merged_aliases = _normalize_aliases(
                [*(entity.aliases or []), *aliases], name
            )
            entity.aliases = merged_aliases
            entities_written += 1

        entity_ids_by_name[name] = entity.id

    # Relationships are bidirectional in the product semantics, so avoid duplicates
    # when the same (source, target, label_canonical) pair already exists in either direction.
    existing_relationship_keys = {
        relationship_signature_from_row(rel)
        for rel in db.query(WorldRelationship)
        .filter(WorldRelationship.novel_id == novel_id)
        .all()
    }
    relationships_written = 0

    for refined_relationship in refinement.relationships:
        source_name = refined_relationship.source_name.strip()
        target_name = refined_relationship.target_name.strip()
        label = refined_relationship.label.strip()
        if (
            not source_name
            or not target_name
            or not label
            or source_name == target_name
        ):
            continue
        source_id = entity_ids_by_name.get(source_name)
        target_id = entity_ids_by_name.get(target_name)
        if source_id is None:
            source = existing_entities.get(source_name)
            source_id = source.id if source else None
        if target_id is None:
            target = existing_entities.get(target_name)
            target_id = target.id if target else None
        if source_id is None or target_id is None:
            continue

        direct_key = build_relationship_signature(
            source_id=source_id, target_id=target_id, label=label
        )
        reverse_key = build_relationship_signature(
            source_id=target_id,
            target_id=source_id,
            label_canonical=direct_key[2],
        )
        if (
            direct_key in existing_relationship_keys
            or reverse_key in existing_relationship_keys
        ):
            continue

        new_rel = WorldRelationship(
            novel_id=novel_id,
            source_id=source_id,
            target_id=target_id,
            label=label,
            origin="bootstrap",
            status="draft",
        )
        db.add(new_rel)
        existing_relationship_keys.add(direct_key)
        relationships_written += 1

    db.flush()
    return entities_written, relationships_written


async def run_bootstrap_job(
    job_id: int,
    *,
    session_factory: Callable[[], Session] | None = None,
    client: AIClient | None = None,
    user_id: int | None = None,
    llm_config: dict | None = None,
) -> BootstrapRunSummary | None:
    make_session = session_factory or SessionLocal
    db = make_session()
    index_persisted = False
    target_index_revision = 0
    try:
        job = db.query(BootstrapJob).filter(BootstrapJob.id == job_id).first()
        if not job:
            return
        novel = db.query(Novel).filter(Novel.id == job.novel_id).first()
        if novel is None:
            raise ValueError(f"Novel not found: {job.novel_id}")

        mode = resolve_bootstrap_mode(job.mode)
        draft_policy = (
            resolve_reextract_draft_policy(job.draft_policy)
            if mode == BOOTSTRAP_MODE_REEXTRACT
            else None
        )
        job.mode = mode
        job.draft_policy = draft_policy

        settings = get_settings()
        chapters = load_chapter_texts(db, job.novel_id)
        if not chapters:
            raise ValueError("Novel has no non-empty chapter text to bootstrap")
        target_index_revision = resolve_window_index_target_revision(
            novel,
            has_source_text=True,
        )

        combined_text = "\n".join(chapter.text for chapter in chapters)
        logger.info(
            "bootstrap[%d]: loaded %d chapters, %d chars",
            job_id,
            len(chapters),
            len(combined_text),
        )

        transition_bootstrap_job(job, "tokenizing", detail="tokenizing chapters")
        db.commit()

        t0 = time.monotonic()
        artifacts = build_window_index_artifacts(
            chapters,
            novel_language=getattr(novel, "language", None),
            settings=settings,
            include_cooccurrence=mode != BOOTSTRAP_MODE_INDEX_REFRESH,
        )
        artifact_build_seconds = time.monotonic() - t0
        logger.info(
            "bootstrap[%d]: prepared index artifacts in %.1fs → %d tokens, %d candidates, %d important (%s)",
            job_id,
            artifact_build_seconds,
            len(artifacts.tokens),
            len(artifacts.candidates),
            len(artifacts.importance),
            artifacts.language,
        )

        transition_bootstrap_job(
            job, "extracting", detail=f"extracting candidates ({artifacts.language})"
        )
        db.commit()

        transition_bootstrap_job(job, "windowing", detail="building window index")
        db.commit()

        logger.info(
            "bootstrap[%d]: built window index → %d cooccurrence pairs (%s)",
            job_id,
            len(artifacts.cooccurrence_pairs),
            mode,
        )

        if mode == BOOTSTRAP_MODE_INDEX_REFRESH:
            transition_bootstrap_job(
                job, "refining", detail="refreshing window index only"
            )
        else:
            transition_bootstrap_job(
                job, "refining", detail="refining entities and relationships"
            )
        db.commit()

        mark_window_index_build_succeeded(
            novel,
            index_payload=artifacts.index.to_msgpack(),
            revision=target_index_revision,
        )
        db.commit()
        index_persisted = True

        if mode == BOOTSTRAP_MODE_INDEX_REFRESH:
            refinement = BootstrapRefinementResult()
        else:
            await acquire_llm_slot_blocking()
            try:
                refinement = await refine_candidates_with_llm(
                    artifacts.importance,
                    artifacts.cooccurrence_pairs,
                    max_candidates=settings.bootstrap_max_candidates,
                    temperature=settings.bootstrap_llm_temperature,
                    client=client,
                    llm_config=llm_config,
                    user_id=user_id,
                    novel_language=getattr(novel, "language", None),
                )
            finally:
                release_llm_slot()

        entities_found, relationships_found = persist_bootstrap_output(
            db,
            novel_id=job.novel_id,
            refinement=refinement,
            mode=mode,
            draft_policy=draft_policy,
        )
        if mode in {BOOTSTRAP_MODE_INITIAL, BOOTSTRAP_MODE_REEXTRACT}:
            job.initialized = True

        transition_bootstrap_job(
            job,
            "completed",
            detail="bootstrap completed",
            result={
                "entities_found": entities_found,
                "relationships_found": relationships_found,
                "index_refresh_only": mode == BOOTSTRAP_MODE_INDEX_REFRESH,
            },
        )
        db.commit()
        return BootstrapRunSummary(
            novel_id=job.novel_id,
            mode=mode,
            entities_found=entities_found,
            relationships_found=relationships_found,
        )
    except Exception as exc:  # pragma: no cover - defensive background task guard
        db.rollback()
        logger.exception("bootstrap background task failed")
        user_error, error_key = _sanitize_bootstrap_error(exc)
        try:
            failed_novel = db.query(Novel).filter(Novel.id == getattr(job, "novel_id", None)).first()
            if failed_novel is not None and not index_persisted:
                current_revision = int(getattr(failed_novel, "window_index_revision", 0) or 0)
                if current_revision <= target_index_revision:
                    mark_window_index_build_failed(
                        failed_novel,
                        error=user_error,
                        revision=max(target_index_revision, current_revision, 1),
                    )
            failed_job = (
                db.query(BootstrapJob).filter(BootstrapJob.id == job_id).first()
            )
            if failed_job and failed_job.status != "failed":
                transition_bootstrap_job(
                    failed_job, "failed", detail="bootstrap failed", error=user_error
                )
                failed_job.result = {"message_key": error_key}
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
