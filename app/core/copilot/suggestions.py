# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Suggestion compilation and dismissal helpers for copilot."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.copilot.messages import CopilotTextKey, get_copilot_text
from app.core.copilot.scope import EvidenceItem, ScopeSnapshot
from app.models import CopilotRun, WorldEntity

logger = logging.getLogger(__name__)

MAX_COMPILED_SUGGESTIONS = 20

_RESOURCE_TEXT_KEYS: dict[str, CopilotTextKey] = {
    "entity": CopilotTextKey.TEXT_RESOURCE_ENTITY,
    "relationship": CopilotTextKey.TEXT_RESOURCE_RELATIONSHIP,
    "system": CopilotTextKey.TEXT_RESOURCE_SYSTEM,
}

_FIELD_TEXT_KEYS: dict[str, CopilotTextKey] = {
    "name": CopilotTextKey.TEXT_FIELD_NAME,
    "entity_type": CopilotTextKey.TEXT_FIELD_ENTITY_TYPE,
    "description": CopilotTextKey.TEXT_FIELD_DESCRIPTION,
    "aliases": CopilotTextKey.TEXT_FIELD_ALIASES,
    "label": CopilotTextKey.TEXT_FIELD_RELATIONSHIP_LABEL,
    "visibility": CopilotTextKey.TEXT_FIELD_VISIBILITY,
    "constraints": CopilotTextKey.TEXT_FIELD_CONSTRAINTS,
    "display_type": CopilotTextKey.TEXT_FIELD_DISPLAY_TYPE,
}


def _suggestion_text(
    interaction_locale: str,
    text_key: CopilotTextKey,
    **params: object,
) -> str:
    return get_copilot_text(text_key, locale=interaction_locale, **params)


def _resource_label(resource: str, interaction_locale: str) -> str:
    key = _RESOURCE_TEXT_KEYS.get(resource)
    if key is None:
        return resource
    return _suggestion_text(interaction_locale, key)


@dataclass
class CompiledSuggestion:
    suggestion_id: str
    kind: str
    title: str
    summary: str
    evidence_ids: list[str]
    target: dict[str, Any]
    preview: dict[str, Any]
    apply_action: dict[str, Any] | None
    status: str = "pending"


def _normalize_entity_name_key(name: str | None) -> str:
    return (name or "").strip().casefold()


def _find_existing_entity_by_name_or_alias(
    name: str | None,
    snapshot: ScopeSnapshot,
) -> WorldEntity | None:
    key = _normalize_entity_name_key(name)
    if not key:
        return None

    matches: list[WorldEntity] = []
    seen_ids: set[int] = set()
    for entity in snapshot.entities:
        candidate_keys = [_normalize_entity_name_key(entity.name)]
        candidate_keys.extend(_normalize_entity_name_key(alias) for alias in (entity.aliases or []))
        if key not in candidate_keys:
            continue
        if entity.id in seen_ids:
            continue
        seen_ids.add(entity.id)
        matches.append(entity)

    return matches[0] if len(matches) == 1 else None


def _build_entity_suggestion_candidates(
    raw_suggestions: list[dict[str, Any]],
    suggestion_ids: list[str],
) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for raw, suggestion_id in zip(raw_suggestions, suggestion_ids):
        if raw.get("kind") != "create_entity":
            continue
        delta = raw.get("delta") or {}
        name = str(delta.get("name") or "").strip()
        key = _normalize_entity_name_key(name)
        if not key:
            continue
        candidates[key] = {
            "suggestion_id": suggestion_id,
            "name": name,
            "entity_type": delta.get("entity_type", "Other"),
        }
    return candidates


