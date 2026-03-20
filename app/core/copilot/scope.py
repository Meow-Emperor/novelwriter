# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Scope loading and backend-sourced evidence helpers for copilot."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.indexing import (
    WINDOW_INDEX_STATUS_FAILED,
    WINDOW_INDEX_STATUS_FRESH,
    WINDOW_INDEX_STATUS_MISSING,
    WINDOW_INDEX_STATUS_STALE,
    WindowIndexLifecycleSnapshot,
    inspect_window_index_lifecycle,
)
from app.core.copilot.messages import CopilotTextKey, get_copilot_text
from app.models import (
    Chapter,
    Novel,
    WorldEntity,
    WorldEntityAttribute,
    WorldRelationship,
    WorldSystem,
)

logger = logging.getLogger(__name__)

CopilotRuntimeProfile = Literal["focused_research", "draft_governance", "broad_exploration"]
CopilotFocusVariant = Literal["entity", "relationship", "draft", "whole_book"]

MAX_EVIDENCE_ITEMS = 15
MAX_SCOPE_ENTITIES = 80
MAX_SCOPE_RELATIONSHIPS = 60
MAX_SCOPE_SYSTEMS = 30
MAX_CHAPTER_EXCERPT_CHARS = 2000


def _scope_text(
    interaction_locale: str,
    text_key: CopilotTextKey,
    **params: object,
) -> str:
    return get_copilot_text(text_key, locale=interaction_locale, **params)


def _append_scope_labeled_line(
    text: str,
    *,
    interaction_locale: str,
    label_key: CopilotTextKey,
    value: str,
) -> str:
    label = _scope_text(interaction_locale, label_key)
    return f"{text}\n{label}: {value}"


@dataclass
class ScopeSnapshot:
    """World-model state loaded by the backend for a copilot scope."""

    novel: Novel
    novel_language: str
    entities: list[WorldEntity]
    entities_by_id: dict[int, WorldEntity]
    relationships: list[WorldRelationship]
    systems: list[WorldSystem]
    attributes_by_entity: dict[int, list[WorldEntityAttribute]]
    draft_entities: list[WorldEntity]
    draft_relationships: list[WorldRelationship]
    draft_systems: list[WorldSystem]
    profile: str = "broad_exploration"
    focus_variant: str = "whole_book"
    focus_entity_id: int | None = None
    window_index_state: WindowIndexLifecycleSnapshot | None = None


@dataclass
class EvidenceItem:
    """A backend-sourced, verifiable evidence item."""

    evidence_id: str
    source_type: str
    source_ref: dict[str, Any]
    title: str
    excerpt: str
    why_relevant: str
    pack_id: str | None = None
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    anchor_terms: list[str] = field(default_factory=list)
    support_count: int | None = None
    preview_excerpt: str | None = None
    expanded: bool = False


def derive_runtime_profile(mode: str, scope: str, context: dict | None) -> CopilotRuntimeProfile:
    """Derive the bounded runtime profile used for isolation and preload policy."""
    if mode == "draft_cleanup":
        return "draft_governance"
    if scope == "whole_book":
        return "broad_exploration"
    return "focused_research"


def derive_focus_variant(mode: str, scope: str, context: dict | None) -> CopilotFocusVariant:
    """Derive the detailed workbench focus within the runtime profile."""
    if mode == "draft_cleanup":
        return "draft"
    if scope == "whole_book":
        return "whole_book"
    if context and context.get("tab") == "relationships":
        return "relationship"
    return "entity"


def _load_attributes_for_entities(
    db: Session,
    entity_ids: list[int],
) -> dict[int, list[WorldEntityAttribute]]:
    if not entity_ids:
        return {}

    attrs = (
        db.query(WorldEntityAttribute)
        .filter(WorldEntityAttribute.entity_id.in_(entity_ids))
        .order_by(WorldEntityAttribute.sort_order)
        .all()
    )
    attrs_by_entity: dict[int, list[WorldEntityAttribute]] = {}
    for attr in attrs:
        attrs_by_entity.setdefault(attr.entity_id, []).append(attr)
    return attrs_by_entity


