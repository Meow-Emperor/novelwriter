# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Deterministic research-tool surface for copilot tool-loop runs."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.indexing import WINDOW_INDEX_STATUS_FRESH
from app.core.copilot.scope import ScopeSnapshot
from app.core.copilot.workspace import EvidencePack, Workspace, make_pack_id
from app.language_policy import get_language_policy
from app.models import Chapter, Novel, WorldEntity, WorldRelationship, WorldSystem

logger = logging.getLogger(__name__)

MAX_EVIDENCE_PACKS = 12
_QUERY_TERM_SPLIT_RE = re.compile(r"[\s,，、；;|/]+")

_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "load_scope_snapshot",
            "description": "Re-load world-model state: entities, relationships, systems, drafts. Use when you need a fresh view.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find",
            "description": "Research query. Returns evidence packs with stable IDs for progressive disclosure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Free-text research query"},
                    "scope": {
                        "type": "string",
                        "enum": ["story_text", "world_rows", "drafts", "all"],
                        "description": "Search scope filter (default: all)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open",
            "description": "Expand a previously-found evidence pack to see full content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pack_id": {"type": "string", "description": "Pack ID from a find result"},
                    "expand_chars": {"type": "integer", "description": "Max chars to expand (default 2000)"},
                },
                "required": ["pack_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read live world state for specific targets (entities, relationships, systems).",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_refs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": ["entity", "relationship", "system"]},
                                "id": {"type": "integer"},
                            },
                            "required": ["type", "id"],
                        },
                        "description": "Targets to read",
                    },
                },
                "required": ["target_refs"],
            },
        },
    },
]


def dispatch_tool(
    tool_name: str,
    tool_args: dict[str, Any],
    db: Session,
    novel_id: int,
    snapshot: ScopeSnapshot,
    workspace: Workspace,
) -> str:
    """Dispatch a single research tool call."""
    if tool_name == "find":
        return _tool_find(
            tool_args.get("query", ""),
            tool_args.get("scope", "all"),
            db,
            novel_id,
            snapshot.novel,
            snapshot,
            workspace,
        )
    if tool_name == "open":
        return _tool_open(
            tool_args.get("pack_id", ""),
            tool_args.get("expand_chars", 2000),
            db,
            snapshot.novel,
            workspace,
        )
    if tool_name == "read":
        return _tool_read(tool_args.get("target_refs", []), db, novel_id, snapshot)
    return json.dumps({"error": f"Unknown tool: {tool_name}"})