def _expand_relationship_entity_dependencies(
    raw_suggestions: list[dict[str, Any]],
    snapshot: ScopeSnapshot,
    interaction_locale: str,
) -> list[dict[str, Any]]:
    """Synthesize missing create_entity suggestions for relationship endpoints."""
    expanded: list[dict[str, Any]] = []
    known_candidate_keys = {
        _normalize_entity_name_key(str((raw.get("delta") or {}).get("name") or ""))
        for raw in raw_suggestions
        if raw.get("kind") == "create_entity"
    }
    synthesized_keys: set[str] = set()

    for raw in raw_suggestions:
        if raw.get("kind") == "create_relationship" and raw.get("target_resource", "relationship") == "relationship":
            delta = raw.get("delta") or {}
            for endpoint in ("source", "target"):
                endpoint_id = delta.get(f"{endpoint}_id")
                if isinstance(endpoint_id, int) and endpoint_id in snapshot.entities_by_id:
                    continue

                endpoint_name = str(delta.get(f"{endpoint}_name") or "").strip()
                key = _normalize_entity_name_key(endpoint_name)
                if not key:
                    continue
                if key in known_candidate_keys or key in synthesized_keys:
                    continue
                if _find_existing_entity_by_name_or_alias(endpoint_name, snapshot) is not None:
                    continue

                endpoint_type = str(delta.get(f"{endpoint}_entity_type") or "Other").strip() or "Other"
                expanded.append({
                    "kind": "create_entity",
                    "title": _suggestion_text(
                        interaction_locale,
                        CopilotTextKey.SUGGESTION_SYNTH_ENTITY_TITLE,
                        entity_name=endpoint_name,
                    ),
                    "summary": _suggestion_text(
                        interaction_locale,
                        CopilotTextKey.SUGGESTION_SYNTH_ENTITY_SUMMARY,
                        entity_name=endpoint_name,
                    ),
                    "target_resource": "entity",
                    "target_id": None,
                    "cited_evidence_indices": list(raw.get("cited_evidence_indices") or []),
                    "delta": {
                        "name": endpoint_name,
                        "entity_type": endpoint_type,
                    },
                })
                synthesized_keys.add(key)
                known_candidate_keys.add(key)

        expanded.append(raw)

    return expanded


def compile_suggestions(
    raw_suggestions: list[dict[str, Any]],
    evidence: list[EvidenceItem],
    snapshot: ScopeSnapshot,
    mode: str,
    scenario: str,
    interaction_locale: str = "zh",
) -> list[CompiledSuggestion]:
    """Backend-compile model-drafted suggestions into validated actionable cards."""
    limited_raw_suggestions = raw_suggestions[:MAX_COMPILED_SUGGESTIONS]
    expanded_raw_suggestions = _expand_relationship_entity_dependencies(
        limited_raw_suggestions,
        snapshot,
        interaction_locale,
    )
    suggestion_ids = [f"sg_{i}_{uuid.uuid4().hex[:8]}" for i, _ in enumerate(expanded_raw_suggestions)]
    entity_candidates = _build_entity_suggestion_candidates(expanded_raw_suggestions, suggestion_ids)
    compiled: list[CompiledSuggestion] = []
    for index, raw in enumerate(expanded_raw_suggestions):
        try:
            suggestion = _compile_one(
                raw,
                index,
                suggestion_ids[index],
                evidence,
                snapshot,
                mode,
                scenario,
                entity_candidates,
                interaction_locale,
            )
            compiled.append(suggestion)
        except Exception:
            logger.debug("Failed to compile suggestion %d", index, exc_info=True)
    return compiled