def _build_scope_snapshot(
    *,
    novel: Novel,
    profile: CopilotRuntimeProfile,
    focus_variant: CopilotFocusVariant,
    focus_entity_id: int | None,
    entities: list[WorldEntity],
    relationships: list[WorldRelationship],
    systems: list[WorldSystem],
    attributes_by_entity: dict[int, list[WorldEntityAttribute]],
    window_index_state: WindowIndexLifecycleSnapshot,
) -> ScopeSnapshot:
    entities_by_id = {entity.id: entity for entity in entities}
    return ScopeSnapshot(
        novel=novel,
        novel_language=novel.language or "zh",
        entities=entities,
        entities_by_id=entities_by_id,
        relationships=relationships,
        systems=systems,
        attributes_by_entity=attributes_by_entity,
        draft_entities=[entity for entity in entities if entity.status == "draft"],
        draft_relationships=[relationship for relationship in relationships if relationship.status == "draft"],
        draft_systems=[system for system in systems if system.status == "draft"],
        profile=profile,
        focus_variant=focus_variant,
        focus_entity_id=focus_entity_id,
        window_index_state=window_index_state,
    )


def _load_broad_exploration_snapshot(
    db: Session,
    novel: Novel,
    *,
    focus_variant: CopilotFocusVariant,
    window_index_state: WindowIndexLifecycleSnapshot,
) -> ScopeSnapshot:
    novel_id = novel.id
    entities = (
        db.query(WorldEntity)
        .filter(WorldEntity.novel_id == novel_id)
        .limit(MAX_SCOPE_ENTITIES)
        .all()
    )
    relationships = (
        db.query(WorldRelationship)
        .filter(WorldRelationship.novel_id == novel_id)
        .limit(MAX_SCOPE_RELATIONSHIPS)
        .all()
    )
    systems = (
        db.query(WorldSystem)
        .filter(WorldSystem.novel_id == novel_id)
        .limit(MAX_SCOPE_SYSTEMS)
        .all()
    )
    attributes_by_entity = _load_attributes_for_entities(db, [entity.id for entity in entities])
    return _build_scope_snapshot(
        novel=novel,
        profile="broad_exploration",
        focus_variant=focus_variant,
        focus_entity_id=None,
        entities=entities,
        relationships=relationships,
        systems=systems,
        attributes_by_entity=attributes_by_entity,
        window_index_state=window_index_state,
    )


def _load_focused_research_snapshot(
    db: Session,
    novel: Novel,
    *,
    focus_variant: CopilotFocusVariant,
    focus_entity_id: int | None,
    window_index_state: WindowIndexLifecycleSnapshot,
) -> ScopeSnapshot:
    novel_id = novel.id
    entity_query = db.query(WorldEntity).filter(WorldEntity.novel_id == novel_id)
    relationship_query = db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel_id)

    if focus_entity_id is not None:
        relationships = relationship_query.filter(
            (WorldRelationship.source_id == focus_entity_id)
            | (WorldRelationship.target_id == focus_entity_id),
        ).limit(MAX_SCOPE_RELATIONSHIPS).all()

        entity_ids = {focus_entity_id}
        for relationship in relationships:
            entity_ids.add(relationship.source_id)
            entity_ids.add(relationship.target_id)

        entities = (
            entity_query
            .filter(WorldEntity.id.in_(entity_ids))
            .limit(MAX_SCOPE_ENTITIES)
            .all()
        )
    else:
        entities = entity_query.limit(min(MAX_SCOPE_ENTITIES, 16)).all()
        entity_ids = {entity.id for entity in entities}
        if entity_ids:
            relationships = relationship_query.filter(
                (WorldRelationship.source_id.in_(entity_ids))
                | (WorldRelationship.target_id.in_(entity_ids)),
            ).limit(min(MAX_SCOPE_RELATIONSHIPS, 20)).all()
        else:
            relationships = []

    attributes_by_entity = _load_attributes_for_entities(db, [entity.id for entity in entities])
    return _build_scope_snapshot(
        novel=novel,
        profile="focused_research",
        focus_variant=focus_variant,
        focus_entity_id=focus_entity_id,
        entities=entities,
        relationships=relationships,
        systems=[],
        attributes_by_entity=attributes_by_entity,
        window_index_state=window_index_state,
    )


