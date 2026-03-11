from __future__ import annotations

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.world_crud import (
    WorldCrudDetailError,
    WorldCrudError,
    batch_confirm_entities,
    batch_confirm_relationships,
    batch_confirm_systems,
    batch_reject_entities,
    batch_reject_relationships,
    batch_reject_systems,
    create_attribute,
    create_entity,
    create_relationship,
    create_system,
    commit_world_change,
    delete_attribute,
    delete_entity,
    delete_relationship,
    delete_system,
    ensure_unique_relationship_write,
    load_attribute,
    load_novel,
    reorder_attributes,
    update_attribute,
    update_entity,
    update_relationship,
    update_system,
)
from app.database import Base
from app.models import Novel, WorldEntity, WorldEntityAttribute, WorldRelationship, WorldSystem


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def novel(db):
    novel = Novel(title="测试小说", author="测试", file_path="/tmp/test.txt", total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)
    return novel


@pytest.fixture
def entity_with_attribute(db, novel):
    entity = WorldEntity(novel_id=novel.id, name="云澈", entity_type="Character", aliases=[])
    db.add(entity)
    db.commit()
    db.refresh(entity)

    attribute = WorldEntityAttribute(entity_id=entity.id, key="修为", surface="真玄境")
    db.add(attribute)
    db.commit()
    db.refresh(attribute)
    return entity, attribute


@pytest.fixture
def relationship_rows(db, novel):
    source = WorldEntity(novel_id=novel.id, name="甲", entity_type="Character", aliases=[])
    target = WorldEntity(novel_id=novel.id, name="乙", entity_type="Character", aliases=[])
    db.add_all([source, target])
    db.commit()
    db.refresh(source)
    db.refresh(target)

    relationship = WorldRelationship(
        novel_id=novel.id,
        source_id=source.id,
        target_id=target.id,
        label="伴侣",
    )
    db.add(relationship)
    db.commit()
    db.refresh(relationship)
    return source, target, relationship


def _create_entity(db, novel, name: str, *, status: str = "draft", origin: str = "manual") -> WorldEntity:
    entity = WorldEntity(
        novel_id=novel.id,
        name=name,
        entity_type="Character",
        aliases=[],
        status=status,
        origin=origin,
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


def _create_relationship(
    db,
    novel,
    *,
    source: WorldEntity,
    target: WorldEntity,
    label: str,
    status: str = "draft",
) -> WorldRelationship:
    relationship = WorldRelationship(
        novel_id=novel.id,
        source_id=source.id,
        target_id=target.id,
        label=label,
        status=status,
    )
    db.add(relationship)
    db.commit()
    db.refresh(relationship)
    return relationship


def _create_system(db, novel, name: str, *, status: str = "draft") -> WorldSystem:
    system = WorldSystem(
        novel_id=novel.id,
        name=name,
        display_type="list",
        status=status,
    )
    db.add(system)
    db.commit()
    db.refresh(system)
    return system


def test_load_novel_raises_structured_not_found(db):
    with pytest.raises(WorldCrudError) as exc_info:
        load_novel(9999, db)

    assert exc_info.value.code == "novel_not_found"
    assert exc_info.value.status_code == 404


def test_load_attribute_is_scoped_to_parent_entity(db, novel, entity_with_attribute):
    _, attribute = entity_with_attribute
    other_entity = WorldEntity(novel_id=novel.id, name="千叶影儿", entity_type="Character", aliases=[])
    db.add(other_entity)
    db.commit()
    db.refresh(other_entity)

    with pytest.raises(WorldCrudError) as exc_info:
        load_attribute(other_entity.id, attribute.id, db)

    assert exc_info.value.code == "attribute_not_found"
    assert exc_info.value.status_code == 404


def test_ensure_unique_relationship_write_translates_conflict(db, relationship_rows):
    source, target, relationship = relationship_rows

    with pytest.raises(WorldCrudError) as exc_info:
        ensure_unique_relationship_write(
            db,
            novel_id=relationship.novel_id,
            source_id=source.id,
            target_id=target.id,
            label="伴侣关系",
        )

    assert exc_info.value.code == "relationship_conflict"
    assert exc_info.value.status_code == 409


def test_commit_world_change_rolls_back_and_raises_structured_conflict(db, novel):
    db.add(WorldEntity(novel_id=novel.id, name="云澈", entity_type="Character", aliases=[]))
    db.commit()

    db.add(WorldEntity(novel_id=novel.id, name="云澈", entity_type="Character", aliases=[]))
    with pytest.raises(WorldCrudError) as exc_info:
        commit_world_change(
            db,
            conflict_code="entity_name_conflict",
            conflict_message="Entity name conflict",
        )

    assert exc_info.value.code == "entity_name_conflict"
    assert exc_info.value.status_code == 409
    assert db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id).count() == 1