def _compile_one(
    raw: dict[str, Any],
    index: int,
    suggestion_id: str,
    evidence: list[EvidenceItem],
    snapshot: ScopeSnapshot,
    mode: str,
    scenario: str,
    entity_candidates: dict[str, dict[str, Any]],
    interaction_locale: str,
) -> CompiledSuggestion:
    kind = raw.get("kind", "")
    title = raw.get(
        "title",
        _suggestion_text(
            interaction_locale,
            CopilotTextKey.SUGGESTION_FALLBACK_TITLE,
            index=index + 1,
        ),
    )
    summary = raw.get("summary", "")
    target_resource = raw.get("target_resource", "entity")
    is_draft_governance = (
        snapshot.profile == "draft_governance"
        or mode == "draft_cleanup"
        or scenario == "draft_cleanup"
    )
    target_id = raw.get("target_id")
    if isinstance(target_id, str):
        try:
            target_id = int(target_id)
        except (ValueError, TypeError):
            target_id = None
    delta = raw.get("delta") or {}

    cited = raw.get("cited_evidence_indices", [])
    evidence_ids = [evidence[idx].evidence_id for idx in cited if isinstance(idx, int) and 0 <= idx < len(evidence)]
    evidence_quotes = [evidence[idx].excerpt[:200] for idx in cited if isinstance(idx, int) and 0 <= idx < len(evidence)][:3]

    actionable = True
    apply_action = None
    target_label = ""
    non_actionable_reason: str | None = None

    if kind.startswith("update_"):
        resolved = _resolve_target(target_resource, target_id, snapshot)
        if resolved is None:
            actionable = False
            target_label = str(target_id or "?")
            non_actionable_reason = _suggestion_text(interaction_locale, CopilotTextKey.SUGGESTION_REASON_STALE)
        else:
            target_id = resolved["id"]
            target_label = resolved["label"]
            if is_draft_governance and not resolved.get("is_draft", False):
                actionable = False
                non_actionable_reason = _suggestion_text(
                    interaction_locale,
                    CopilotTextKey.SUGGESTION_REASON_DRAFT_ONLY,
                )
            else:
                apply_action = _build_update_action(kind, delta, target_resource, target_id, snapshot, mode)
                if apply_action is None:
                    actionable = False
                    non_actionable_reason = _suggestion_text(
                        interaction_locale,
                        CopilotTextKey.SUGGESTION_REASON_CANNOT_APPLY_DIRECT,
                    )

    elif kind.startswith("create_"):
        if is_draft_governance:
            actionable = False
            non_actionable_reason = _suggestion_text(
                interaction_locale,
                CopilotTextKey.SUGGESTION_REASON_DRAFT_CREATE_DISALLOWED,
            )
        else:
            target_id = None
            target_label = (
                delta.get("name", "")
                or delta.get("label", "")
                or _build_new_resource_label(target_resource, interaction_locale)
            )
            apply_action = _build_create_action(kind, delta, target_resource, snapshot, entity_candidates)
            if apply_action is None:
                actionable = False
                non_actionable_reason = _build_non_actionable_create_reason(
                    kind,
                    delta,
                    target_resource,
                    snapshot,
                    entity_candidates,
                    interaction_locale,
                )
    else:
        actionable = False
        target_label = str(target_id or "?")
        non_actionable_reason = _suggestion_text(
            interaction_locale,
            CopilotTextKey.SUGGESTION_REASON_NOT_DIRECTLY_APPLICABLE,
        )

    field_deltas = _build_field_deltas(
        kind,
        delta,
        target_id,
        target_resource,
        snapshot,
        interaction_locale,
    )
    preview = {
        "target_label": target_label or _build_new_resource_label(target_resource, interaction_locale),
        "summary": summary,
        "field_deltas": field_deltas,
        "evidence_quotes": evidence_quotes,
        "actionable": actionable,
        "non_actionable_reason": non_actionable_reason,
    }

    target_tab = _resource_to_tab(
        target_resource,
        "draft_governance" if is_draft_governance else snapshot.profile,
    )
    target_dict: dict[str, Any] = {
        "resource": target_resource,
        "resource_id": target_id,
        "label": target_label or "",
        "tab": target_tab,
    }
    if target_resource == "entity":
        target_dict["entity_id"] = target_id
    elif target_resource == "relationship":
        if target_id:
            target_dict["highlight_id"] = target_id
            for relationship in snapshot.relationships:
                if relationship.id == target_id:
                    target_dict["entity_id"] = relationship.source_id
                    break
        elif isinstance(delta.get("source_id"), int):
            target_dict["entity_id"] = delta["source_id"]
        elif isinstance(delta.get("target_id"), int):
            target_dict["entity_id"] = delta["target_id"]
        elif isinstance(snapshot.focus_entity_id, int):
            target_dict["entity_id"] = snapshot.focus_entity_id
    if is_draft_governance:
        target_dict["tab"] = "review"
        target_dict["review_kind"] = _resource_to_review_kind(target_resource)
        if target_id:
            target_dict["highlight_id"] = target_id

    return CompiledSuggestion(
        suggestion_id=suggestion_id,
        kind=kind,
        title=title,
        summary=summary,
        evidence_ids=evidence_ids,
        target=target_dict,
        preview=preview,
        apply_action=apply_action,
    )


