from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.core.world_write import (
    InvalidSystemDisplayTypeError,
    RelationshipConflictError,
    build_relationship_signature,
    ensure_relationship_is_unique,
    is_worldpack_controlled_by_pack,
    is_worldpack_origin,
    normalize_system_data_for_write,
    promote_ai_draft_origin_to_manual,
    promote_worldpack_origin_to_manual,
    relationship_signature_from_row,
)
from app.database import Base
from app.models import Novel, WorldEntity, WorldRelationship


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
def relationship(db, novel):
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
    return relationship


def test_promote_worldpack_origin_to_manual():
    row = SimpleNamespace(origin="worldpack")

    changed = promote_worldpack_origin_to_manual(row)

    assert changed is True
    assert row.origin == "manual"


def test_is_worldpack_origin_matches_only_worldpack_rows():
    assert is_worldpack_origin(SimpleNamespace(origin="worldpack")) is True
    assert is_worldpack_origin(SimpleNamespace(origin="manual")) is False


def test_is_worldpack_controlled_by_pack_requires_matching_pack_id():
    row = SimpleNamespace(origin="worldpack", worldpack_pack_id="pack-1")

    assert is_worldpack_controlled_by_pack(row, pack_id="pack-1") is True
    assert is_worldpack_controlled_by_pack(row, pack_id="pack-2") is False


def test_promote_ai_draft_origin_to_manual_for_worldgen_draft():
    row = SimpleNamespace(origin="worldgen", status="draft")

    changed = promote_ai_draft_origin_to_manual(row)

    assert changed is True
    assert row.origin == "manual"


def test_promote_ai_draft_origin_to_manual_keeps_confirmed_row():
    row = SimpleNamespace(origin="bootstrap", status="confirmed")

    changed = promote_ai_draft_origin_to_manual(row)

    assert changed is False
    assert row.origin == "bootstrap"


def test_relationship_uniqueness_rejects_canonical_duplicate(db, relationship):
    with pytest.raises(RelationshipConflictError):
        ensure_relationship_is_unique(
            db,
            novel_id=relationship.novel_id,
            source_id=relationship.source_id,
            target_id=relationship.target_id,
            label="伴侣关系",
        )


def test_relationship_uniqueness_allows_existing_row_when_excluded(db, relationship):
    ensure_relationship_is_unique(
        db,
        novel_id=relationship.novel_id,
        source_id=relationship.source_id,
        target_id=relationship.target_id,
        label="伴侣关系",
        exclude_relationship_id=relationship.id,
    )


def test_build_relationship_signature_canonicalizes_label():
    signature = build_relationship_signature(source_id=1, target_id=2, label="伴侣关系")

    assert signature == (1, 2, "伴侣")


def test_relationship_signature_from_row_falls_back_to_label():
    row = SimpleNamespace(source_id=1, target_id=2, label="伴侣关系", label_canonical="")

    assert relationship_signature_from_row(row) == (1, 2, "伴侣")


def test_normalize_system_data_for_write_preserves_list_item_ids():
    normalized = normalize_system_data_for_write(
        "list",
        {"items": [{"id": "title_mushen", "label": "母神", "description": "x"}]},
    )

    assert normalized == {"items": [{"id": "title_mushen", "label": "母神", "description": "x"}]}


def test_normalize_system_data_for_write_rejects_unknown_display_type():
    with pytest.raises(InvalidSystemDisplayTypeError):
        normalize_system_data_for_write("bogus", {})


def test_normalize_system_data_for_write_preserves_validation_error_shape():
    with pytest.raises(ValidationError):
        normalize_system_data_for_write(
            "list",
            {"items": [{"label": "A", "visibility": "bogus"}]},
        )