def tool_load_scope_snapshot(snapshot: ScopeSnapshot) -> str:
    """Render a structured summary for the live scope snapshot tool."""
    entity_names = [
        f"{entity.name}({entity.entity_type})" + (" [draft]" if entity.status == "draft" else "")
        for entity in snapshot.entities[:40]
    ]
    draft_count = (
        len(snapshot.draft_entities)
        + len(snapshot.draft_relationships)
        + len(snapshot.draft_systems)
    )
    return json.dumps({
        "profile": snapshot.profile,
        "focus_variant": snapshot.focus_variant,
        "focus_entity_id": snapshot.focus_entity_id,
        "entities": entity_names,
        "entity_count": len(snapshot.entities),
        "relationship_count": len(snapshot.relationships),
        "systems": [system.name for system in snapshot.systems],
        "draft_count": draft_count,
    }, ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class QueryTerm:
    raw: str
    normalized: str


def _extract_query_terms(query: str, language: str | None) -> list[QueryTerm]:
    raw_query = (query or "").strip()
    if not raw_query:
        return []

    policy = get_language_policy(language, sample_text=raw_query)
    raw_chunks = [chunk.strip() for chunk in _QUERY_TERM_SPLIT_RE.split(raw_query) if chunk.strip()]
    candidate_terms: list[str] = []

    if len(raw_chunks) > 1:
        candidate_terms.extend(raw_chunks)
    else:
        candidate_terms.append(raw_query)
        try:
            from app.core.indexing.builder import get_tokenizer

            tokenizer = get_tokenizer(policy.language)
            candidate_terms.extend(tokenizer.tokenize(raw_query))
        except Exception:
            logger.debug("Copilot query tokenization fallback engaged", exc_info=True)

    extracted: list[QueryTerm] = []
    seen: set[str] = set()
    for raw_term in candidate_terms:
        cleaned = policy.normalize_token(raw_term)
        normalized = policy.normalize_for_matching(cleaned)
        if len(normalized) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        extracted.append(QueryTerm(raw=cleaned, normalized=normalized))

    return extracted[:12]


def _find_term_matches(
    text: str,
    query_terms: list[QueryTerm],
    *,
    language: str | None,
) -> list[tuple[int, int, QueryTerm]]:
    if not text or not query_terms:
        return []

    policy = get_language_policy(language, sample_text=text)
    normalized_text = policy.normalize_for_matching(text)
    matches: list[tuple[int, int, QueryTerm]] = []

    for term in query_terms:
        search_from = 0
        while search_from < len(normalized_text):
            pos = normalized_text.find(term.normalized, search_from)
            if pos == -1:
                break
            end = pos + len(term.normalized)
            if policy.match_has_word_boundaries(normalized_text, pos, end):
                matches.append((pos, end, term))
            search_from = max(pos + 1, end)

    matches.sort(key=lambda item: item[0])
    return matches


def _resolve_excerpt_window(
    text: str,
    matches: list[tuple[int, int, QueryTerm]],
) -> tuple[int, int]:
    if not text:
        return 0, 0
    if not matches:
        return 0, min(len(text), 500)

    cluster_start = matches[0][0]
    cluster_end = matches[0][1]
    for start, end, _ in matches[1:4]:
        if start - cluster_end > 220:
            break
        cluster_end = end

    start = max(0, cluster_start - 200)
    end = min(len(text), cluster_end + 320)
    if end <= start:
        end = min(len(text), start + 500)
    return start, end


def _summarize_matched_terms(matches: list[tuple[int, int, QueryTerm]]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for _, _, term in matches:
        if term.normalized in seen:
            continue
        seen.add(term.normalized)
        terms.append(term.raw)
    return terms


def _tool_find(
    query: str,
    scope_filter: str,
    db: Session,
    _novel_id: int,
    novel: Novel,
    snapshot: ScopeSnapshot,
    workspace: Workspace,
) -> str:
    packs: list[EvidencePack] = []

    if scope_filter in ("world_rows", "all"):
        packs += _find_from_world_rows(query, snapshot)

    if scope_filter in ("story_text", "all"):
        packs += _find_from_window_index(query, db, _novel_id, novel, snapshot)

    if scope_filter == "drafts":
        packs += _find_from_draft_auditors(snapshot)

    if len(packs) < 3 and scope_filter in ("story_text", "all"):
        packs += _find_from_chapters(query, db, novel)

    deduped = _deduplicate_packs(packs)[:MAX_EVIDENCE_PACKS]
    for pack in deduped:
        workspace.evidence_packs[pack.pack_id] = pack

    return json.dumps({
        "packs": [
            {
                "pack_id": pack.pack_id,
                "preview": pack.preview_excerpt[:300],
                "anchor_terms": pack.anchor_terms,
                "support_count": pack.support_count,
            }
            for pack in deduped
        ],
        "total_found": len(deduped),
    }, ensure_ascii=False)


def _find_from_world_rows(query: str, snapshot: ScopeSnapshot) -> list[EvidencePack]:
    packs: list[EvidencePack] = []
    query_terms = _extract_query_terms(query, snapshot.novel_language)
    if not query_terms:
        return []

    for entity in snapshot.entities:
        attrs = snapshot.attributes_by_entity.get(entity.id, [])
        attr_text = "; ".join(f"{attr.key}={attr.surface[:80]}" for attr in attrs[:5])
        match_terms = _summarize_matched_terms(
            _find_term_matches(
                "\n".join([entity.name, *(entity.aliases or []), entity.description or "", attr_text]),
                query_terms,
                language=snapshot.novel_language,
            )
        )
        if not match_terms:
            continue

        excerpt = f"{entity.name} ({entity.entity_type}): {(entity.description or '')[:300]}"
        if attr_text:
            excerpt += f"\n属性: {attr_text}"

        packs.append(EvidencePack(
            pack_id=make_pack_id(f"pk_ent_{entity.id}", excerpt[:100]),
            source_refs=[{"type": "entity", "id": entity.id}],
            preview_excerpt=excerpt[:500],
            anchor_terms=match_terms[:5],
            support_count=len(match_terms),
            related_targets=[{"type": "entity", "id": entity.id, "name": entity.name}],
        ))

    for relationship in snapshot.relationships:
        src = snapshot.entities_by_id.get(relationship.source_id)
        tgt = snapshot.entities_by_id.get(relationship.target_id)
        src_name = src.name if src else f"#{relationship.source_id}"
        tgt_name = tgt.name if tgt else f"#{relationship.target_id}"
        text = f"{src_name} --[{relationship.label}]--> {tgt_name}: {(relationship.description or '')[:200]}"
        match_terms = _summarize_matched_terms(
            _find_term_matches(text, query_terms, language=snapshot.novel_language)
        )
        if not match_terms:
            continue
        packs.append(EvidencePack(
            pack_id=make_pack_id(f"pk_rel_{relationship.id}", text[:100]),
            source_refs=[{"type": "relationship", "id": relationship.id}],
            preview_excerpt=text[:500],
            anchor_terms=match_terms[:5],
            support_count=len(match_terms),
            related_targets=[
                {"type": "entity", "id": relationship.source_id, "name": src_name},
                {"type": "entity", "id": relationship.target_id, "name": tgt_name},
            ],
        ))

    for system in snapshot.systems:
        text = f"{system.name} ({system.display_type}): {(system.description or '')[:300]}"
        if system.constraints:
            text += "\n约束: " + "; ".join(str(item)[:80] for item in system.constraints[:6])
        match_terms = _summarize_matched_terms(
            _find_term_matches(text, query_terms, language=snapshot.novel_language)
        )
        if not match_terms:
            continue
        packs.append(EvidencePack(
            pack_id=make_pack_id(f"pk_sys_{system.id}", text[:100]),
            source_refs=[{"type": "system", "id": system.id}],
            preview_excerpt=text[:500],
            anchor_terms=match_terms[:5],
            support_count=len(match_terms),
            related_targets=[{"type": "system", "id": system.id, "name": system.name}],
        ))

    return packs


def _find_from_window_index(
    query: str,
    db: Session,
    _novel_id: int,
    novel: Novel,
    snapshot: ScopeSnapshot,
) -> list[EvidencePack]:
    from app.core.indexing.window_index import NovelIndex

    lifecycle = snapshot.window_index_state
    if not (
        lifecycle
        and lifecycle.status == WINDOW_INDEX_STATUS_FRESH
        and lifecycle.has_payload
        and novel.window_index
    ):
        return []

    query_terms = _extract_query_terms(query, novel.language or snapshot.novel_language)
    if not query_terms:
        return []

    candidate_name_rows: list[tuple[str, list[str]]] = []
    for entity in snapshot.entities:
        match_terms = _summarize_matched_terms(
            _find_term_matches(
                "\n".join([entity.name, *(entity.aliases or [])]),
                query_terms,
                language=novel.language or snapshot.novel_language,
            )
        )
        if match_terms:
            candidate_name_rows.append((entity.name, match_terms))

    candidate_name_rows.sort(key=lambda item: (-len(item[1]), item[0]))
    if not candidate_name_rows:
        candidate_name_rows = [(query.strip(), [query.strip()])]

    packs: list[EvidencePack] = []
    try:
        index = NovelIndex.from_msgpack(novel.window_index)
    except Exception:
        logger.debug("Window index load failed in find", exc_info=True)
        return []

    seen_windows: set[tuple[int, int]] = set()
    for name, anchor_terms in candidate_name_rows[:5]:
        windows = index.find_entity_passages(name, limit=4)
        for window in windows:
            key = (window.chapter_id, window.start_pos)
            if key in seen_windows:
                continue
            seen_windows.add(key)

            chapter = db.get(Chapter, window.chapter_id)
            if not chapter or not chapter.content:
                continue
            start = max(0, window.start_pos)
            end = min(len(chapter.content), window.end_pos)
            text = chapter.content[start:end]
            if not text.strip():
                continue

            packs.append(EvidencePack(
                pack_id=make_pack_id(f"pk_ch_{chapter.id}_{start}_{end}", text[:100]),
                source_refs=[{
                    "type": "chapter",
                    "chapter_id": chapter.id,
                    "chapter_number": chapter.chapter_number,
                    "start_pos": start,
                    "end_pos": end,
                }],
                preview_excerpt=text[:500],
                anchor_terms=anchor_terms[:5] or [name],
                support_count=max(window.entity_count, len(anchor_terms)),
                related_targets=[{"type": "chapter", "chapter_id": chapter.id}],
            ))

    return packs


def _find_from_draft_auditors(snapshot: ScopeSnapshot) -> list[EvidencePack]:
    packs: list[EvidencePack] = []

    for entity in snapshot.draft_entities:
        issues: list[str] = []
        if not entity.description or not entity.description.strip():
            issues.append("空描述")
        if not entity.aliases:
            issues.append("无别名")
        attrs = snapshot.attributes_by_entity.get(entity.id, [])
        if not attrs:
            issues.append("无属性")
        if issues:
            excerpt = f"[草稿实体] {entity.name} ({entity.entity_type}) — 问题: {', '.join(issues)}"
            packs.append(EvidencePack(
                pack_id=make_pack_id(f"pk_draft_ent_{entity.id}", excerpt),
                source_refs=[{"type": "entity", "id": entity.id}],
                preview_excerpt=excerpt,
                anchor_terms=[entity.name],
                support_count=len(issues),
                related_targets=[{"type": "entity", "id": entity.id, "name": entity.name}],
                conflict_group="draft_quality",
            ))

    for relationship in snapshot.draft_relationships:
        if not relationship.description or not relationship.description.strip():
            src = snapshot.entities_by_id.get(relationship.source_id)
            tgt = snapshot.entities_by_id.get(relationship.target_id)
            excerpt = f"[草稿关系] {src.name if src else '?'} --[{relationship.label}]--> {tgt.name if tgt else '?'} — 空描述"
            packs.append(EvidencePack(
                pack_id=make_pack_id(f"pk_draft_rel_{relationship.id}", excerpt),
                source_refs=[{"type": "relationship", "id": relationship.id}],
                preview_excerpt=excerpt,
                anchor_terms=[relationship.label],
                support_count=1,
                related_targets=[],
                conflict_group="draft_quality",
            ))

    for system in snapshot.draft_systems:
        issues: list[str] = []
        if not system.description or not system.description.strip():
            issues.append("空描述")
        if not system.constraints:
            issues.append("无约束")
        if issues:
            excerpt = f"[草稿体系] {system.name} — 问题: {', '.join(issues)}"
            packs.append(EvidencePack(
                pack_id=make_pack_id(f"pk_draft_sys_{system.id}", excerpt),
                source_refs=[{"type": "system", "id": system.id}],
                preview_excerpt=excerpt,
                anchor_terms=[system.name],
                support_count=len(issues),
                related_targets=[{"type": "system", "id": system.id, "name": system.name}],
                conflict_group="draft_quality",
            ))

    return packs


def _find_from_chapters(query: str, db: Session, novel: Novel) -> list[EvidencePack]:
    query_terms = _extract_query_terms(query, novel.language)
    if not query_terms:
        return []

    scored: list[tuple[int, int, int, EvidencePack]] = []
    chapters = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel.id)
        .order_by(Chapter.chapter_number.asc())
        .all()
    )
    for chapter in chapters:
        if not chapter.content:
            continue
        matches = _find_term_matches(chapter.content, query_terms, language=novel.language)
        if not matches:
            continue
        matched_terms = _summarize_matched_terms(matches)
        start, end = _resolve_excerpt_window(chapter.content, matches)
        text = chapter.content[start:end]
        pack = EvidencePack(
            pack_id=make_pack_id(f"pk_ch_{chapter.id}_{start}_{end}", text[:100]),
            source_refs=[{
                "type": "chapter",
                "chapter_id": chapter.id,
                "chapter_number": chapter.chapter_number,
                "start_pos": start,
                "end_pos": end,
            }],
            preview_excerpt=text[:500],
            anchor_terms=matched_terms[:5],
            support_count=len(matched_terms),
            related_targets=[{"type": "chapter", "chapter_id": chapter.id}],
        )
        scored.append((len(matched_terms), len(matches), chapter.chapter_number, pack))

    scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [item[3] for item in scored[:MAX_EVIDENCE_PACKS]]