def _resource_to_tab(resource: str, profile: str) -> str:
    if profile == "draft_governance":
        return "review"
    return {"entity": "entities", "relationship": "relationships", "system": "systems"}.get(resource, "entities")


def _build_new_resource_label(resource: str, interaction_locale: str) -> str:
    return _suggestion_text(
        interaction_locale,
        CopilotTextKey.TEXT_NEW_RESOURCE,
        resource_label=_resource_label(resource, interaction_locale),
    )


def _resource_to_review_kind(resource: str) -> str:
    return {"entity": "entities", "relationship": "relationships", "system": "systems"}.get(resource, "entities")


def _resolve_target(resource: str, target_id: int | None, snapshot: ScopeSnapshot) -> dict[str, Any] | None:
    if target_id is None:
        return None
    if resource == "entity":
        entity = snapshot.entities_by_id.get(target_id)
        if entity:
            return {"id": entity.id, "label": entity.name, "is_draft": entity.status == "draft"}
    elif resource == "relationship":
        for relationship in snapshot.relationships:
            if relationship.id == target_id:
                source = snapshot.entities_by_id.get(relationship.source_id)
                target = snapshot.entities_by_id.get(relationship.target_id)
                label = f"{source.name if source else '?'} ↔ {target.name if target else '?'}"
                return {"id": relationship.id, "label": label, "is_draft": relationship.status == "draft"}
    elif resource == "system":
        for system in snapshot.systems:
            if system.id == target_id:
                return {"id": system.id, "label": system.name, "is_draft": system.status == "draft"}
    return None


_ENTITY_UPDATE_FIELDS = {"name", "entity_type", "description", "aliases"}
_RELATIONSHIP_UPDATE_FIELDS = {"label", "description", "visibility"}
_SYSTEM_UPDATE_FIELDS = {"name", "description", "constraints", "display_type"}
_DRAFT_ENTITY_UPDATE_FIELDS = {"name", "entity_type", "description", "aliases"}
_DRAFT_REL_UPDATE_FIELDS = {"label", "description", "visibility"}
_DRAFT_SYSTEM_UPDATE_FIELDS = {"name", "description", "constraints"}


def _build_update_action(
    kind: str,
    delta: dict[str, Any],
    target_resource: str,
    target_id: int,
    snapshot: ScopeSnapshot,
    mode: str,
) -> dict[str, Any] | None:
    is_draft_governance = snapshot.profile == "draft_governance" or mode == "draft_cleanup"
    if target_resource == "entity":
        allowed = _DRAFT_ENTITY_UPDATE_FIELDS if is_draft_governance else _ENTITY_UPDATE_FIELDS
        data = {k: v for k, v in delta.items() if k in allowed and v is not None}
        attr_actions = _compile_attribute_actions(delta.get("attributes", []), target_id, snapshot)
        if not data and not attr_actions:
            return None
        action: dict[str, Any] = {"type": "update_entity", "entity_id": target_id, "data": data}
        if attr_actions:
            action["attribute_actions"] = attr_actions
        return action

    if target_resource == "relationship":
        allowed = _DRAFT_REL_UPDATE_FIELDS if is_draft_governance else _RELATIONSHIP_UPDATE_FIELDS
        data = {k: v for k, v in delta.items() if k in allowed and v is not None}
        return {"type": "update_relationship", "relationship_id": target_id, "data": data} if data else None

    if target_resource == "system":
        allowed = _DRAFT_SYSTEM_UPDATE_FIELDS if is_draft_governance else _SYSTEM_UPDATE_FIELDS
        data = {k: v for k, v in delta.items() if k in allowed and v is not None}
        return {"type": "update_system", "system_id": target_id, "data": data} if data else None

    return None


