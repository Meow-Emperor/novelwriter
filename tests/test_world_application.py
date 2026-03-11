from __future__ import annotations

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core import world_application
from app.database import Base
from app.models import Novel, WorldEntity, WorldSystem


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


def _create_entity(db, novel, name: str, *, status: str = "draft") -> WorldEntity:
    entity = WorldEntity(
        novel_id=novel.id,
        name=name,
        entity_type="Character",
        aliases=[],
        status=status,
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


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


def test_create_entity_records_world_edit_event(db, novel, monkeypatch):
    recorded: list[dict] = []

    monkeypatch.setattr(
        world_application,
        "record_event",
        lambda db, user_id, event, novel_id=None, meta=None: recorded.append(
            {"user_id": user_id, "event": event, "novel_id": novel_id, "meta": meta}
        ),
    )

    entity = world_application.create_entity(
        novel.id,
        {"name": "云澈", "entity_type": "Character"},
        user_id=7,
        db=db,
    )

    assert entity.id is not None
    assert recorded == [
        {
            "user_id": 7,
            "event": "world_edit",
            "novel_id": novel.id,
            "meta": {"action": "create_entity"},
        }
    ]


def test_batch_confirm_entities_records_draft_confirm_event(db, novel, monkeypatch):
    draft = _create_entity(db, novel, "待确认")
    _create_entity(db, novel, "已确认", status="confirmed")
    recorded: list[dict] = []

    monkeypatch.setattr(
        world_application,
        "record_event",
        lambda db, user_id, event, novel_id=None, meta=None: recorded.append(
            {"user_id": user_id, "event": event, "novel_id": novel_id, "meta": meta}
        ),
    )

    count = world_application.batch_confirm_entities(novel.id, [draft.id, 9999], user_id=9, db=db)
    db.refresh(draft)

    assert count == 1
    assert draft.status == "confirmed"
    assert recorded == [
        {
            "user_id": 9,
            "event": "draft_confirm",
            "novel_id": novel.id,
            "meta": {"type": "entity", "count": 1},
        }
    ]


def test_batch_reject_systems_records_draft_reject_event(db, novel, monkeypatch):
    draft = _create_system(db, novel, "待拒绝")
    kept = _create_system(db, novel, "保留体系", status="confirmed")
    recorded: list[dict] = []

    monkeypatch.setattr(
        world_application,
        "record_event",
        lambda db, user_id, event, novel_id=None, meta=None: recorded.append(
            {"user_id": user_id, "event": event, "novel_id": novel_id, "meta": meta}
        ),
    )

    count = world_application.batch_reject_systems(novel.id, [draft.id, kept.id], user_id=11, db=db)

    assert count == 1
    assert db.query(WorldSystem).filter(WorldSystem.id == draft.id).first() is None
    assert db.query(WorldSystem).filter(WorldSystem.id == kept.id).first() is not None
    assert recorded == [
        {
            "user_id": 11,
            "event": "draft_reject",
            "novel_id": novel.id,
            "meta": {"type": "system", "count": 1},
        }
    ]


def test_delete_entity_does_not_record_event(db, novel, monkeypatch):
    entity = _create_entity(db, novel, "临时角色")
    recorded: list[dict] = []

    monkeypatch.setattr(
        world_application,
        "record_event",
        lambda *args, **kwargs: recorded.append({"args": args, "kwargs": kwargs}),
    )

    world_application.delete_entity(novel.id, entity.id, db=db)

    assert db.query(WorldEntity).filter(WorldEntity.id == entity.id).first() is None
    assert recorded == []