def _load_draft_governance_snapshot(
    db: Session,
    novel: Novel,
    *,
    window_index_state: WindowIndexLifecycleSnapshot,
) -> ScopeSnapshot:
    novel_id = novel.id
    draft_entities = (
        db.query(WorldEntity)
        .filter(WorldEntity.novel_id == novel_id, WorldEntity.status == "draft")
        .limit(MAX_SCOPE_ENTITIES)
        .all()
    )
    draft_relationships = (
        db.query(WorldRelationship)
        .filter(WorldRelationship.novel_id == novel_id, WorldRelationship.status == "draft")
        .limit(MAX_SCOPE_RELATIONSHIPS)
        .all()
    )
    draft_systems = (
        db.query(WorldSystem)
        .filter(WorldSystem.novel_id == novel_id, WorldSystem.status == "draft")
        .limit(MAX_SCOPE_SYSTEMS)
        .all()
    )

    entity_ids = {entity.id for entity in draft_entities}
    for relationship in draft_relationships:
        entity_ids.add(relationship.source_id)
        entity_ids.add(relationship.target_id)

    entities = (
        db.query(WorldEntity)
        .filter(WorldEntity.novel_id == novel_id, WorldEntity.id.in_(entity_ids))
        .all()
        if entity_ids
        else []
    )
    attributes_by_entity = _load_attributes_for_entities(db, [entity.id for entity in entities])
    return _build_scope_snapshot(
        novel=novel,
        profile="draft_governance",
        focus_variant="draft",
        focus_entity_id=None,
        entities=entities,
        relationships=draft_relationships,
        systems=draft_systems,
        attributes_by_entity=attributes_by_entity,
        window_index_state=window_index_state,
    )


def load_scope_snapshot(db: Session, novel: Novel, mode: str, scope: str, context: dict | None) -> ScopeSnapshot:
    """Load world-model state relevant to the current copilot scope."""
    profile = derive_runtime_profile(mode, scope, context)
    focus_variant = derive_focus_variant(mode, scope, context)
    window_index_state = inspect_window_index_lifecycle(novel, db=db)
    focus_entity_id = (context or {}).get("entity_id")
    if not isinstance(focus_entity_id, int):
        focus_entity_id = None

    if profile == "draft_governance":
        return _load_draft_governance_snapshot(db, novel, window_index_state=window_index_state)
    if profile == "focused_research":
        return _load_focused_research_snapshot(
            db,
            novel,
            focus_variant=focus_variant,
            focus_entity_id=focus_entity_id,
            window_index_state=window_index_state,
        )
    return _load_broad_exploration_snapshot(
        db,
        novel,
        focus_variant=focus_variant,
        window_index_state=window_index_state,
    )


def gather_evidence(
    db: Session,
    novel: Novel,
    snapshot: ScopeSnapshot,
    context: dict | None,
    interaction_locale: str = "zh",
) -> list[EvidenceItem]:
    """Gather evidence from backend-known sources BEFORE the LLM call."""
    items: list[EvidenceItem] = []

    if snapshot.profile == "draft_governance":
        _gather_draft_row_evidence(snapshot, items, interaction_locale)
        if snapshot.focus_entity_id is not None:
            _gather_chapter_evidence(db, novel, context, snapshot, items, interaction_locale)
    else:
        _gather_chapter_evidence(db, novel, context, snapshot, items, interaction_locale)
        _gather_entity_evidence(snapshot, context, items, interaction_locale)
        _gather_relationship_evidence(snapshot, context, items, interaction_locale)

    return items[:MAX_EVIDENCE_ITEMS]