def test_create_entity_persists_manual_draft_row(db, novel):
    entity = create_entity(
        novel.id,
        {"name": "新实体", "entity_type": "Character", "aliases": ["别名"], "description": "desc"},
        db,
    )

    assert entity.novel_id == novel.id
    assert entity.origin == "manual"
    assert entity.status == "draft"
    assert entity.aliases == ["别名"]


def test_update_entity_promotes_worldpack_origin_to_manual(db, novel):
    entity = _create_entity(db, novel, "待更新实体")
    entity.origin = "worldpack"
    db.commit()

    updated = update_entity(novel.id, entity.id, {"description": "更新"}, db)

    assert updated.description == "更新"
    assert updated.origin == "manual"


def test_create_attribute_promotes_ai_draft_entity_origin(db, novel):
    entity = _create_entity(db, novel, "属性宿主", origin="bootstrap")

    attribute = create_attribute(novel.id, entity.id, {"key": "身份", "surface": "剑修"}, db)
    db.refresh(entity)

    assert attribute.key == "身份"
    assert entity.origin == "manual"


def test_update_attribute_promotes_attribute_and_entity_origins(db, novel, entity_with_attribute):
    entity, attribute = entity_with_attribute
    entity.origin = "worldgen"
    attribute.origin = "worldpack"
    db.commit()

    updated = update_attribute(novel.id, entity.id, attribute.id, {"surface": "更新值"}, db)
    db.refresh(entity)

    assert updated.surface == "更新值"
    assert updated.origin == "manual"
    assert entity.origin == "manual"


def test_create_relationship_persists_manual_draft_row(db, novel):
    source = _create_entity(db, novel, "关系甲")
    target = _create_entity(db, novel, "关系乙")

    relationship = create_relationship(
        novel.id,
        {"source_id": source.id, "target_id": target.id, "label": "同盟", "description": "desc"},
        db,
    )

    assert relationship.novel_id == novel.id
    assert relationship.origin == "manual"
    assert relationship.status == "draft"
    assert relationship.label == "同盟"


def test_update_relationship_promotes_worldpack_origin_to_manual(db, novel):
    source = _create_entity(db, novel, "源")
    target = _create_entity(db, novel, "目标")
    relationship = _create_relationship(db, novel, source=source, target=target, label="旧标签")
    relationship.origin = "worldpack"
    db.commit()

    updated = update_relationship(novel.id, relationship.id, {"label": "新标签"}, db)

    assert updated.label == "新标签"
    assert updated.origin == "manual"


def test_create_system_normalizes_payload(db, novel):
    system = create_system(
        novel.id,
        {
            "name": "称谓体系",
            "display_type": "list",
            "data": {"items": [{"id": "title_mushen", "label": "母神", "description": "x"}]},
            "constraints": [],
        },
        db,
    )

    assert system.origin == "manual"
    assert system.data["items"][0]["id"] == "title_mushen"


def test_update_system_promotes_origin_and_validates_payload(db, novel):
    system = _create_system(db, novel, "规则体系")
    system.origin = "worldpack"
    db.commit()

    updated = update_system(
        novel.id,
        system.id,
        {"data": {"items": [{"id": "rule_a", "label": "规则A", "description": "x"}]}},
        db,
    )

    assert updated.origin == "manual"
    assert updated.data["items"][0]["id"] == "rule_a"


def test_update_system_invalid_payload_raises_detail_error(db, novel):
    system = _create_system(db, novel, "坏数据体系")

    with pytest.raises(WorldCrudDetailError) as exc_info:
        update_system(
            novel.id,
            system.id,
            {"data": {"items": [{"label": "A", "visibility": "bogus"}]}},
            db,
        )

    assert exc_info.value.status_code == 422
    assert isinstance(exc_info.value.detail, list)


def test_delete_entity_commits_cascade_changes(db, novel):
    entity = _create_entity(db, novel, "待删除实体")
    attribute = WorldEntityAttribute(entity_id=entity.id, key="身份", surface="临时")
    db.add(attribute)
    db.commit()
    db.refresh(attribute)

    delete_entity(novel.id, entity.id, db)

    assert db.query(WorldEntity).filter(WorldEntity.id == entity.id).first() is None
    assert db.query(WorldEntityAttribute).filter(WorldEntityAttribute.id == attribute.id).first() is None


def test_delete_attribute_promotes_ai_draft_origin_before_delete(db, novel, entity_with_attribute):
    entity, attribute = entity_with_attribute
    entity.origin = "bootstrap"
    entity.status = "draft"
    db.commit()

    delete_attribute(novel.id, entity.id, attribute.id, db)
    db.refresh(entity)

    assert entity.origin == "manual"
    assert db.query(WorldEntityAttribute).filter(WorldEntityAttribute.id == attribute.id).first() is None


def test_delete_relationship_removes_row(db, novel):
    source = _create_entity(db, novel, "关系源")
    target = _create_entity(db, novel, "关系目标")
    relationship = _create_relationship(db, novel, source=source, target=target, label="盟友")

    delete_relationship(novel.id, relationship.id, db)

    assert db.query(WorldRelationship).filter(WorldRelationship.id == relationship.id).first() is None