def _deduplicate_packs(packs: list[EvidencePack]) -> list[EvidencePack]:
    seen: dict[str, EvidencePack] = {}
    for pack in packs:
        if pack.pack_id not in seen or pack.support_count > seen[pack.pack_id].support_count:
            seen[pack.pack_id] = pack
    return sorted(
        seen.values(),
        key=lambda pack: (-(pack.support_count or 0), pack.pack_id),
    )


def _tool_open(
    pack_id: str,
    expand_chars: int,
    db: Session,
    _novel: Novel,
    workspace: Workspace,
) -> str:
    pack = workspace.evidence_packs.get(pack_id)
    if not pack:
        return json.dumps({"error": f"Unknown pack_id: {pack_id}. Use find() first."})

    expand_chars = min(expand_chars or 2000, 4000)
    for ref in pack.source_refs:
        if ref.get("type") == "chapter" and ref.get("chapter_id"):
            chapter = db.get(Chapter, ref["chapter_id"])
            if chapter and chapter.content:
                start = max(0, ref.get("start_pos", 0) - 200)
                end = min(len(chapter.content), ref.get("end_pos", 0) + expand_chars)
                pack.expanded_text = chapter.content[start:end]

    if pack_id not in workspace.opened_pack_ids:
        workspace.opened_pack_ids.append(pack_id)

    return json.dumps({
        "pack_id": pack_id,
        "expanded_text": pack.expanded_text or pack.preview_excerpt,
        "source_refs": pack.source_refs,
    }, ensure_ascii=False)