def _gather_chapter_evidence(
    db: Session,
    novel: Novel,
    context: dict | None,
    snapshot: ScopeSnapshot,
    items: list[EvidenceItem],
    interaction_locale: str,
) -> None:
    """Gather chapter excerpts from window index or tail chapters."""
    from app.core.indexing.window_index import NovelIndex

    lifecycle = snapshot.window_index_state
    use_window_index = bool(
        lifecycle
        and lifecycle.status == WINDOW_INDEX_STATUS_FRESH
        and lifecycle.has_payload
        and novel.window_index
    )

    if context and context.get("entity_id") and use_window_index:
        entity = snapshot.entities_by_id.get(context["entity_id"])
        if entity:
            try:
                index = NovelIndex.from_msgpack(novel.window_index)
                windows = index.find_entity_passages(entity.name, limit=6)
                for window in windows:
                    chapter = db.get(Chapter, window.chapter_id)
                    if chapter and chapter.content:
                        start = max(0, window.start_pos)
                        end = min(len(chapter.content), window.end_pos)
                        text = chapter.content[start:end]
                        if text.strip():
                            items.append(EvidenceItem(
                                evidence_id=f"ch_{chapter.id}_{start}",
                                source_type="chapter_excerpt",
                                source_ref={
                                    "chapter_id": chapter.id,
                                    "chapter_number": chapter.chapter_number,
                                    "start_pos": start,
                                    "end_pos": end,
                                },
                                title=_scope_text(
                                    interaction_locale,
                                    CopilotTextKey.SCOPE_CHAPTER_WINDOW_TITLE,
                                    chapter_number=chapter.chapter_number,
                                    start=start,
                                    end=end,
                                ),
                                excerpt=text[:MAX_CHAPTER_EXCERPT_CHARS],
                                why_relevant=_scope_text(
                                    interaction_locale,
                                    CopilotTextKey.SCOPE_CHAPTER_MENTIONS_ENTITY,
                                    entity_name=entity.name,
                                ),
                            ))
            except Exception:
                logger.debug("Window index load failed, falling back to tail chapters", exc_info=True)

    if len(items) < 3 and snapshot.focus_variant != "whole_book":
        fallback_reason = _scope_text(interaction_locale, CopilotTextKey.SCOPE_RECENT_CHAPTER_CONTEXT)
        if lifecycle and lifecycle.status == WINDOW_INDEX_STATUS_STALE:
            fallback_reason = _scope_text(interaction_locale, CopilotTextKey.SCOPE_STALE_RECENT_CHAPTER_CONTEXT)
        elif lifecycle and lifecycle.status == WINDOW_INDEX_STATUS_MISSING:
            fallback_reason = _scope_text(interaction_locale, CopilotTextKey.SCOPE_MISSING_RECENT_CHAPTER_CONTEXT)
        elif lifecycle and lifecycle.status == WINDOW_INDEX_STATUS_FAILED:
            fallback_reason = _scope_text(interaction_locale, CopilotTextKey.SCOPE_FAILED_RECENT_CHAPTER_CONTEXT)
        chapters = (
            db.query(Chapter)
            .filter(Chapter.novel_id == novel.id)
            .order_by(Chapter.chapter_number.desc())
            .limit(3)
            .all()
        )
        seen_ch_ids = {item.source_ref.get("chapter_id") for item in items if item.source_type == "chapter_excerpt"}
        for chapter in chapters:
            if chapter.id in seen_ch_ids or not chapter.content or not chapter.content.strip():
                continue
            text = (
                chapter.content[-MAX_CHAPTER_EXCERPT_CHARS:]
                if len(chapter.content) > MAX_CHAPTER_EXCERPT_CHARS
                else chapter.content
            )
            items.append(EvidenceItem(
                evidence_id=f"ch_{chapter.id}_tail",
                source_type="chapter_excerpt",
                source_ref={
                    "chapter_id": chapter.id,
                    "chapter_number": chapter.chapter_number,
                    "start_pos": max(0, len(chapter.content) - MAX_CHAPTER_EXCERPT_CHARS),
                    "end_pos": len(chapter.content),
                },
                title=_scope_text(
                    interaction_locale,
                    CopilotTextKey.SCOPE_CHAPTER_TAIL_TITLE,
                    chapter_number=chapter.chapter_number,
                ),
                excerpt=text[:MAX_CHAPTER_EXCERPT_CHARS],
                why_relevant=fallback_reason,
            ))