def test_reorder_attributes_updates_sort_order_and_promotes_entity_origin(db, novel):
    entity = _create_entity(db, novel, "排序实体", origin="bootstrap")
    first = WorldEntityAttribute(entity_id=entity.id, key="A", surface="a", sort_order=0)
    second = WorldEntityAttribute(entity_id=entity.id, key="B", surface="b", sort_order=1)
    third = WorldEntityAttribute(entity_id=entity.id, key="C", surface="c", sort_order=2)
    db.add_all([first, second, third])
    db.commit()
    db.refresh(entity)
    db.refresh(first)
    db.refresh(second)
    db.refresh(third)

    reorder_attributes(novel.id, entity.id, [third.id, first.id, second.id], db)

    db.refresh(entity)
    reordered = (
        db.query(WorldEntityAttribute)
        .filter(WorldEntityAttribute.entity_id == entity.id)
        .order_by(WorldEntityAttribute.sort_order.asc(), WorldEntityAttribute.id.asc())
        .all()
    )
    assert entity.origin == "manual"
    assert [attribute.key for attribute in reordered] == ["C", "A", "B"]


def test_delete_system_removes_row(db, novel):
    system = _create_system(db, novel, "待删除体系")

    delete_system(novel.id, system.id, db)

    assert db.query(WorldSystem).filter(WorldSystem.id == system.id).first() is None


def test_batch_confirm_entities_only_updates_drafts(db, novel):
    draft = _create_entity(db, novel, "草稿实体", status="draft")
    confirmed = _create_entity(db, novel, "已确认实体", status="confirmed")

    count = batch_confirm_entities(novel.id, [draft.id, confirmed.id, 9999], db)
    db.refresh(draft)
    db.refresh(confirmed)

    assert count == 1
    assert draft.status == "confirmed"
    assert confirmed.status == "confirmed"


def test_batch_confirm_relationships_only_updates_drafts(db, novel):
    source = _create_entity(db, novel, "甲")
    target = _create_entity(db, novel, "乙")
    draft = _create_relationship(db, novel, source=source, target=target, label="草稿关系", status="draft")
    confirmed = _create_relationship(db, novel, source=target, target=source, label="已确认关系", status="confirmed")

    count = batch_confirm_relationships(novel.id, [draft.id, confirmed.id, 9999], db)
    db.refresh(draft)
    db.refresh(confirmed)

    assert count == 1
    assert draft.status == "confirmed"
    assert confirmed.status == "confirmed"


def test_batch_confirm_systems_only_updates_drafts(db, novel):
    draft = _create_system(db, novel, "草稿体系", status="draft")
    confirmed = _create_system(db, novel, "已确认体系", status="confirmed")

    count = batch_confirm_systems(novel.id, [draft.id, confirmed.id, 9999], db)
    db.refresh(draft)
    db.refresh(confirmed)

    assert count == 1
    assert draft.status == "confirmed"
    assert confirmed.status == "confirmed"


def test_batch_reject_entities_deletes_only_drafts(db, novel):
    draft = _create_entity(db, novel, "待拒绝实体", status="draft")
    confirmed = _create_entity(db, novel, "保留实体", status="confirmed")
    attribute = WorldEntityAttribute(entity_id=draft.id, key="身份", surface="草稿")
    db.add(attribute)
    db.commit()
    db.refresh(attribute)

    count = batch_reject_entities(novel.id, [draft.id, confirmed.id, 9999], db)

    assert count == 1
    assert db.query(WorldEntity).filter(WorldEntity.id == draft.id).first() is None
    assert db.query(WorldEntity).filter(WorldEntity.id == confirmed.id).first() is not None
    assert db.query(WorldEntityAttribute).filter(WorldEntityAttribute.id == attribute.id).first() is None


def test_batch_reject_relationships_deletes_only_drafts(db, novel):
    source = _create_entity(db, novel, "关系源A")
    target = _create_entity(db, novel, "关系目标B")
    draft = _create_relationship(db, novel, source=source, target=target, label="待拒绝关系", status="draft")
    confirmed = _create_relationship(db, novel, source=target, target=source, label="保留关系", status="confirmed")

    count = batch_reject_relationships(novel.id, [draft.id, confirmed.id, 9999], db)

    assert count == 1
    assert db.query(WorldRelationship).filter(WorldRelationship.id == draft.id).first() is None
    assert db.query(WorldRelationship).filter(WorldRelationship.id == confirmed.id).first() is not None


def test_batch_reject_systems_deletes_only_drafts(db, novel):
    draft = _create_system(db, novel, "待拒绝体系", status="draft")
    confirmed = _create_system(db, novel, "保留体系", status="confirmed")

    count = batch_reject_systems(novel.id, [draft.id, confirmed.id, 9999], db)

    assert count == 1
    assert db.query(WorldSystem).filter(WorldSystem.id == draft.id).first() is None
    assert db.query(WorldSystem).filter(WorldSystem.id == confirmed.id).first() is not None
