# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Application-level orchestration for world-model CRUD use cases."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from sqlalchemy.orm import Session

from app.core.events import record_event
from app.core import world_crud
from app.models import WorldEntity, WorldEntityAttribute, WorldRelationship, WorldSystem


def create_entity(novel_id: int, data: Mapping[str, Any], *, user_id: int, db: Session) -> WorldEntity:
    entity = world_crud.create_entity(novel_id, data, db)
    _record_world_edit(db, user_id=user_id, novel_id=novel_id, action="create_entity")
    return entity


def update_entity(
    novel_id: int,
    entity_id: int,
    data: Mapping[str, Any],
    *,
    user_id: int,
    db: Session,
) -> WorldEntity:
    entity = world_crud.update_entity(novel_id, entity_id, data, db)
    _record_world_edit(db, user_id=user_id, novel_id=novel_id, action="update_entity")
    return entity


def delete_entity(novel_id: int, entity_id: int, *, db: Session) -> None:
    world_crud.delete_entity(novel_id, entity_id, db)


def batch_confirm_entities(novel_id: int, ids: Sequence[int], *, user_id: int, db: Session) -> int:
    count = world_crud.batch_confirm_entities(novel_id, ids, db)
    _record_draft_event(db, user_id=user_id, novel_id=novel_id, event="draft_confirm", row_type="entity", count=count)
    return count


def batch_reject_entities(novel_id: int, ids: Sequence[int], *, user_id: int, db: Session) -> int:
    count = world_crud.batch_reject_entities(novel_id, ids, db)
    _record_draft_event(db, user_id=user_id, novel_id=novel_id, event="draft_reject", row_type="entity", count=count)
    return count


def create_attribute(
    novel_id: int,
    entity_id: int,
    data: Mapping[str, Any],
    *,
    db: Session,
) -> WorldEntityAttribute:
    return world_crud.create_attribute(novel_id, entity_id, data, db)


def update_attribute(
    novel_id: int,
    entity_id: int,
    attribute_id: int,
    data: Mapping[str, Any],
    *,
    db: Session,
) -> WorldEntityAttribute:
    return world_crud.update_attribute(novel_id, entity_id, attribute_id, data, db)


def delete_attribute(novel_id: int, entity_id: int, attribute_id: int, *, db: Session) -> None:
    world_crud.delete_attribute(novel_id, entity_id, attribute_id, db)


def reorder_attributes(novel_id: int, entity_id: int, order: Sequence[int], *, db: Session) -> None:
    world_crud.reorder_attributes(novel_id, entity_id, order, db)


def create_relationship(
    novel_id: int,
    data: Mapping[str, Any],
    *,
    user_id: int,
    db: Session,
) -> WorldRelationship:
    relationship = world_crud.create_relationship(novel_id, data, db)
    _record_world_edit(db, user_id=user_id, novel_id=novel_id, action="create_relationship")
    return relationship


def update_relationship(
    novel_id: int,
    relationship_id: int,
    data: Mapping[str, Any],
    *,
    user_id: int,
    db: Session,
) -> WorldRelationship:
    relationship = world_crud.update_relationship(novel_id, relationship_id, data, db)
    _record_world_edit(db, user_id=user_id, novel_id=novel_id, action="update_relationship")
    return relationship


def delete_relationship(novel_id: int, relationship_id: int, *, db: Session) -> None:
    world_crud.delete_relationship(novel_id, relationship_id, db)


def batch_confirm_relationships(novel_id: int, ids: Sequence[int], *, user_id: int, db: Session) -> int:
    count = world_crud.batch_confirm_relationships(novel_id, ids, db)
    _record_draft_event(
        db,
        user_id=user_id,
        novel_id=novel_id,
        event="draft_confirm",
        row_type="relationship",
        count=count,
    )
    return count


def batch_reject_relationships(novel_id: int, ids: Sequence[int], *, user_id: int, db: Session) -> int:
    count = world_crud.batch_reject_relationships(novel_id, ids, db)
    _record_draft_event(
        db,
        user_id=user_id,
        novel_id=novel_id,
        event="draft_reject",
        row_type="relationship",
        count=count,
    )
    return count


def create_system(
    novel_id: int,
    data: Mapping[str, Any],
    *,
    user_id: int,
    db: Session,
) -> WorldSystem:
    system = world_crud.create_system(novel_id, data, db)
    _record_world_edit(db, user_id=user_id, novel_id=novel_id, action="create_system")
    return system


def update_system(
    novel_id: int,
    system_id: int,
    data: Mapping[str, Any],
    *,
    user_id: int,
    db: Session,
) -> WorldSystem:
    system = world_crud.update_system(novel_id, system_id, data, db)
    _record_world_edit(db, user_id=user_id, novel_id=novel_id, action="update_system")
    return system


def delete_system(novel_id: int, system_id: int, *, db: Session) -> None:
    world_crud.delete_system(novel_id, system_id, db)


def batch_confirm_systems(novel_id: int, ids: Sequence[int], *, user_id: int, db: Session) -> int:
    count = world_crud.batch_confirm_systems(novel_id, ids, db)
    _record_draft_event(db, user_id=user_id, novel_id=novel_id, event="draft_confirm", row_type="system", count=count)
    return count


def batch_reject_systems(novel_id: int, ids: Sequence[int], *, user_id: int, db: Session) -> int:
    count = world_crud.batch_reject_systems(novel_id, ids, db)
    _record_draft_event(db, user_id=user_id, novel_id=novel_id, event="draft_reject", row_type="system", count=count)
    return count


def _record_world_edit(db: Session, *, user_id: int, novel_id: int, action: str) -> None:
    record_event(db, user_id, "world_edit", novel_id=novel_id, meta={"action": action})


def _record_draft_event(
    db: Session,
    *,
    user_id: int,
    novel_id: int,
    event: str,
    row_type: str,
    count: int,
) -> None:
    record_event(db, user_id, event, novel_id=novel_id, meta={"type": row_type, "count": count})