def _gather_entity_evidence(
    snapshot: ScopeSnapshot,
    context: dict | None,
    items: list[EvidenceItem],
    interaction_locale: str,
) -> None:
    """Add world-model entity rows as evidence items."""
    target_id = (context or {}).get("entity_id")
    if target_id:
        entity = snapshot.entities_by_id.get(target_id)
        if entity:
            desc = entity.description[:500] if entity.description else _scope_text(
                interaction_locale,
                CopilotTextKey.TEXT_NO_DESCRIPTION,
            )
            attrs = snapshot.attributes_by_entity.get(entity.id, [])
            attr_text = "; ".join(f"{attr.key}={attr.surface[:80]}" for attr in attrs[:5])
            excerpt = f"{entity.name} ({entity.entity_type}): {desc}"
            if attr_text:
                excerpt = _append_scope_labeled_line(
                    excerpt,
                    interaction_locale=interaction_locale,
                    label_key=CopilotTextKey.TEXT_ATTRIBUTES_LABEL,
                    value=attr_text,
                )
            items.append(EvidenceItem(
                evidence_id=f"ent_{entity.id}",
                source_type="world_entity",
                source_ref={"entity_id": entity.id},
                title=_scope_text(
                    interaction_locale,
                    CopilotTextKey.SCOPE_ENTITY_TITLE,
                    entity_name=entity.name,
                ),
                excerpt=excerpt,
                why_relevant=_scope_text(interaction_locale, CopilotTextKey.SCOPE_ENTITY_TARGET_REASON),
            ))


def _gather_relationship_evidence(
    snapshot: ScopeSnapshot,
    context: dict | None,
    items: list[EvidenceItem],
    interaction_locale: str,
) -> None:
    """Add relationship rows as evidence for relationship-scoped work."""
    target_id = (context or {}).get("entity_id")
    if not target_id:
        return
    for relationship in snapshot.relationships[:10]:
        if relationship.source_id == target_id or relationship.target_id == target_id:
            source = snapshot.entities_by_id.get(relationship.source_id)
            target = snapshot.entities_by_id.get(relationship.target_id)
            source_name = source.name if source else f"#{relationship.source_id}"
            target_name = target.name if target else f"#{relationship.target_id}"
            description = relationship.description[:200] if relationship.description else ""
            items.append(EvidenceItem(
                evidence_id=f"rel_{relationship.id}",
                source_type="world_relationship",
                source_ref={
                    "relationship_id": relationship.id,
                    "source_id": relationship.source_id,
                    "target_id": relationship.target_id,
                },
                title=f"{source_name} --[{relationship.label}]--> {target_name}",
                excerpt=_scope_text(
                    interaction_locale,
                    CopilotTextKey.SCOPE_RELATIONSHIP_EXCERPT,
                    source_name=source_name,
                    label=relationship.label,
                    target_name=target_name,
                    description=description,
                ),
                why_relevant=_scope_text(interaction_locale, CopilotTextKey.SCOPE_RELATIONSHIP_TARGET_REASON),
            ))