def _compile_attribute_actions(
    raw_attrs: list[dict[str, Any]],
    entity_id: int,
    snapshot: ScopeSnapshot,
) -> list[dict[str, Any]]:
    if not raw_attrs:
        return []
    existing_attrs = snapshot.attributes_by_entity.get(entity_id, [])
    existing_by_key = {attr.key: attr for attr in existing_attrs}
    actions: list[dict[str, Any]] = []
    for raw_attr in raw_attrs:
        key = raw_attr.get("key")
        surface = raw_attr.get("surface")
        if not key or not surface:
            continue
        if key in existing_by_key:
            attr = existing_by_key[key]
            if attr.surface != surface:
                actions.append({
                    "type": "update_attribute",
                    "entity_id": entity_id,
                    "attribute_id": attr.id,
                    "data": {"surface": surface},
                })
        else:
            actions.append({
                "type": "create_attribute",
                "entity_id": entity_id,
                "data": {"key": key, "surface": surface},
            })
    return actions


def _resolve_relationship_endpoint_reference(
    *,
    endpoint_id: Any,
    endpoint_name: Any,
    snapshot: ScopeSnapshot,
    entity_candidates: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if isinstance(endpoint_id, int) and endpoint_id in snapshot.entities_by_id:
        entity = snapshot.entities_by_id[endpoint_id]
        return {"kind": "existing", "entity_id": entity.id, "label": entity.name}

    name = str(endpoint_name or "").strip()
    if not name:
        return None

    existing_entity = _find_existing_entity_by_name_or_alias(name, snapshot)
    if existing_entity is not None:
        return {"kind": "existing", "entity_id": existing_entity.id, "label": existing_entity.name}

    candidate = entity_candidates.get(_normalize_entity_name_key(name))
    if candidate is not None:
        return {
            "kind": "suggestion",
            "suggestion_id": candidate["suggestion_id"],
            "entity_name": candidate["name"],
        }
    return None


def _build_create_action(
    kind: str,
    delta: dict[str, Any],
    target_resource: str,
    snapshot: ScopeSnapshot,
    entity_candidates: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if target_resource == "entity":
        name = delta.get("name")
        if not name:
            return None
        for entity in snapshot.entities:
            if entity.name == name:
                return None
        data: dict[str, Any] = {"name": name, "entity_type": delta.get("entity_type", "Other")}
        if delta.get("description"):
            data["description"] = delta["description"]
        if delta.get("aliases"):
            data["aliases"] = delta["aliases"]
        action: dict[str, Any] = {"type": "create_entity", "data": data}
        attrs = delta.get("attributes", [])
        if attrs:
            action["deferred_attribute_actions"] = [
                {"type": "create_attribute", "data": {"key": attr["key"], "surface": attr["surface"]}}
                for attr in attrs if attr.get("key") and attr.get("surface")
            ]
        return action

    if target_resource == "relationship":
        source_id = delta.get("source_id")
        target_id = delta.get("target_id")
        source_name = delta.get("source_name")
        target_name = delta.get("target_name")
        label = delta.get("label")
        if not label:
            return None
        source_ref = _resolve_relationship_endpoint_reference(
            endpoint_id=source_id,
            endpoint_name=source_name,
            snapshot=snapshot,
            entity_candidates=entity_candidates,
        )
        target_ref = _resolve_relationship_endpoint_reference(
            endpoint_id=target_id,
            endpoint_name=target_name,
            snapshot=snapshot,
            entity_candidates=entity_candidates,
        )
        if source_ref is None or target_ref is None:
            return None
        data = {"label": label}
        if delta.get("description"):
            data["description"] = delta["description"]
        if source_ref["kind"] == "existing":
            data["source_id"] = source_ref["entity_id"]
        if target_ref["kind"] == "existing":
            data["target_id"] = target_ref["entity_id"]
        action: dict[str, Any] = {"type": "create_relationship", "data": data}
        if source_ref["kind"] != "existing" or target_ref["kind"] != "existing":
            action["endpoint_dependencies"] = {
                "source": source_ref,
                "target": target_ref,
            }
        return action

    if target_resource == "system":
        name = delta.get("name")
        if not name:
            return None
        for system in snapshot.systems:
            if system.name == name:
                return None
        data = {"name": name, "display_type": delta.get("display_type", "list")}
        if delta.get("description"):
            data["description"] = delta["description"]
        if delta.get("constraints"):
            data["constraints"] = delta["constraints"]
        return {"type": "create_system", "data": data}

    return None


def _build_non_actionable_create_reason(
    kind: str,
    delta: dict[str, Any],
    target_resource: str,
    snapshot: ScopeSnapshot,
    entity_candidates: dict[str, dict[str, Any]],
    interaction_locale: str,
) -> str:
    if target_resource == "entity":
        if not delta.get("name"):
            return _suggestion_text(
                interaction_locale,
                CopilotTextKey.SUGGESTION_CREATE_REASON_ENTITY_INCOMPLETE,
            )
        return _suggestion_text(
            interaction_locale,
            CopilotTextKey.SUGGESTION_CREATE_REASON_ENTITY_NAME_COLLISION,
        )

    if target_resource == "relationship":
        source_id = delta.get("source_id")
        target_id = delta.get("target_id")
        source_name = str(delta.get("source_name") or "").strip()
        target_name = str(delta.get("target_name") or "").strip()
        label = delta.get("label")
        if not label:
            return _suggestion_text(
                interaction_locale,
                CopilotTextKey.SUGGESTION_CREATE_REASON_RELATIONSHIP_INCOMPLETE,
            )
        if not any([isinstance(source_id, int), source_name]) or not any([isinstance(target_id, int), target_name]):
            return _suggestion_text(
                interaction_locale,
                CopilotTextKey.SUGGESTION_CREATE_REASON_RELATIONSHIP_INCOMPLETE,
            )

        source_ref = _resolve_relationship_endpoint_reference(
            endpoint_id=source_id,
            endpoint_name=source_name,
            snapshot=snapshot,
            entity_candidates=entity_candidates,
        )
        target_ref = _resolve_relationship_endpoint_reference(
            endpoint_id=target_id,
            endpoint_name=target_name,
            snapshot=snapshot,
            entity_candidates=entity_candidates,
        )
        if source_ref is None or target_ref is None:
            return _suggestion_text(
                interaction_locale,
                CopilotTextKey.SUGGESTION_CREATE_REASON_RELATIONSHIP_DEPENDENCY,
            )
        return _suggestion_text(
            interaction_locale,
            CopilotTextKey.SUGGESTION_CREATE_REASON_RELATIONSHIP_CONFLICT,
        )

    if target_resource == "system":
        if not delta.get("name"):
            return _suggestion_text(
                interaction_locale,
                CopilotTextKey.SUGGESTION_CREATE_REASON_SYSTEM_INCOMPLETE,
            )
        return _suggestion_text(
            interaction_locale,
            CopilotTextKey.SUGGESTION_CREATE_REASON_SYSTEM_NAME_COLLISION,
        )

    return _suggestion_text(
        interaction_locale,
        CopilotTextKey.SUGGESTION_REASON_CANNOT_APPLY_DIRECT,
    )

_RELATIONSHIP_METADATA_FIELDS = {
    "source_id",
    "target_id",
    "source_name",
    "target_name",
    "source_entity_type",
    "target_entity_type",
    "attributes",
}


def _build_field_deltas(
    kind: str,
    delta: dict[str, Any],
    target_id: int | None,
    target_resource: str,
    snapshot: ScopeSnapshot,
    interaction_locale: str,
) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    if target_id and target_resource == "entity":
        entity = snapshot.entities_by_id.get(target_id)
        if entity:
            current = {
                "name": entity.name,
                "entity_type": entity.entity_type,
                "description": entity.description or "",
                "aliases": ", ".join(entity.aliases) if entity.aliases else "",
            }
    elif target_id and target_resource == "relationship":
        for relationship in snapshot.relationships:
            if relationship.id == target_id:
                current = {
                    "label": relationship.label,
                    "description": relationship.description or "",
                    "visibility": relationship.visibility,
                }
                break
    elif target_id and target_resource == "system":
        for system in snapshot.systems:
            if system.id == target_id:
                current = {
                    "name": system.name,
                    "description": system.description or "",
                    "constraints": "; ".join(str(value) for value in (system.constraints or [])),
                }
                break

    for field_key, value in delta.items():
        if value is None or field_key in _RELATIONSHIP_METADATA_FIELDS:
            continue
        field_text_key = _FIELD_TEXT_KEYS.get(field_key)
        label = (
            _suggestion_text(interaction_locale, field_text_key)
            if field_text_key is not None
            else field_key
        )
        before = current.get(field_key)
        after = ", ".join(value) if isinstance(value, list) else str(value) if value else ""
        if isinstance(before, list):
            before = ", ".join(str(item) for item in before)
        deltas.append({
            "field": field_key,
            "label": label,
            "before": str(before) if before else None,
            "after": after,
        })

    for attr in delta.get("attributes", []):
        key = attr.get("key", "")
        surface = attr.get("surface", "")
        if key and surface:
            existing_attrs = snapshot.attributes_by_entity.get(target_id or 0, [])
            existing = next((item for item in existing_attrs if item.key == key), None)
            deltas.append({
                "field": f"attribute:{key}",
                "label": _suggestion_text(
                    interaction_locale,
                    CopilotTextKey.TEXT_ATTRIBUTE_FIELD_LABEL,
                    key=key,
                ),
                "before": existing.surface if existing else None,
                "after": surface,
            })
    return deltas


def _serialize_compiled(suggestion: CompiledSuggestion) -> dict[str, Any]:
    return {
        "suggestion_id": suggestion.suggestion_id,
        "kind": suggestion.kind,
        "title": suggestion.title,
        "summary": suggestion.summary,
        "evidence_ids": suggestion.evidence_ids,
        "target": suggestion.target,
        "preview": suggestion.preview,
        "apply": suggestion.apply_action,
        "status": suggestion.status,
    }


def serialize_compiled_suggestions(
    suggestions: list[CompiledSuggestion],
) -> list[dict[str, Any]]:
    return [_serialize_compiled(suggestion) for suggestion in suggestions]


def dismiss_suggestions(db: Session, run: CopilotRun, suggestion_ids: list[str]) -> None:
    """Mark suggestions as dismissed (no world-model mutation)."""
    from sqlalchemy.orm.attributes import flag_modified

    suggestions_by_id = {suggestion["suggestion_id"]: suggestion for suggestion in (run.suggestions_json or [])}
    changed = False
    for suggestion_id in suggestion_ids:
        suggestion = suggestions_by_id.get(suggestion_id)
        if suggestion and suggestion.get("status") == "pending":
            suggestion["status"] = "dismissed"
            changed = True
    if changed:
        flag_modified(run, "suggestions_json")
        db.commit()