def _tool_read(
    target_refs: list[dict[str, Any]],
    db: Session,
    novel_id: int,
    snapshot: ScopeSnapshot,
) -> str:
    results: list[dict[str, Any]] = []
    for ref in target_refs[:10]:
        ref_type = ref.get("type", "")
        ref_id = ref.get("id")
        if not ref_id:
            continue
        if ref_type == "entity":
            entity = snapshot.entities_by_id.get(ref_id)
            if not entity:
                entity = (
                    db.query(WorldEntity)
                    .filter(WorldEntity.id == ref_id, WorldEntity.novel_id == novel_id)
                    .first()
                )
            if entity:
                attrs = snapshot.attributes_by_entity.get(entity.id, [])
                results.append({
                    "type": "entity",
                    "id": entity.id,
                    "name": entity.name,
                    "entity_type": entity.entity_type,
                    "description": (entity.description or "")[:500],
                    "aliases": entity.aliases or [],
                    "status": entity.status,
                    "attributes": [
                        {
                            "key": attr.key,
                            "surface": attr.surface[:200],
                            "visibility": attr.visibility,
                        }
                        for attr in attrs[:10]
                    ],
                })
        elif ref_type == "relationship":
            relationship = next(
                (rel for rel in snapshot.relationships if rel.id == ref_id),
                None,
            )
            if not relationship:
                relationship = (
                    db.query(WorldRelationship)
                    .filter(WorldRelationship.id == ref_id, WorldRelationship.novel_id == novel_id)
                    .first()
                )
            if relationship:
                src = snapshot.entities_by_id.get(relationship.source_id)
                tgt = snapshot.entities_by_id.get(relationship.target_id)
                results.append({
                    "type": "relationship",
                    "id": relationship.id,
                    "label": relationship.label,
                    "source": {"id": relationship.source_id, "name": src.name if src else "?"},
                    "target": {"id": relationship.target_id, "name": tgt.name if tgt else "?"},
                    "description": (relationship.description or "")[:300],
                    "status": relationship.status,
                })
        elif ref_type == "system":
            system = next((item for item in snapshot.systems if item.id == ref_id), None)
            if not system:
                system = (
                    db.query(WorldSystem)
                    .filter(WorldSystem.id == ref_id, WorldSystem.novel_id == novel_id)
                    .first()
                )
            if system:
                results.append({
                    "type": "system",
                    "id": system.id,
                    "name": system.name,
                    "display_type": system.display_type,
                    "description": (system.description or "")[:300],
                    "status": system.status,
                })

    return json.dumps({"results": results}, ensure_ascii=False)