def _gather_draft_row_evidence(snapshot: ScopeSnapshot, items: list[EvidenceItem], interaction_locale: str) -> None:
    """Surface draft rows themselves as first-class evidence in draft governance."""
    for entity in snapshot.draft_entities[:6]:
        attrs = snapshot.attributes_by_entity.get(entity.id, [])
        attr_text = "; ".join(f"{attr.key}={attr.surface[:60]}" for attr in attrs[:4])
        excerpt = _scope_text(
            interaction_locale,
            CopilotTextKey.SCOPE_DRAFT_ENTITY_EXCERPT,
            entity_name=entity.name,
            entity_type=entity.entity_type,
        )
        if entity.description:
            excerpt = _append_scope_labeled_line(
                excerpt,
                interaction_locale=interaction_locale,
                label_key=CopilotTextKey.TEXT_DESCRIPTION_LABEL,
                value=entity.description[:200],
            )
        else:
            excerpt = _append_scope_labeled_line(
                excerpt,
                interaction_locale=interaction_locale,
                label_key=CopilotTextKey.TEXT_DESCRIPTION_LABEL,
                value=_scope_text(interaction_locale, CopilotTextKey.TEXT_NO_DESCRIPTION),
            )
        if attr_text:
            excerpt = _append_scope_labeled_line(
                excerpt,
                interaction_locale=interaction_locale,
                label_key=CopilotTextKey.TEXT_ATTRIBUTES_LABEL,
                value=attr_text,
            )
        items.append(EvidenceItem(
            evidence_id=f"draft_ent_{entity.id}",
            source_type="world_entity",
            source_ref={"entity_id": entity.id},
            title=_scope_text(
                interaction_locale,
                CopilotTextKey.SCOPE_DRAFT_ENTITY_TITLE,
                entity_name=entity.name,
            ),
            excerpt=excerpt,
            why_relevant=_scope_text(interaction_locale, CopilotTextKey.SCOPE_DRAFT_ENTITY_REASON),
        ))

    for relationship in snapshot.draft_relationships[:6]:
        source = snapshot.entities_by_id.get(relationship.source_id)
        target = snapshot.entities_by_id.get(relationship.target_id)
        excerpt = _scope_text(
            interaction_locale,
            CopilotTextKey.SCOPE_DRAFT_RELATIONSHIP_EXCERPT,
            source_name=source.name if source else "?",
            label=relationship.label,
            target_name=target.name if target else "?",
        )
        if relationship.description:
            excerpt = _append_scope_labeled_line(
                excerpt,
                interaction_locale=interaction_locale,
                label_key=CopilotTextKey.TEXT_DESCRIPTION_LABEL,
                value=relationship.description[:200],
            )
        else:
            excerpt = _append_scope_labeled_line(
                excerpt,
                interaction_locale=interaction_locale,
                label_key=CopilotTextKey.TEXT_DESCRIPTION_LABEL,
                value=_scope_text(interaction_locale, CopilotTextKey.TEXT_NO_DESCRIPTION),
            )
        items.append(EvidenceItem(
            evidence_id=f"draft_rel_{relationship.id}",
            source_type="world_relationship",
            source_ref={
                "relationship_id": relationship.id,
                "source_id": relationship.source_id,
                "target_id": relationship.target_id,
            },
            title=_scope_text(
                interaction_locale,
                CopilotTextKey.SCOPE_DRAFT_RELATIONSHIP_TITLE,
                label=relationship.label,
            ),
            excerpt=excerpt,
            why_relevant=_scope_text(interaction_locale, CopilotTextKey.SCOPE_DRAFT_RELATIONSHIP_REASON),
        ))

    for system in snapshot.draft_systems[:4]:
        excerpt = _scope_text(
            interaction_locale,
            CopilotTextKey.SCOPE_DRAFT_SYSTEM_EXCERPT,
            system_name=system.name,
        )
        if system.description:
            excerpt = _append_scope_labeled_line(
                excerpt,
                interaction_locale=interaction_locale,
                label_key=CopilotTextKey.TEXT_DESCRIPTION_LABEL,
                value=system.description[:200],
            )
        items.append(EvidenceItem(
            evidence_id=f"draft_sys_{system.id}",
            source_type="world_system",
            source_ref={"system_id": system.id},
            title=_scope_text(
                interaction_locale,
                CopilotTextKey.SCOPE_DRAFT_SYSTEM_TITLE,
                system_name=system.name,
            ),
            excerpt=excerpt,
            why_relevant=_scope_text(interaction_locale, CopilotTextKey.SCOPE_DRAFT_SYSTEM_REASON),
        ))


def serialize_evidence(evidence: EvidenceItem) -> dict[str, Any]:
    return {
        "evidence_id": evidence.evidence_id,
        "source_type": evidence.source_type,
        "source_ref": evidence.source_ref,
        "title": evidence.title,
        "excerpt": evidence.excerpt,
        "why_relevant": evidence.why_relevant,
        "pack_id": evidence.pack_id,
        "source_refs": evidence.source_refs,
        "anchor_terms": evidence.anchor_terms,
        "support_count": evidence.support_count,
        "preview_excerpt": evidence.preview_excerpt,
        "expanded": evidence.expanded,
    }
