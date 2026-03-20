# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Copilot backend workflow tests.

Tests verify user workflows and product contracts, not code paths:
  - evidence sourced from backend, not model invention
  - suggestion compilation validates against live world state
  - apply IS the approval boundary (confirmed, not draft)
  - draft_cleanup only targets draft rows
  - stale targets don't block other suggestions
  - session/run scoping is strict (user + novel)
  - inquiry-only runs are normal results
  - multilingual targeting safety
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import (
    Chapter,
    CopilotRun,
    CopilotSession,
    Novel,
    QuotaReservation,
    User,
    WorldEntity,
    WorldEntityAttribute,
    WorldRelationship,
    WorldSystem,
)

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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


@pytest.fixture(scope="function")
def hosted_settings(_force_selfhost_settings):  # ensure conftest runs first
    import app.config as config_mod
    from app.config import Settings

    prev = config_mod._settings_instance
    config_mod._settings_instance = Settings(deploy_mode="hosted", _env_file=None)
    try:
        yield
    finally:
        config_mod._settings_instance = prev


@pytest.fixture
def novel(db):
    n = Novel(title="测试小说", author="测试", file_path="/tmp/t.txt", total_chapters=3, language="zh")
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@pytest.fixture
def hosted_user(db, hosted_settings):
    user = User(
        username="hosted_copilot_user",
        hashed_password="x",
        role="admin",
        is_active=True,
        generation_quota=2,
        feedback_submitted=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def chapters(db, novel):
    chs = []
    for i in range(1, 4):
        ch = Chapter(novel_id=novel.id, chapter_number=i, title=f"第{i}章", content=f"这是第{i}章的内容。主角张三在宗门修行。")
        db.add(ch)
        chs.append(ch)
    db.commit()
    for ch in chs:
        db.refresh(ch)
    return chs


@pytest.fixture
def entities(db, novel):
    e1 = WorldEntity(novel_id=novel.id, name="张三", entity_type="Character", description="主角", aliases=["三哥"], status="confirmed", origin="manual")
    e2 = WorldEntity(novel_id=novel.id, name="李四", entity_type="Character", description="反派", aliases=[], status="confirmed", origin="manual")
    e3 = WorldEntity(novel_id=novel.id, name="王五", entity_type="Character", description="", aliases=[], status="draft", origin="bootstrap")
    db.add_all([e1, e2, e3])
    db.commit()
    for e in [e1, e2, e3]:
        db.refresh(e)
    return [e1, e2, e3]


@pytest.fixture
def attributes(db, entities):
    a = WorldEntityAttribute(entity_id=entities[0].id, key="境界", surface="金丹期", visibility="active", origin="manual")
    db.add(a)
    db.commit()
    db.refresh(a)
    return [a]


@pytest.fixture
def relationships(db, novel, entities):
    r = WorldRelationship(
        novel_id=novel.id, source_id=entities[0].id, target_id=entities[1].id,
        label="对手", label_canonical="对手", description="宿敌", status="confirmed", origin="manual",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return [r]


@pytest.fixture
def systems(db, novel):
    s = WorldSystem(novel_id=novel.id, name="修行体系", display_type="hierarchy", description="宗门修行等级", constraints=["每阶需要突破"], status="confirmed", origin="manual")
    db.add(s)
    db.commit()
    db.refresh(s)
    return [s]


@pytest.fixture
def client(db):
    from app.api import copilot as copilot_api, world

    test_app = FastAPI()
    test_app.include_router(copilot_api.router)
    test_app.include_router(world.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db
    from app.core.auth import check_generation_quota, get_current_user, get_current_user_or_default
    fake_user = User(id=1, username="testuser", hashed_password="x", role="admin", is_active=True, generation_quota=999)
    test_app.dependency_overrides[get_current_user] = lambda: fake_user
    test_app.dependency_overrides[get_current_user_or_default] = lambda: fake_user
    test_app.dependency_overrides[check_generation_quota] = lambda: fake_user

    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


@pytest.fixture
def hosted_client(db, hosted_user, monkeypatch):
    import app.core.auth as auth_core
    from app.api import copilot as copilot_api, world
    from app.core.auth import get_current_user, get_current_user_or_default

    test_app = FastAPI()
    test_app.include_router(copilot_api.router)
    test_app.include_router(world.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_user] = lambda: hosted_user
    test_app.dependency_overrides[get_current_user_or_default] = lambda: hosted_user
    monkeypatch.setattr(auth_core, "ensure_ai_available", lambda *args, **kwargs: None)

    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


# ===========================================================================
# Session tests
# ===========================================================================


class TestSessionOpenReuse:
    def test_create_new_session(self, client, novel):
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={"mode": "research", "scope": "whole_book"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] is True
        assert data["session_id"]

    def test_reuse_same_signature(self, client, novel):
        body = {"mode": "research", "scope": "whole_book", "interaction_locale": "zh"}
        r1 = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json=body).json()
        r2 = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json=body).json()
        assert r1["session_id"] == r2["session_id"]
        assert r1["created"] is True
        assert r2["created"] is False

    def test_different_scope_different_session(self, client, novel, entities):
        r1 = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={"mode": "research", "scope": "whole_book"}).json()
        r2 = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={"mode": "current_entity", "scope": "current_entity", "context": {"entity_id": entities[0].id}}).json()
        assert r1["session_id"] != r2["session_id"]

    def test_different_locale_different_session(self, client, novel):
        r1 = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={"mode": "research", "scope": "whole_book", "interaction_locale": "zh"}).json()
        r2 = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={"mode": "research", "scope": "whole_book", "interaction_locale": "en"}).json()
        assert r1["session_id"] != r2["session_id"]

    def test_locale_aliases_reuse_same_session_and_return_normalized_locale(self, client, novel):
        r1 = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={"mode": "research", "scope": "whole_book", "interaction_locale": "en-US"},
        ).json()
        r2 = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={"mode": "research", "scope": "whole_book", "interaction_locale": "en"},
        ).json()
        assert r1["session_id"] == r2["session_id"]
        assert r1["interaction_locale"] == "en"
        assert r2["interaction_locale"] == "en"

    def test_non_string_interaction_locale_returns_422(self, client, novel):
        from pydantic import ValidationError

        from app.schemas import CopilotSessionOpenRequest

        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={"mode": "research", "scope": "whole_book", "interaction_locale": 5},
        )

        assert resp.status_code == 422
        with pytest.raises(ValidationError):
            CopilotSessionOpenRequest(mode="research", scope="whole_book", interaction_locale=5)

    def test_service_boundary_normalizes_interaction_locale_aliases(self, db, novel):
        from app.core.copilot import open_or_reuse_session

        session, created = open_or_reuse_session(
            db,
            novel.id,
            1,
            "research",
            "whole_book",
            None,
            "en-US",
            "English workspace",
        )

        assert created is True
        assert session.interaction_locale == "en"

        reused, created = open_or_reuse_session(
            db,
            novel.id,
            1,
            "research",
            "whole_book",
            None,
            "en",
            "English workspace 2",
        )

        assert created is False
        assert reused.session_id == session.session_id
        assert reused.interaction_locale == "en"

    def test_ui_surface_context_reuses_same_session_identity(self, client, novel, entities):
        r1 = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={
                "mode": "current_entity",
                "scope": "current_entity",
                "context": {"entity_id": entities[0].id, "surface": "studio", "stage": "entity"},
            },
        ).json()
        r2 = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={
                "mode": "current_entity",
                "scope": "current_entity",
                "context": {"entity_id": entities[0].id, "surface": "atlas", "stage": "entities", "tab": "entities"},
            },
        ).json()
        assert r1["session_id"] == r2["session_id"]
        assert r2["context"]["surface"] == "atlas"
        assert r2["context"]["tab"] == "entities"
        assert r2["context"]["stage"] is None

    def test_whole_book_ui_context_does_not_split_session(self, client, novel):
        r1 = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={
                "mode": "research",
                "scope": "whole_book",
                "context": {"surface": "studio", "stage": "write"},
            },
        ).json()
        r2 = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={
                "mode": "research",
                "scope": "whole_book",
                "context": {"surface": "atlas", "stage": "systems", "tab": "systems"},
            },
        ).json()
        assert r1["session_id"] == r2["session_id"]
        assert r2["context"]["surface"] == "atlas"
        assert r2["context"]["tab"] == "systems"
        assert r2["context"]["stage"] is None

    def test_current_entity_scope_requires_entity_id(self, client, novel):
        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={
                "mode": "current_entity",
                "scope": "current_entity",
                "context": {"surface": "studio", "stage": "entity"},
            },
        )
        assert resp.status_code == 422

    def test_research_current_tab_requires_relationship_tab(self, client, novel):
        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={
                "mode": "research",
                "scope": "current_tab",
                "context": {"tab": "review"},
            },
        )
        assert resp.status_code == 422

    def test_duplicate_signature_conflict_reuses_existing_session(self, db, novel, monkeypatch):
        from app.core.copilot import _load_session_by_signature, open_or_reuse_session

        existing, created = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "初始标题")
        assert created is True

        calls = {"count": 0}

        def fake_load(db_session, *, novel_id, user_id, signature):
            calls["count"] += 1
            if calls["count"] == 1:
                return None
            return _load_session_by_signature(
                db_session,
                novel_id=novel_id,
                user_id=user_id,
                signature=signature,
            )

        monkeypatch.setattr("app.core.copilot._load_session_by_signature", fake_load)

        reused, created = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "更新标题")
        assert created is False
        assert reused.session_id == existing.session_id
        assert reused.display_title == "更新标题"

    def test_model_declares_unique_session_signature_index(self):
        indexes = {index.name: index for index in CopilotSession.__table__.indexes}
        lookup_index = indexes["uq_copilot_sessions_lookup"]
        assert lookup_index.unique is True

    def test_model_declares_partial_unique_active_run_index_for_sqlite_and_postgres(self):
        indexes = {index.name: index for index in CopilotRun.__table__.indexes}
        active_index = indexes["uq_copilot_runs_active_session"]
        assert active_index.unique is True
        assert active_index.dialect_options["sqlite"].get("where") is not None
        assert active_index.dialect_options["postgresql"].get("where") is not None


# ===========================================================================
# Backend-sourced evidence tests
# ===========================================================================


class TestBackendEvidence:
    def test_entity_scope_uses_window_index_only_when_fresh(self, db, novel, entities, chapters):
        from app.core.copilot import gather_evidence, load_scope_snapshot
        from app.core.indexing import mark_window_index_build_succeeded
        from app.core.indexing.window_index import NovelIndex, WindowRef

        mark_window_index_build_succeeded(
            novel,
            index_payload=NovelIndex(
                entity_windows={
                    entities[0].name: [
                        WindowRef(
                            window_id=1,
                            chapter_id=chapters[0].id,
                            start_pos=0,
                            end_pos=len(chapters[0].content),
                            entity_count=1,
                        )
                    ]
                },
                window_entities={1: {entities[0].name}},
            ).to_msgpack(),
            revision=1,
        )
        db.commit()

        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        evidence = gather_evidence(db, novel, snapshot, {"entity_id": entities[0].id})

        chapter_evidence = [item for item in evidence if item.source_type == "chapter_excerpt"]
        assert chapter_evidence
        assert any("包含对" in item.why_relevant for item in chapter_evidence)

    def test_evidence_has_verifiable_source_ref(self, db, novel, entities, chapters):
        from app.core.copilot import gather_evidence, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        evidence = gather_evidence(db, novel, snapshot, {"entity_id": entities[0].id})

        assert len(evidence) > 0
        for ev in evidence:
            assert ev.source_ref is not None
            assert ev.evidence_id  # unique ID for citation linking
            if ev.source_type == "chapter_excerpt":
                assert "chapter_id" in ev.source_ref
            elif ev.source_type == "world_entity":
                assert "entity_id" in ev.source_ref
            elif ev.source_type == "world_relationship":
                assert "relationship_id" in ev.source_ref

    def test_evidence_includes_entity_context_for_entity_scope(self, db, novel, entities, attributes, chapters):
        from app.core.copilot import gather_evidence, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        evidence = gather_evidence(db, novel, snapshot, {"entity_id": entities[0].id})

        entity_evidence = [e for e in evidence if e.source_type == "world_entity"]
        assert len(entity_evidence) >= 1
        assert "张三" in entity_evidence[0].excerpt

    def test_whole_book_preload_does_not_default_to_latest_three_chapters(self, db, novel, entities, relationships, systems, chapters):
        from app.core.copilot import gather_evidence, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)

        assert all(item.source_type != "chapter_excerpt" for item in evidence)

    @pytest.mark.parametrize(
        ("prepare_state", "expected_reason"),
        [
            ("missing", "全书内容还在准备中，先回退到最近章节上下文"),
            ("stale", "章节有更新，先回退到最近章节上下文"),
            ("failed", "全书内容整理失败，先回退到最近章节上下文"),
        ],
    )
    def test_entity_scope_falls_back_with_explicit_reason(
        self,
        db,
        novel,
        entities,
        chapters,
        prepare_state,
        expected_reason,
    ):
        from app.core.copilot import gather_evidence, load_scope_snapshot
        from app.core.indexing import (
            mark_window_index_build_failed,
            mark_window_index_build_succeeded,
            mark_window_index_inputs_changed,
        )

        if prepare_state == "stale":
            mark_window_index_build_succeeded(
                novel,
                index_payload=b"index-bytes",
                revision=1,
            )
            db.commit()
            mark_window_index_inputs_changed(novel)
            db.commit()
        elif prepare_state == "failed":
            mark_window_index_build_failed(
                novel,
                error="窗口索引重建失败，请稍后重试",
                revision=1,
            )
            db.commit()

        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        evidence = gather_evidence(db, novel, snapshot, {"entity_id": entities[0].id})

        chapter_evidence = [item for item in evidence if item.source_type == "chapter_excerpt"]
        assert chapter_evidence
        assert all(item.why_relevant == expected_reason for item in chapter_evidence)

    @pytest.mark.parametrize("state", ["fresh", "missing", "stale", "failed"])
    def test_window_index_find_requires_fresh_state(self, db, novel, entities, chapters, state):
        from app.core.copilot import _find_from_window_index, load_scope_snapshot
        from app.core.indexing import (
            mark_window_index_build_failed,
            mark_window_index_build_succeeded,
            mark_window_index_inputs_changed,
        )
        from app.core.indexing.window_index import NovelIndex, WindowRef

        if state == "fresh":
            mark_window_index_build_succeeded(
                novel,
                index_payload=NovelIndex(
                    entity_windows={
                        entities[0].name: [
                            WindowRef(
                                window_id=1,
                                chapter_id=chapters[0].id,
                                start_pos=0,
                                end_pos=len(chapters[0].content),
                                entity_count=1,
                            )
                        ]
                    },
                    window_entities={1: {entities[0].name}},
                ).to_msgpack(),
                revision=1,
            )
            db.commit()
        elif state == "stale":
            mark_window_index_build_succeeded(
                novel,
                index_payload=b"index-bytes",
                revision=1,
            )
            db.commit()
            mark_window_index_inputs_changed(novel)
            db.commit()
        elif state == "failed":
            mark_window_index_build_failed(
                novel,
                error="窗口索引重建失败，请稍后重试",
                revision=1,
            )
            db.commit()

        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        packs = _find_from_window_index("张三", db, novel.id, novel, snapshot)

        if state == "fresh":
            assert packs
        else:
            assert packs == []


# ===========================================================================
# Suggestion compilation tests (backend-grounded)
# ===========================================================================


class TestSuggestionCompilation:
    def _make_snapshot(self, entities, relationships, systems, db):
        from app.core.copilot import ScopeSnapshot
        novel = entities[0].novel if entities else Novel(id=1, title="test", language="zh")
        entities_by_id = {e.id: e for e in entities}
        attrs_by_entity: dict[int, list] = {}
        for e in entities:
            attrs = db.query(WorldEntityAttribute).filter(WorldEntityAttribute.entity_id == e.id).all()
            if attrs:
                attrs_by_entity[e.id] = attrs
        return ScopeSnapshot(
            novel=novel, novel_language="zh", entities=entities, entities_by_id=entities_by_id,
            relationships=relationships, systems=systems, attributes_by_entity=attrs_by_entity,
            draft_entities=[e for e in entities if e.status == "draft"],
            draft_relationships=[r for r in relationships if r.status == "draft"],
            draft_systems=[s for s in systems if s.status == "draft"],
        )

    def test_valid_update_compiles_to_actionable(self, db, novel, entities):
        from app.core.copilot import EvidenceItem, compile_suggestions
        snapshot = self._make_snapshot(entities, [], [], db)
        evidence = [EvidenceItem(evidence_id="ev_0", source_type="chapter_excerpt", source_ref={"chapter_id": 1}, title="第1章", excerpt="张三是宗门弟子", why_relevant="支撑")]
        raw = [{"kind": "update_entity", "title": "补完", "summary": "补充", "cited_evidence_indices": [0], "target_resource": "entity", "target_id": entities[0].id, "delta": {"description": "宗门弟子"}}]
        compiled = compile_suggestions(raw, evidence, snapshot, "research", "current_entity")
        assert len(compiled) == 1
        assert compiled[0].preview["actionable"] is True
        assert compiled[0].apply_action["type"] == "update_entity"

    def test_invalid_target_compiles_to_advisory(self, db, novel, entities):
        from app.core.copilot import compile_suggestions
        snapshot = self._make_snapshot(entities, [], [], db)
        raw = [{"kind": "update_entity", "title": "x", "summary": "x", "target_resource": "entity", "target_id": 99999, "delta": {"description": "x"}}]
        compiled = compile_suggestions(raw, [], snapshot, "research", "current_entity")
        assert len(compiled) == 1
        assert compiled[0].preview["actionable"] is False

    def test_create_entity_not_blocked_without_collision(self, db, novel, entities):
        from app.core.copilot import compile_suggestions
        snapshot = self._make_snapshot(entities, [], [], db)
        raw = [{"kind": "create_entity", "target_resource": "entity", "title": "新", "summary": "新", "delta": {"name": "太玄禁律", "entity_type": "Concept"}}]
        compiled = compile_suggestions(raw, [], snapshot, "research", "whole_book")
        assert len(compiled) == 1
        assert compiled[0].preview["actionable"] is True

    def test_create_blocked_by_name_collision(self, db, novel, entities):
        from app.core.copilot import compile_suggestions
        snapshot = self._make_snapshot(entities, [], [], db)
        raw = [{"kind": "create_entity", "target_resource": "entity", "title": "重名", "summary": "x", "delta": {"name": "张三", "entity_type": "Character"}}]
        compiled = compile_suggestions(raw, [], snapshot, "research", "whole_book")
        assert compiled[0].preview["actionable"] is False

    def test_attribute_suggestion_compiled_to_action(self, db, novel, entities, attributes):
        """Entity enrichment with attributes — the #1 workflow."""
        from app.core.copilot import compile_suggestions
        snapshot = self._make_snapshot(entities, [], [], db)
        raw = [{
            "kind": "update_entity", "title": "补属性", "summary": "补充", "target_resource": "entity",
            "target_id": entities[0].id,
            "delta": {"attributes": [{"key": "门派", "surface": "太玄宗"}, {"key": "境界", "surface": "元婴期"}]},
        }]
        compiled = compile_suggestions(raw, [], snapshot, "research", "current_entity")
        assert len(compiled) == 1
        assert compiled[0].preview["actionable"] is True
        action = compiled[0].apply_action
        assert "attribute_actions" in action
        attr_actions = action["attribute_actions"]
        # "门派" is new -> create_attribute; "境界" exists -> update_attribute
        types = [a["type"] for a in attr_actions]
        assert "create_attribute" in types
        assert "update_attribute" in types

    def test_update_relationship_target_contains_graph_focus_and_highlight(self, db, novel, entities, relationships):
        from app.core.copilot import compile_suggestions

        snapshot = self._make_snapshot(entities, relationships, [], db)
        raw = [{
            "kind": "update_relationship",
            "title": "补关系描述",
            "summary": "补充宿敌关系",
            "target_resource": "relationship",
            "target_id": relationships[0].id,
            "delta": {"description": "更明确的宿敌关系"},
        }]

        compiled = compile_suggestions(raw, [], snapshot, "research", "relationships")
        assert len(compiled) == 1
        assert compiled[0].target["tab"] == "relationships"
        assert compiled[0].target["entity_id"] == relationships[0].source_id
        assert compiled[0].target["highlight_id"] == relationships[0].id

    def test_create_relationship_target_uses_source_entity_context(self, db, novel, entities):
        from app.core.copilot import compile_suggestions

        snapshot = self._make_snapshot(entities, [], [], db)
        raw = [{
            "kind": "create_relationship",
            "title": "补关系",
            "summary": "建立张三和李四的联系",
            "target_resource": "relationship",
            "target_id": None,
            "delta": {
                "source_id": entities[0].id,
                "target_id": entities[1].id,
                "label": "同门",
            },
        }]

        compiled = compile_suggestions(raw, [], snapshot, "research", "relationships")
        assert len(compiled) == 1
        assert compiled[0].target["tab"] == "relationships"
        assert compiled[0].target["entity_id"] == entities[0].id

    def test_create_relationship_with_unresolved_entities_exposes_non_actionable_reason(self, db, novel, entities):
        from app.core.copilot import compile_suggestions

        snapshot = self._make_snapshot(entities, [], [], db)
        raw = [{
            "kind": "create_relationship",
            "title": "补关系",
            "summary": "建立两名新人物之间的联系",
            "target_resource": "relationship",
            "target_id": None,
            "delta": {
                "source_id": 9991,
                "target_id": 9992,
                "label": "同盟",
            },
        }]

        compiled = compile_suggestions(raw, [], snapshot, "research", "relationships")
        assert len(compiled) == 1
        assert compiled[0].preview["actionable"] is False
        assert "请先确认相关实体" in (compiled[0].preview["non_actionable_reason"] or "")

    def test_compile_suggestions_localizes_preview_to_english(self, db, novel, entities):
        from app.core.copilot import compile_suggestions

        snapshot = self._make_snapshot(entities, [], [], db)
        raw = [{
            "kind": "update_entity",
            "title": "Fill entity",
            "summary": "Add clearer details",
            "target_resource": "entity",
            "target_id": entities[0].id,
            "delta": {
                "description": "A clearer English description",
                "attributes": [{"key": "Faction", "surface": "Tai Xuan Sect"}],
            },
        }]

        compiled = compile_suggestions(
            raw,
            [],
            snapshot,
            "research",
            "current_entity",
            interaction_locale="en",
        )

        labels = {item["label"] for item in compiled[0].preview["field_deltas"]}
        assert "Description" in labels
        assert "Attribute · Faction" in labels

    def test_create_relationship_non_actionable_reason_localizes_to_english(self, db, novel, entities):
        from app.core.copilot import compile_suggestions

        snapshot = self._make_snapshot(entities, [], [], db)
        raw = [{
            "kind": "create_relationship",
            "title": "Add bond",
            "summary": "Link two unresolved targets",
            "target_resource": "relationship",
            "target_id": None,
            "delta": {
                "source_id": 9991,
                "target_id": 9992,
                "label": "Ally",
            },
        }]

        compiled = compile_suggestions(
            raw,
            [],
            snapshot,
            "research",
            "relationships",
            interaction_locale="en",
        )

        assert compiled[0].preview["actionable"] is False
        assert "Confirm those first" in (compiled[0].preview["non_actionable_reason"] or "")

    def test_compile_suggestions_localizes_fallback_title_and_new_resource_label_to_english(self, db, novel, entities):
        from app.core.copilot import compile_suggestions

        snapshot = self._make_snapshot(entities, [], [], db)
        raw = [{
            "kind": "create_entity",
            "summary": "Need a better-formed entity card",
            "target_resource": "entity",
            "delta": {},
        }]

        compiled = compile_suggestions(
            raw,
            [],
            snapshot,
            "research",
            "whole_book",
            interaction_locale="en",
        )

        assert compiled[0].title == "Suggestion 1"
        assert compiled[0].preview["target_label"] == "New entity"
        assert "incomplete" in (compiled[0].preview["non_actionable_reason"] or "")

    def test_create_relationship_with_same_run_entity_dependencies_compiles_actionable(self, db, novel, entities):
        from app.core.copilot import compile_suggestions

        snapshot = self._make_snapshot(entities, [], [], db)
        raw = [
            {
                "kind": "create_entity",
                "title": "创建林七",
                "summary": "补一个新人物",
                "target_resource": "entity",
                "target_id": None,
                "delta": {"name": "林七", "entity_type": "Character"},
            },
            {
                "kind": "create_entity",
                "title": "创建赵八",
                "summary": "再补一个新人物",
                "target_resource": "entity",
                "target_id": None,
                "delta": {"name": "赵八", "entity_type": "Character"},
            },
            {
                "kind": "create_relationship",
                "title": "补关系",
                "summary": "建立两名新人物之间的联系",
                "target_resource": "relationship",
                "target_id": None,
                "delta": {
                    "source_name": "林七",
                    "target_name": "赵八",
                    "label": "同盟",
                },
            },
        ]

        compiled = compile_suggestions(raw, [], snapshot, "research", "relationships")
        assert len(compiled) == 3
        assert compiled[2].preview["actionable"] is True
        endpoint_dependencies = compiled[2].apply_action["endpoint_dependencies"]
        assert endpoint_dependencies["source"]["suggestion_id"] == compiled[0].suggestion_id
        assert endpoint_dependencies["target"]["suggestion_id"] == compiled[1].suggestion_id

    def test_create_relationship_synthesizes_missing_endpoint_entities(self, db, novel, entities):
        from app.core.copilot import compile_suggestions

        snapshot = self._make_snapshot(entities, [], [], db)
        raw = [{
            "kind": "create_relationship",
            "title": "补关系",
            "summary": "让张三与太玄宗建立归属关系",
            "target_resource": "relationship",
            "target_id": None,
            "delta": {
                "source_id": entities[0].id,
                "target_name": "太玄宗",
                "target_entity_type": "Faction",
                "label": "隶属",
            },
        }]

        compiled = compile_suggestions(raw, [], snapshot, "research", "relationships")

        assert len(compiled) == 2
        synthetic_entity = compiled[0]
        relationship = compiled[1]
        assert synthetic_entity.kind == "create_entity"
        assert synthetic_entity.apply_action["data"]["name"] == "太玄宗"
        assert synthetic_entity.apply_action["data"]["entity_type"] == "Faction"
        assert relationship.preview["actionable"] is True
        endpoint_dependencies = relationship.apply_action["endpoint_dependencies"]
        assert endpoint_dependencies["target"]["suggestion_id"] == synthetic_entity.suggestion_id

    def test_create_relationship_resolves_existing_entity_alias_without_synthesizing_duplicate(self, db, novel, entities):
        from app.core.copilot import compile_suggestions

        entities[1].aliases = ["四哥"]
        db.commit()
        snapshot = self._make_snapshot(entities, [], [], db)
        raw = [{
            "kind": "create_relationship",
            "title": "补关系",
            "summary": "让张三与四哥建立联系",
            "target_resource": "relationship",
            "target_id": None,
            "delta": {
                "source_id": entities[0].id,
                "target_name": "四哥",
                "label": "同盟",
            },
        }]

        compiled = compile_suggestions(raw, [], snapshot, "research", "relationships")
        assert len(compiled) == 1
        assert compiled[0].preview["actionable"] is True
        assert "endpoint_dependencies" not in compiled[0].apply_action
        assert compiled[0].apply_action["data"]["target_id"] == entities[1].id

    def test_draft_cleanup_rejects_confirmed_target(self, db, novel, entities):
        """draft_cleanup must only target draft rows."""
        from app.core.copilot import compile_suggestions
        snapshot = self._make_snapshot(entities, [], [], db)
        # entities[0] is confirmed, not draft
        raw = [{"kind": "update_entity", "title": "x", "summary": "x", "target_resource": "entity", "target_id": entities[0].id, "delta": {"description": "x"}}]
        compiled = compile_suggestions(raw, [], snapshot, "draft_cleanup", "draft_cleanup")
        assert compiled[0].preview["actionable"] is False

    def test_draft_cleanup_allows_draft_target(self, db, novel, entities):
        """draft_cleanup allows targeting actual draft rows."""
        from app.core.copilot import compile_suggestions
        snapshot = self._make_snapshot(entities, [], [], db)
        # entities[2] is draft
        raw = [{"kind": "update_entity", "title": "补完草稿", "summary": "x", "target_resource": "entity", "target_id": entities[2].id, "delta": {"description": "补充描述"}}]
        compiled = compile_suggestions(raw, [], snapshot, "draft_cleanup", "draft_cleanup")
        assert compiled[0].preview["actionable"] is True
        assert compiled[0].target["tab"] == "review"
        assert compiled[0].target["review_kind"] == "entities"

    def test_draft_cleanup_rejects_create(self, db, novel, entities):
        from app.core.copilot import compile_suggestions
        snapshot = self._make_snapshot(entities, [], [], db)
        raw = [{"kind": "create_entity", "target_resource": "entity", "title": "新建", "summary": "x", "delta": {"name": "新实体", "entity_type": "Other"}}]
        compiled = compile_suggestions(raw, [], snapshot, "draft_cleanup", "draft_cleanup")
        assert compiled[0].preview["actionable"] is False


# ===========================================================================
# Apply contract: approval boundary
# ===========================================================================


class TestApplyContract:
    def _create_completed_run(self, db, novel, entities, interaction_locale: str = "zh"):
        session = CopilotSession(
            session_id="test-sess-apply", novel_id=novel.id, user_id=1,
            mode="current_entity", scope="current_entity", context_json={"entity_id": entities[0].id},
            interaction_locale=interaction_locale, signature=f"sig-apply-{interaction_locale}", display_title=entities[0].name,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        run = CopilotRun(
            run_id="test-run-apply", copilot_session_id=session.id,
            novel_id=novel.id, user_id=1, status="completed", prompt="补完",
            answer="完成", evidence_json=[],
            suggestions_json=[
                {
                    "suggestion_id": "sg_update", "kind": "update_entity", "title": "补描述", "summary": "x",
                    "evidence_ids": [], "target": {"resource": "entity", "resource_id": entities[0].id, "label": "张三", "tab": "entities", "entity_id": entities[0].id},
                    "preview": {"target_label": "张三", "summary": "x", "field_deltas": [], "evidence_quotes": [], "actionable": True},
                    "apply": {"type": "update_entity", "entity_id": entities[0].id, "data": {"description": "宗门弟子"}},
                    "status": "pending",
                },
                {
                    "suggestion_id": "sg_create", "kind": "create_entity", "title": "新建", "summary": "x",
                    "evidence_ids": [], "target": {"resource": "entity", "resource_id": None, "label": "太玄禁律", "tab": "entities"},
                    "preview": {"target_label": "太玄禁律", "summary": "x", "field_deltas": [], "evidence_quotes": [], "actionable": True},
                    "apply": {"type": "create_entity", "data": {"name": "太玄禁律", "entity_type": "Concept", "description": "禁忌规约"}},
                    "status": "pending",
                },
                {
                    "suggestion_id": "sg_advisory", "kind": "update_entity", "title": "仅参考", "summary": "x",
                    "evidence_ids": [], "target": {"resource": "entity", "resource_id": entities[0].id, "label": "张三", "tab": "entities"},
                    "preview": {"target_label": "张三", "summary": "x", "field_deltas": [], "evidence_quotes": [], "actionable": False},
                    "apply": None, "status": "pending",
                },
            ],
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return session, run

    def test_apply_update_modifies_entity(self, client, db, novel, entities):
        session, run = self._create_completed_run(db, novel, entities)
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply", json={"suggestion_ids": ["sg_update"]})
        assert resp.status_code == 200
        assert resp.json()["results"][0]["success"] is True
        db.refresh(entities[0])
        assert entities[0].description == "宗门弟子"

    def test_apply_create_produces_confirmed_manual_row(self, client, db, novel, entities):
        """Apply IS the approval boundary — created rows are confirmed, not draft."""
        session, run = self._create_completed_run(db, novel, entities)
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply", json={"suggestion_ids": ["sg_create"]})
        assert resp.status_code == 200
        assert resp.json()["results"][0]["success"] is True
        new_entity = db.query(WorldEntity).filter(WorldEntity.name == "太玄禁律").first()
        assert new_entity is not None
        assert new_entity.origin == "manual"
        assert new_entity.status == "confirmed"

    def test_apply_create_rolls_back_when_deferred_attribute_write_fails(self, client, db, novel, entities):
        session = CopilotSession(
            session_id="test-sess-apply-rollback",
            novel_id=novel.id,
            user_id=1,
            mode="current_entity",
            scope="current_entity",
            context_json={"entity_id": entities[0].id},
            interaction_locale="zh",
            signature="sig-apply-rollback",
            display_title="张三",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        run = CopilotRun(
            run_id="test-run-apply-rollback",
            copilot_session_id=session.id,
            novel_id=novel.id,
            user_id=1,
            status="completed",
            prompt="补完",
            answer="完成",
            evidence_json=[],
            suggestions_json=[
                {
                    "suggestion_id": "sg_create_attr_conflict",
                    "kind": "create_entity",
                    "title": "新建失败回滚",
                    "summary": "x",
                    "evidence_ids": [],
                    "target": {"resource": "entity", "resource_id": None, "label": "玄天戒律", "tab": "entities"},
                    "preview": {"target_label": "玄天戒律", "summary": "x", "field_deltas": [], "evidence_quotes": [], "actionable": True},
                    "apply": {
                        "type": "create_entity",
                        "data": {"name": "玄天戒律", "entity_type": "Concept", "description": "会触发属性冲突"},
                        "deferred_attribute_actions": [
                            {"type": "create_attribute", "data": {"key": "约束", "surface": "不可违逆"}},
                            {"type": "create_attribute", "data": {"key": "约束", "surface": "重复键导致失败"}},
                        ],
                    },
                    "status": "pending",
                },
            ],
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply",
            json={"suggestion_ids": ["sg_create_attr_conflict"]},
        )

        assert resp.status_code == 200
        result = resp.json()["results"][0]
        assert result["success"] is False

        assert db.query(WorldEntity).filter(
            WorldEntity.novel_id == novel.id,
            WorldEntity.name == "玄天戒律",
        ).first() is None

        db.refresh(run)
        assert run.suggestions_json[0]["status"] == "pending"

    def test_advisory_suggestion_not_applicable(self, client, db, novel, entities):
        session, run = self._create_completed_run(db, novel, entities)
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply", json={"suggestion_ids": ["sg_advisory"]})
        assert resp.json()["results"][0]["success"] is False
        assert resp.json()["results"][0]["error_code"] == "not_actionable"

    def test_apply_endpoint_localizes_not_actionable_error_to_english(self, client, db, novel, entities):
        session, run = self._create_completed_run(db, novel, entities, interaction_locale="en")
        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply",
            json={"suggestion_ids": ["sg_advisory"]},
        )

        assert resp.status_code == 200
        result = resp.json()["results"][0]
        assert result["success"] is False
        assert result["error_code"] == "not_actionable"
        assert "cannot be applied directly" in result["error_message"]

    def test_stale_target_doesnt_block_others(self, client, db, novel, entities):
        session, run = self._create_completed_run(db, novel, entities)
        db.delete(entities[0])
        db.commit()
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply", json={"suggestion_ids": ["sg_update"]})
        results = resp.json()["results"]
        assert results[0]["success"] is False
        assert results[0]["error_code"] == "copilot_target_stale"

    def test_apply_endpoint_localizes_stale_error_to_english(self, client, db, novel, entities):
        session, run = self._create_completed_run(db, novel, entities, interaction_locale="en")
        db.delete(entities[0])
        db.commit()

        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply",
            json={"suggestion_ids": ["sg_update"]},
        )

        result = resp.json()["results"][0]
        assert result["success"] is False
        assert result["error_code"] == "copilot_target_stale"
        assert result["error_message"] == "The underlying content just changed. Refresh and try again."

    def test_apply_on_running_run_rejected(self, client, db, novel, entities):
        session = CopilotSession(session_id="sess-running", novel_id=novel.id, user_id=1, mode="research", scope="whole_book", interaction_locale="zh", signature="sig-r", display_title="")
        db.add(session)
        db.commit()
        db.refresh(session)
        run = CopilotRun(run_id="run-running", copilot_session_id=session.id, novel_id=novel.id, user_id=1, status="running", prompt="x")
        db.add(run)
        db.commit()
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply", json={"suggestion_ids": ["x"]})
        assert resp.status_code == 409

    def test_apply_endpoint_returns_auto_applied_dependency_results(self, client, db, novel, entities):
        from app.core.copilot import compile_suggestions
        from app.core.copilot.suggestions import serialize_compiled_suggestions

        session = CopilotSession(
            session_id="test-sess-chain-api",
            novel_id=novel.id,
            user_id=1,
            mode="research",
            scope="whole_book",
            interaction_locale="zh",
            signature="sig-chain-api",
            display_title="关系补全",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        snapshot = TestSuggestionCompilation()._make_snapshot(entities, [], [], db)
        raw = [
            {
                "kind": "create_entity",
                "title": "创建林七",
                "summary": "补一个新人物",
                "target_resource": "entity",
                "target_id": None,
                "delta": {"name": "林七", "entity_type": "Character"},
            },
            {
                "kind": "create_entity",
                "title": "创建赵八",
                "summary": "再补一个新人物",
                "target_resource": "entity",
                "target_id": None,
                "delta": {"name": "赵八", "entity_type": "Character"},
            },
            {
                "kind": "create_relationship",
                "title": "补关系",
                "summary": "建立两名新人物之间的联系",
                "target_resource": "relationship",
                "target_id": None,
                "delta": {
                    "source_name": "林七",
                    "target_name": "赵八",
                    "label": "同盟",
                },
            },
        ]
        compiled = compile_suggestions(raw, [], snapshot, "research", "relationships")
        run = CopilotRun(
            run_id="test-run-chain-api",
            copilot_session_id=session.id,
            novel_id=novel.id,
            user_id=1,
            status="completed",
            prompt="补关系",
            answer="完成",
            evidence_json=[],
            suggestions_json=serialize_compiled_suggestions(compiled),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        relationship_suggestion = next(item for item in compiled if item.kind == "create_relationship")
        response = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/apply",
            json={"suggestion_ids": [relationship_suggestion.suggestion_id]},
        )

        assert response.status_code == 200
        result_ids = [item["suggestion_id"] for item in response.json()["results"]]
        assert result_ids == [item.suggestion_id for item in compiled]
        assert all(item["success"] is True for item in response.json()["results"])

    def test_apply_relationship_auto_applies_same_run_entity_dependencies(self, db, novel, entities):
        from app.core.copilot import apply_suggestions, compile_suggestions
        from app.core.copilot.suggestions import serialize_compiled_suggestions

        session = CopilotSession(
            session_id="test-sess-chain",
            novel_id=novel.id,
            user_id=1,
            mode="research",
            scope="whole_book",
            interaction_locale="zh",
            signature="sig-chain",
            display_title="关系补全",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        snapshot = TestSuggestionCompilation()._make_snapshot(entities, [], [], db)
        raw = [
            {
                "kind": "create_entity",
                "title": "创建林七",
                "summary": "补一个新人物",
                "target_resource": "entity",
                "target_id": None,
                "delta": {"name": "林七", "entity_type": "Character"},
            },
            {
                "kind": "create_entity",
                "title": "创建赵八",
                "summary": "再补一个新人物",
                "target_resource": "entity",
                "target_id": None,
                "delta": {"name": "赵八", "entity_type": "Character"},
            },
            {
                "kind": "create_relationship",
                "title": "补关系",
                "summary": "建立两名新人物之间的联系",
                "target_resource": "relationship",
                "target_id": None,
                "delta": {
                    "source_name": "林七",
                    "target_name": "赵八",
                    "label": "同盟",
                },
            },
        ]
        compiled = compile_suggestions(raw, [], snapshot, "research", "relationships")
        run = CopilotRun(
            run_id="test-run-chain",
            copilot_session_id=session.id,
            novel_id=novel.id,
            user_id=1,
            status="completed",
            prompt="补关系",
            answer="完成",
            evidence_json=[],
            suggestions_json=serialize_compiled_suggestions(compiled),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        relationship_suggestion = next(item for item in compiled if item.kind == "create_relationship")
        results = apply_suggestions(db, run, [relationship_suggestion.suggestion_id])

        assert all(result.success for result in results)
        assert [result.suggestion_id for result in results] == [item.suggestion_id for item in compiled]
        names = {entity.name for entity in db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id).all()}
        assert "林七" in names
        assert "赵八" in names

        relationship = db.query(WorldRelationship).filter(
            WorldRelationship.novel_id == novel.id,
            WorldRelationship.label == "同盟",
        ).first()
        assert relationship is not None
        assert relationship.status == "confirmed"

        db.refresh(run)
        statuses = {item["suggestion_id"]: item["status"] for item in (run.suggestions_json or [])}
        assert statuses[relationship_suggestion.suggestion_id] == "applied"
        assert sum(1 for status in statuses.values() if status == "applied") == 3

    def test_apply_relationship_with_synthesized_entity_dependency(self, db, novel, entities):
        from app.core.copilot import apply_suggestions, compile_suggestions
        from app.core.copilot.suggestions import serialize_compiled_suggestions

        session = CopilotSession(
            session_id="test-sess-synth-chain",
            novel_id=novel.id,
            user_id=1,
            mode="research",
            scope="current_entity",
            interaction_locale="zh",
            signature="sig-synth-chain",
            display_title="关系补全",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        snapshot = TestSuggestionCompilation()._make_snapshot(entities, [], [], db)
        raw = [{
            "kind": "create_relationship",
            "title": "补关系",
            "summary": "让张三与太玄宗建立归属关系",
            "target_resource": "relationship",
            "target_id": None,
            "delta": {
                "source_id": entities[0].id,
                "target_name": "太玄宗",
                "target_entity_type": "Faction",
                "label": "隶属",
            },
        }]

        compiled = compile_suggestions(raw, [], snapshot, "research", "relationships")
        relationship_suggestion = next(item for item in compiled if item.kind == "create_relationship")
        run = CopilotRun(
            run_id="test-run-synth-chain",
            copilot_session_id=session.id,
            novel_id=novel.id,
            user_id=1,
            status="completed",
            prompt="补关系",
            answer="完成",
            evidence_json=[],
            suggestions_json=serialize_compiled_suggestions(compiled),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        results = apply_suggestions(db, run, [relationship_suggestion.suggestion_id])

        assert all(result.success for result in results)
        created_entity = db.query(WorldEntity).filter(
            WorldEntity.novel_id == novel.id,
            WorldEntity.name == "太玄宗",
        ).first()
        assert created_entity is not None
        assert created_entity.entity_type == "Faction"
        relationship = db.query(WorldRelationship).filter(
            WorldRelationship.novel_id == novel.id,
            WorldRelationship.label == "隶属",
        ).first()
        assert relationship is not None
        assert relationship.target_id == created_entity.id

    def test_apply_relationship_auto_applies_synthesized_endpoint_entity(self, db, novel, entities):
        from app.core.copilot import apply_suggestions, compile_suggestions
        from app.core.copilot.suggestions import serialize_compiled_suggestions

        session = CopilotSession(
            session_id="test-sess-synth",
            novel_id=novel.id,
            user_id=1,
            mode="research",
            scope="current_entity",
            interaction_locale="zh",
            signature="sig-synth",
            display_title="实体补全",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        snapshot = TestSuggestionCompilation()._make_snapshot(entities, [], [], db)
        raw = [{
            "kind": "create_relationship",
            "title": "补关系",
            "summary": "让张三与太玄宗建立归属关系",
            "target_resource": "relationship",
            "target_id": None,
            "delta": {
                "source_id": entities[0].id,
                "target_name": "太玄宗",
                "target_entity_type": "Faction",
                "label": "隶属",
            },
        }]
        compiled = compile_suggestions(raw, [], snapshot, "research", "relationships")
        run = CopilotRun(
            run_id="test-run-synth",
            copilot_session_id=session.id,
            novel_id=novel.id,
            user_id=1,
            status="completed",
            prompt="补关系",
            answer="完成",
            evidence_json=[],
            suggestions_json=serialize_compiled_suggestions(compiled),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        relationship_suggestion = next(item for item in compiled if item.kind == "create_relationship")
        results = apply_suggestions(db, run, [relationship_suggestion.suggestion_id])

        assert all(result.success for result in results)
        created = db.query(WorldEntity).filter(
            WorldEntity.novel_id == novel.id,
            WorldEntity.name == "太玄宗",
        ).first()
        assert created is not None
        assert created.entity_type == "Faction"
        relationship = db.query(WorldRelationship).filter(
            WorldRelationship.novel_id == novel.id,
            WorldRelationship.label == "隶属",
        ).first()
        assert relationship is not None
        assert relationship.target_id == created.id


# ===========================================================================
# Dismiss tests
# ===========================================================================


class TestDismiss:
    def test_dismiss_doesnt_mutate_world_model(self, client, db, novel, entities):
        session = CopilotSession(session_id="sess-dismiss", novel_id=novel.id, user_id=1, mode="research", scope="whole_book", interaction_locale="zh", signature="sig-d", display_title="")
        db.add(session)
        db.commit()
        db.refresh(session)
        run = CopilotRun(
            run_id="run-dismiss", copilot_session_id=session.id, novel_id=novel.id, user_id=1, status="completed", prompt="x",
            suggestions_json=[{
                "suggestion_id": "sg_d", "kind": "update_entity", "title": "x", "summary": "x", "evidence_ids": [],
                "target": {"resource": "entity", "resource_id": entities[0].id, "label": "张三", "tab": "entities"},
                "preview": {"target_label": "张三", "summary": "x", "field_deltas": [], "evidence_quotes": [], "actionable": True},
                "apply": {"type": "update_entity", "entity_id": entities[0].id, "data": {"description": "不应写入"}},
                "status": "pending",
            }],
        )
        db.add(run)
        db.commit()
        original_desc = entities[0].description
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}/dismiss", json={"suggestion_ids": ["sg_d"]})
        assert resp.status_code == 200
        db.refresh(entities[0])
        assert entities[0].description == original_desc
        db.refresh(run)
        assert run.suggestions_json[0]["status"] == "dismissed"


# ===========================================================================
# Admission control tests
# ===========================================================================


class TestAdmissionControl:
    def test_create_run_snapshots_canonical_context_before_session_reuse(self, db, novel, entities):
        from app.core.copilot import create_run, open_or_reuse_session

        studio_context = {"entity_id": entities[0].id, "surface": "studio", "stage": "entity"}
        atlas_context = {"entity_id": entities[0].id, "surface": "atlas", "stage": "entities", "tab": "entities"}

        session, _ = open_or_reuse_session(
            db,
            novel.id,
            1,
            "current_entity",
            "current_entity",
            studio_context,
            "zh",
            "张三",
        )
        run = create_run(db, session, 1, "先看 studio 上下文")

        reused, created = open_or_reuse_session(
            db,
            novel.id,
            1,
            "current_entity",
            "current_entity",
            atlas_context,
            "zh",
            "张三 Atlas",
        )

        db.refresh(run)
        db.refresh(reused)
        assert created is False
        assert reused.session_id == session.session_id
        assert run.context_json == studio_context
        assert reused.context_json == {"entity_id": entities[0].id, "surface": "atlas", "tab": "entities"}

    def test_one_active_run_per_session(self, db, novel):
        from app.core.copilot import CopilotError, create_run, open_or_reuse_session
        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")
        create_run(db, session, 1, "first")
        with pytest.raises(CopilotError) as exc_info:
            create_run(db, session, 1, "second")
        assert exc_info.value.code == "session_run_active"

    def test_max_active_runs_per_user(self, db, novel):
        from app.config import get_settings
        from app.core.copilot import CopilotError, create_run, open_or_reuse_session
        limit = get_settings().copilot_max_runs_per_user
        for i in range(limit):
            session, _ = open_or_reuse_session(
                db,
                novel.id,
                1,
                "current_entity",
                "current_entity",
                {"entity_id": i + 100},
                "zh",
                f"s{i}",
            )
            create_run(db, session, 1, f"run {i}")
        extra, _ = open_or_reuse_session(
            db,
            novel.id,
            1,
            "current_entity",
            "current_entity",
            {"entity_id": 999},
            "zh",
            "extra",
        )
        with pytest.raises(CopilotError) as exc_info:
            create_run(db, extra, 1, "too many")
        assert exc_info.value.code == "too_many_active_runs"

    def test_stale_queued_run_reclaimed_before_new_run(self, db, novel):
        from datetime import datetime, timedelta, timezone
        from app.core.copilot import create_run, open_or_reuse_session

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")
        stale_run = create_run(db, session, 1, "first")
        stale_run.lease_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=60)
        db.commit()

        replacement = create_run(db, session, 1, "second")

        db.refresh(stale_run)
        assert stale_run.status == "interrupted"
        assert replacement.run_id != stale_run.run_id
        assert replacement.status == "queued"

    def test_db_constraint_translates_duplicate_active_run_conflict(self, db, novel, monkeypatch):
        from app.core.copilot import CopilotError, create_run, open_or_reuse_session

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")
        create_run(db, session, 1, "first")

        monkeypatch.setattr("app.core.copilot._count_active_runs_in_session", lambda *_args, **_kwargs: 0)

        with pytest.raises(CopilotError) as exc_info:
            create_run(db, session, 1, "second")
        assert exc_info.value.code == "session_run_active"


class TestHostedQuotaBilling:
    def test_run_create_reserves_quota_and_links_reservation(self, hosted_client, db, novel, hosted_user, monkeypatch):
        from app.api import copilot as copilot_api

        novel.owner_id = hosted_user.id
        db.commit()
        db.refresh(novel)

        session_resp = hosted_client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={"mode": "research", "scope": "whole_book"},
        )
        assert session_resp.status_code == 200
        session_id = session_resp.json()["session_id"]

        scheduled: list[object] = []

        def fake_create_task(coro):
            scheduled.append(coro)
            coro.close()
            return object()

        monkeypatch.setattr(copilot_api.asyncio, "create_task", fake_create_task)

        resp = hosted_client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs",
            json={"prompt": "分析张三"},
        )
        assert resp.status_code == 202

        data = resp.json()
        run = db.query(CopilotRun).filter(CopilotRun.run_id == data["run_id"]).one()
        reservation = db.query(QuotaReservation).filter(QuotaReservation.id == run.quota_reservation_id).one()

        db.refresh(hosted_user)
        assert hosted_user.generation_quota == 1
        assert run.quota_reservation_id is not None
        assert reservation.reserved_count == 1
        assert reservation.charged_count == 0
        assert reservation.released_at is None
        assert len(scheduled) == 1

    def test_run_create_returns_structured_quota_code_when_quota_is_exhausted(self, hosted_client, db, novel, hosted_user):
        novel.owner_id = hosted_user.id
        hosted_user.generation_quota = 0
        db.commit()
        db.refresh(novel)
        db.refresh(hosted_user)

        session_resp = hosted_client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={"mode": "research", "scope": "whole_book"},
        )
        assert session_resp.status_code == 200
        session_id = session_resp.json()["session_id"]

        resp = hosted_client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs",
            json={"prompt": "分析张三"},
        )

        assert resp.status_code == 429
        data = resp.json()
        assert data["detail"]["code"] == "generation_quota_exhausted"
        assert "quota exhausted" in data["detail"]["message"].lower()

    def test_reclaim_stale_run_refunds_reserved_quota(self, db, novel, hosted_user):
        from datetime import datetime, timedelta, timezone

        from app.core.auth import open_quota_reservation
        from app.core.copilot import create_run, open_or_reuse_session, reclaim_stale_runs

        novel.owner_id = hosted_user.id
        db.commit()

        session, _ = open_or_reuse_session(db, novel.id, hosted_user.id, "research", "whole_book", None, "zh", "")
        reservation_id = open_quota_reservation(db, hosted_user.id, count=1)
        run = create_run(db, session, hosted_user.id, "排队中的请求", quota_reservation_id=reservation_id)
        run.lease_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=60)
        db.commit()

        reclaimed = reclaim_stale_runs(db, run_ids=[run.run_id])

        db.refresh(run)
        db.refresh(hosted_user)
        reservation = db.query(QuotaReservation).filter(QuotaReservation.id == reservation_id).one()
        assert reclaimed == [run.run_id]
        assert run.status == "interrupted"
        assert hosted_user.generation_quota == 2
        assert reservation.charged_count == 0
        assert reservation.released_at is not None

    @pytest.mark.asyncio
    async def test_execute_copilot_run_charges_completed_hosted_run(self, db, novel, hosted_user, monkeypatch):
        import app.database as db_mod
        import app.core.copilot as copilot_mod
        from app.core.auth import open_quota_reservation
        from app.core.copilot import create_run, execute_copilot_run, open_or_reuse_session

        novel.owner_id = hosted_user.id
        db.commit()

        session, _ = open_or_reuse_session(db, novel.id, hosted_user.id, "research", "whole_book", None, "zh", "")
        reservation_id = open_quota_reservation(db, hosted_user.id, count=1)
        run = create_run(db, session, hosted_user.id, "分析张三", quota_reservation_id=reservation_id)

        async def fake_run_tool_loop(*_args, **_kwargs):
            return {"answer": "已完成分析", "suggestions": []}, [], None

        monkeypatch.setattr(db_mod, "SessionLocal", TestingSessionLocal)
        monkeypatch.setattr(copilot_mod, "gather_evidence", lambda *_args, **_kwargs: [])
        monkeypatch.setattr(copilot_mod, "_run_tool_loop", fake_run_tool_loop)
        monkeypatch.setattr(copilot_mod, "compile_suggestions", lambda *_args, **_kwargs: [])

        await execute_copilot_run(run.run_id, novel.id, hosted_user.id, llm_config={"billing_source_hint": "selfhost"})

        db.expire_all()
        run = db.query(CopilotRun).filter(CopilotRun.run_id == run.run_id).one()
        reservation = db.query(QuotaReservation).filter(QuotaReservation.id == reservation_id).one()
        db.refresh(hosted_user)
        assert run.status == "completed"
        assert hosted_user.generation_quota == 1
        assert reservation.charged_count == 1
        assert reservation.released_at is not None

    @pytest.mark.asyncio
    async def test_execute_copilot_run_refunds_failed_hosted_run(self, db, novel, hosted_user, monkeypatch):
        import app.database as db_mod
        import app.core.copilot as copilot_mod
        from app.core.auth import open_quota_reservation
        from app.core.copilot import create_run, execute_copilot_run, open_or_reuse_session

        novel.owner_id = hosted_user.id
        db.commit()

        session, _ = open_or_reuse_session(db, novel.id, hosted_user.id, "research", "whole_book", None, "zh", "")
        reservation_id = open_quota_reservation(db, hosted_user.id, count=1)
        run = create_run(db, session, hosted_user.id, "这次会失败", quota_reservation_id=reservation_id)

        async def broken_tool_loop(*_args, **_kwargs):
            raise RuntimeError("tool loop failed")

        async def broken_one_shot(*_args, **_kwargs):
            raise RuntimeError("one-shot failed")

        monkeypatch.setattr(db_mod, "SessionLocal", TestingSessionLocal)
        monkeypatch.setattr(copilot_mod, "gather_evidence", lambda *_args, **_kwargs: [])
        monkeypatch.setattr(copilot_mod, "_run_tool_loop", broken_tool_loop)
        monkeypatch.setattr(copilot_mod, "_run_one_shot", broken_one_shot)

        await execute_copilot_run(run.run_id, novel.id, hosted_user.id, llm_config={"billing_source_hint": "selfhost"})

        db.expire_all()
        run = db.query(CopilotRun).filter(CopilotRun.run_id == run.run_id).one()
        reservation = db.query(QuotaReservation).filter(QuotaReservation.id == reservation_id).one()
        db.refresh(hosted_user)
        assert run.status == "error"
        assert hosted_user.generation_quota == 2
        assert reservation.charged_count == 0
        assert reservation.released_at is not None


class TestPromptContracts:
    def test_run_create_keeps_quick_action_prefix_out_of_response_prompt(self, client, db, novel, monkeypatch):
        from app.api import copilot as copilot_api

        session_resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions",
            json={"mode": "research", "scope": "whole_book"},
        )
        assert session_resp.status_code == 200
        session_id = session_resp.json()["session_id"]

        scheduled: list[object] = []

        def fake_create_task(coro):
            scheduled.append(coro)
            coro.close()
            return object()

        monkeypatch.setattr(copilot_api.asyncio, "create_task", fake_create_task)

        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs",
            json={
                "prompt": "请盘点当前世界模型的缺口。",
                "quick_action_id": "scan_world_gaps",
            },
        )
        assert resp.status_code == 202

        payload = resp.json()
        run = db.query(CopilotRun).filter(CopilotRun.run_id == payload["run_id"]).one()
        assert payload["prompt"] == "请盘点当前世界模型的缺口。"
        assert run.prompt == "请盘点当前世界模型的缺口。"
        assert run.quick_action_id == "scan_world_gaps"
        assert len(scheduled) == 1

    @pytest.mark.asyncio
    async def test_execute_copilot_run_uses_internal_quick_action_prompt(self, db, novel, monkeypatch):
        import app.database as db_mod
        import app.core.copilot as copilot_mod

        from app.core.copilot import create_run, execute_copilot_run, open_or_reuse_session

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")
        run = create_run(
            db,
            session,
            1,
            "请盘点当前世界模型的缺口。",
            quick_action_id="scan_world_gaps",
        )

        captured_prompts: list[str] = []

        async def fake_run_tool_loop(_db_factory, _novel_id, _session_data, prompt, *_args, **_kwargs):
            captured_prompts.append(prompt)
            return {"answer": "完成", "suggestions": []}, [], None

        monkeypatch.setattr(db_mod, "SessionLocal", TestingSessionLocal)
        monkeypatch.setattr(copilot_mod, "gather_evidence", lambda *_args, **_kwargs: [])
        monkeypatch.setattr(copilot_mod, "_run_tool_loop", fake_run_tool_loop)
        monkeypatch.setattr(copilot_mod, "compile_suggestions", lambda *_args, **_kwargs: [])

        await execute_copilot_run(run.run_id, novel.id, 1, llm_config={"billing_source_hint": "selfhost"})

        db.expire_all()
        run = db.query(CopilotRun).filter(CopilotRun.run_id == run.run_id).one()
        assert run.status == "completed"
        assert run.prompt == "请盘点当前世界模型的缺口。"
        assert captured_prompts == [
            "[研究重点: 重点找出世界模型中尚未覆盖但章节反复提到的设定、组织或概念。]\n\n请盘点当前世界模型的缺口。",
        ]

    @pytest.mark.asyncio
    async def test_execute_copilot_run_uses_run_context_snapshot_after_session_retarget(self, db, novel, entities, monkeypatch):
        import app.database as db_mod
        import app.core.copilot as copilot_mod

        from app.core.copilot import create_run, execute_copilot_run, open_or_reuse_session

        studio_context = {"entity_id": entities[0].id, "surface": "studio", "stage": "entity"}
        atlas_context = {"entity_id": entities[0].id, "surface": "atlas", "tab": "entities"}

        session, _ = open_or_reuse_session(
            db,
            novel.id,
            1,
            "current_entity",
            "current_entity",
            studio_context,
            "zh",
            "张三",
        )
        run = create_run(db, session, 1, "分析张三")

        reused, created = open_or_reuse_session(
            db,
            novel.id,
            1,
            "current_entity",
            "current_entity",
            atlas_context,
            "zh",
            "张三 Atlas",
        )
        assert created is False
        assert reused.session_id == session.session_id

        captured_contexts: list[dict | None] = []

        def fail_after_capturing_context(_db, _novel, _mode, _scope, context):
            captured_contexts.append(context)
            raise RuntimeError("stop after context capture")

        monkeypatch.setattr(db_mod, "SessionLocal", TestingSessionLocal)
        monkeypatch.setattr(copilot_mod, "load_scope_snapshot", fail_after_capturing_context)

        await execute_copilot_run(run.run_id, novel.id, 1, llm_config={"billing_source_hint": "selfhost"})

        db.expire_all()
        run = db.query(CopilotRun).filter(CopilotRun.run_id == run.run_id).one()
        session = db.query(CopilotSession).filter(CopilotSession.session_id == session.session_id).one()

        assert captured_contexts == [studio_context]
        assert run.context_json == studio_context
        assert session.context_json == atlas_context
        assert run.status == "error"


# ===========================================================================
# Scope snapshot + prompt tests
# ===========================================================================


class TestScopeAndPrompt:
    def test_whole_book_loads_all(self, db, novel, entities, relationships, systems, chapters):
        from app.core.copilot import load_scope_snapshot
        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        assert len(snapshot.entities) >= 3
        assert len(snapshot.relationships) >= 1
        assert len(snapshot.systems) >= 1

    def test_current_entity_scopes_to_neighbors(self, db, novel, entities, relationships, chapters):
        from app.core.copilot import load_scope_snapshot
        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        ids = {e.id for e in snapshot.entities}
        assert entities[0].id in ids
        assert entities[1].id in ids  # relationship partner

    def test_relationship_current_tab_uses_focused_research_profile(self, db, novel, entities, relationships, systems):
        from app.core.copilot import load_scope_snapshot

        extra = WorldEntity(
            novel_id=novel.id,
            name="赵六",
            entity_type="Character",
            description="路人",
            aliases=[],
            status="confirmed",
            origin="manual",
        )
        db.add(extra)
        db.commit()
        db.refresh(extra)

        noise_rel = WorldRelationship(
            novel_id=novel.id,
            source_id=entities[1].id,
            target_id=extra.id,
            label="同伙",
            label_canonical="同伙",
            description="和张三无关",
            status="confirmed",
            origin="manual",
        )
        db.add(noise_rel)
        db.commit()

        snapshot = load_scope_snapshot(
            db,
            novel,
            "research",
            "current_tab",
            {"entity_id": entities[0].id, "tab": "relationships"},
        )

        ids = {entity.id for entity in snapshot.entities}
        assert snapshot.profile == "focused_research"
        assert snapshot.focus_variant == "relationship"
        assert entities[0].id in ids
        assert entities[1].id in ids
        assert entities[2].id not in ids
        assert extra.id not in ids
        assert snapshot.systems == []
        assert {relationship.id for relationship in snapshot.relationships} == {relationships[0].id}

    def test_draft_cleanup_exposes_drafts(self, db, novel, entities, chapters):
        from app.core.copilot import load_scope_snapshot
        snapshot = load_scope_snapshot(db, novel, "draft_cleanup", "whole_book", None)
        assert len(snapshot.draft_entities) > 0

    def test_draft_cleanup_current_tab_isolates_to_draft_workset(self, db, novel, entities, relationships, systems):
        from app.core.copilot import load_scope_snapshot

        draft_relationship = WorldRelationship(
            novel_id=novel.id,
            source_id=entities[2].id,
            target_id=entities[0].id,
            label="待确认同门",
            label_canonical="待确认同门",
            description="仅草稿工作需要",
            status="draft",
            origin="bootstrap",
        )
        draft_system = WorldSystem(
            novel_id=novel.id,
            name="未定法则",
            display_type="list",
            description="待补完",
            constraints=[],
            status="draft",
            origin="bootstrap",
        )
        db.add_all([draft_relationship, draft_system])
        db.commit()
        db.refresh(draft_relationship)
        db.refresh(draft_system)

        snapshot = load_scope_snapshot(
            db,
            novel,
            "draft_cleanup",
            "current_tab",
            {"tab": "review"},
        )

        ids = {entity.id for entity in snapshot.entities}
        assert snapshot.profile == "draft_governance"
        assert snapshot.focus_variant == "draft"
        assert entities[2].id in ids
        assert entities[0].id in ids  # supporting endpoint for the draft relationship
        assert entities[1].id not in ids
        assert {relationship.id for relationship in snapshot.relationships} == {draft_relationship.id}
        assert {system.id for system in snapshot.systems} == {draft_system.id}
        assert relationships[0].id not in {relationship.id for relationship in snapshot.relationships}
        assert systems[0].id not in {system.id for system in snapshot.systems}

    def test_prompt_contains_evidence_refs(self, db, novel, entities, chapters):
        from app.core.copilot import build_copilot_system_prompt, gather_evidence, load_scope_snapshot
        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)
        prompt = build_copilot_system_prompt(
            snapshot, evidence, "whole_book", "zh",
            {"context_json": {"surface": "atlas", "tab": "systems"}, "display_title": "全书探索"},
            "task_query",
        )
        assert "[Evidence#" in prompt
        assert "cited_evidence_indices" in prompt

    def test_whole_book_prompt_stays_thin(self, db, novel, entities, relationships, systems, chapters):
        from app.core.copilot import build_copilot_system_prompt, gather_evidence, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)
        prompt = build_copilot_system_prompt(
            snapshot,
            evidence,
            "whole_book",
            "zh",
            {"context_json": {"surface": "atlas", "tab": "systems"}, "display_title": "全书探索"},
            "task_query",
        )

        assert "已加载全书概览" in prompt
        assert f"[Entity#{entities[0].id}]" not in prompt
        assert f"[Rel#{relationships[0].id}]" not in prompt
        assert "按需检索或展开证据" in prompt

    def test_entity_prompt_explicitly_mentions_non_character_entity_types(self, db, novel, entities):
        from app.core.copilot import _build_tool_loop_system_prompt, derive_scenario, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        prompt = _build_tool_loop_system_prompt(
            snapshot,
            derive_scenario("current_entity", "current_entity", {"entity_id": entities[0].id}),
            "zh",
            {"context_json": {"entity_id": entities[0].id}, "display_title": entities[0].name},
            "task_query",
        )

        assert "不只包括人物" in prompt
        assert "势力、地点、组织、物件、概念" in prompt

    def test_multilingual_prompt_preserves_canonical(self, db, novel, entities, chapters):
        from app.core.copilot import build_copilot_system_prompt, gather_evidence, load_scope_snapshot
        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)
        prompt = build_copilot_system_prompt(
            snapshot, evidence, "whole_book", "en",
            {"context_json": {"surface": "atlas", "tab": "systems"}, "display_title": "全书探索"},
            "task_query",
        )
        assert "canonical" in prompt.lower() or "原语言" in prompt
        assert "张三" in prompt  # Chinese entity name preserved

    def test_english_prompt_localizes_instruction_scaffold(self, db, novel, entities, chapters):
        from app.core.copilot import build_copilot_system_prompt, gather_evidence, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None, interaction_locale="en")
        prompt = build_copilot_system_prompt(
            snapshot,
            evidence,
            "whole_book",
            "en",
            {"context_json": {"surface": "atlas", "tab": "systems"}, "display_title": "World sweep"},
            "task_query",
        )

        assert "You are a novel world-model research assistant" in prompt
        assert "## Current task" in prompt
        assert "## Current workbench context" in prompt
        assert "Canonical names and labels must remain" in prompt
        assert "张三" in prompt

    def test_prompt_explicitly_allows_non_character_entities(self, db, novel, entities, chapters):
        from app.core.copilot import build_copilot_system_prompt, gather_evidence, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)
        prompt = build_copilot_system_prompt(
            snapshot, evidence, "whole_book", "zh",
            {"context_json": {"surface": "atlas", "tab": "systems"}, "display_title": "全书探索"},
            "task_query",
        )

        assert "实体不只包括人物" in prompt
        assert "势力、组织、地点、物件、概念、规则" in prompt

    def test_intent_classifier_distinguishes_smalltalk_capability_and_task(self):
        from app.core.copilot import classify_turn_intent

        assert classify_turn_intent("你好") == "smalltalk"
        assert classify_turn_intent("你现在能做什么？") == "capability_query"
        assert classify_turn_intent("梳理一下张三和李四的关系") == "task_query"

    def test_smalltalk_prompt_uses_light_workbench_context(self, db, novel, entities, chapters):
        from app.core.copilot import build_copilot_system_prompt, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        prompt = build_copilot_system_prompt(
            snapshot,
            [],
            "current_entity",
            "zh",
            {"context_json": {"surface": "studio", "stage": "entity", "entity_id": entities[0].id}, "display_title": "张三"},
            "smalltalk",
        )
        assert "当前界面：Studio / 实体检查" in prompt
        assert "不要主动生成 suggestions" in prompt
        assert "## 世界模型" not in prompt

    def test_draft_governance_evidence_stays_local_to_drafts(self, db, novel, entities, chapters):
        from app.core.copilot import gather_evidence, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "draft_cleanup", "current_tab", {"tab": "review"})
        evidence = gather_evidence(db, novel, snapshot, {"tab": "review"})

        assert any(item.evidence_id.startswith("draft_ent_") for item in evidence)
        assert all(item.source_type != "chapter_excerpt" for item in evidence)

    def test_gather_evidence_localizes_to_english(self, db, novel, entities, chapters):
        from app.core.copilot import gather_evidence, load_scope_snapshot

        snapshot = load_scope_snapshot(db, novel, "current_entity", "current_entity", {"entity_id": entities[0].id})
        evidence = gather_evidence(
            db,
            novel,
            snapshot,
            {"entity_id": entities[0].id},
            interaction_locale="en",
        )

        assert any(item.title.startswith("Chapter ") for item in evidence if item.source_type == "chapter_excerpt")
        assert any(item.title == f"Entity · {entities[0].name}" for item in evidence)
        assert any(item.why_relevant == "Current research target entity" for item in evidence)


# ===========================================================================
# Multilingual targeting safety
# ===========================================================================


class TestMultilingualTargeting:
    def test_display_text_not_used_for_targeting(self, db, novel, entities):
        """Target resolution uses ID, not display text."""
        from app.core.copilot import ScopeSnapshot, compile_suggestions
        snapshot = ScopeSnapshot(
            novel=novel, novel_language="zh", entities=entities, entities_by_id={e.id: e for e in entities},
            relationships=[], systems=[], attributes_by_entity={},
            draft_entities=[], draft_relationships=[], draft_systems=[],
        )
        raw = [{"kind": "update_entity", "title": "x", "summary": "x", "target_resource": "entity", "target_id": None, "delta": {"description": "x"}}]
        compiled = compile_suggestions(raw, [], snapshot, "research", "current_entity")
        # target_id is None for update → can't resolve → advisory
        assert compiled[0].preview["actionable"] is False


# ===========================================================================
# Run poll tests
# ===========================================================================


class TestRunPoll:
    def test_poll_returns_backend_evidence(self, client, db, novel):
        session = CopilotSession(session_id="sess-poll", novel_id=novel.id, user_id=1, mode="research", scope="whole_book", interaction_locale="zh", signature="sig-p", display_title="")
        db.add(session)
        db.commit()
        db.refresh(session)
        run = CopilotRun(
            run_id="run-poll", copilot_session_id=session.id, novel_id=novel.id, user_id=1,
            status="completed", prompt="test", answer="分析完成",
            evidence_json=[{
                "evidence_id": "ev_0", "source_type": "chapter_excerpt",
                "source_ref": {"chapter_id": 1, "chapter_number": 1, "start_pos": 0, "end_pos": 100},
                "title": "第1章", "excerpt": "关键文本", "why_relevant": "相关",
                "pack_id": "pk_ch_1",
                "source_refs": [{"type": "chapter", "chapter_id": 1, "chapter_number": 1, "start_pos": 0, "end_pos": 100}],
                "anchor_terms": ["帝国", "军团"],
                "support_count": 2,
                "preview_excerpt": "关键文本",
                "expanded": True,
            }],
            suggestions_json=[],
        )
        db.add(run)
        db.commit()
        resp = client.get(f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/{run.run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["answer"] == "分析完成"
        assert len(data["evidence"]) == 1
        assert data["evidence"][0]["source_ref"]["chapter_id"] == 1
        assert data["evidence"][0]["pack_id"] == "pk_ch_1"
        assert data["evidence"][0]["anchor_terms"] == ["帝国", "军团"]
        assert data["evidence"][0]["expanded"] is True

    def test_poll_nonexistent_returns_404(self, client, db, novel):
        session = CopilotSession(session_id="sess-p404", novel_id=novel.id, user_id=1, mode="research", scope="whole_book", interaction_locale="zh", signature="sig-p404", display_title="")
        db.add(session)
        db.commit()
        resp = client.get(f"/api/novels/{novel.id}/world/copilot/sessions/{session.session_id}/runs/nonexistent")
        assert resp.status_code == 404


# ===========================================================================
# Scenario derivation (clean abstraction)
# ===========================================================================


class TestScenarioDerivation:
    def test_derive_scenarios(self):
        from app.core.copilot import derive_scenario
        assert derive_scenario("draft_cleanup", "whole_book", None) == "draft_cleanup"
        assert derive_scenario("research", "whole_book", None) == "whole_book"
        assert derive_scenario("current_entity", "current_entity", {"tab": "relationships"}) == "relationships"
        assert derive_scenario("current_entity", "current_entity", {"entity_id": 1}) == "current_entity"

    def test_derive_runtime_profiles(self):
        from app.core.copilot import derive_runtime_profile

        assert derive_runtime_profile("draft_cleanup", "current_tab", {"tab": "review"}) == "draft_governance"
        assert derive_runtime_profile("research", "whole_book", None) == "broad_exploration"
        assert derive_runtime_profile("research", "current_tab", {"entity_id": 1, "tab": "relationships"}) == "focused_research"


# ===========================================================================
# Tool dispatch tests (pure unit, real DB, no LLM)
# ===========================================================================


class TestToolDispatch:
    def _make_snapshot(self, db, novel, entities=None, relationships=None, systems=None):
        from app.core.copilot import load_scope_snapshot
        return load_scope_snapshot(db, novel, "research", "whole_book", None)

    def test_tool_find_by_entity_name(self, db, novel, entities, chapters):
        from app.core.copilot import Workspace, _tool_find
        workspace = Workspace()
        result = _tool_find("张三", "all", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        import json
        data = json.loads(result)
        assert data["total_found"] > 0
        # Should have found world rows matching 张三
        pack_ids = [p["pack_id"] for p in data["packs"]]
        assert any("ent_" in pid for pid in pack_ids)

    def test_tool_find_by_alias(self, db, novel, entities, chapters):
        from app.core.copilot import Workspace, _tool_find
        workspace = Workspace()
        result = _tool_find("三哥", "all", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        import json
        data = json.loads(result)
        assert data["total_found"] > 0

    def test_tool_find_drafts_returns_quality_signals(self, db, novel, entities, chapters):
        from app.core.copilot import Workspace, _tool_find
        workspace = Workspace()
        result = _tool_find("草稿", "drafts", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        import json
        data = json.loads(result)
        # entities[2] (王五) is draft with empty description
        has_draft = any("draft" in p.get("pack_id", "") for p in data["packs"])
        assert has_draft

    def test_tool_find_drafts_localizes_quality_signals_to_english(self, db, novel, entities, chapters):
        from app.core.copilot import Workspace, _tool_find

        workspace = Workspace()
        result = _tool_find("draft", "drafts", db, novel.id, novel, self._make_snapshot(db, novel), workspace, interaction_locale="en")
        import json
        data = json.loads(result)

        assert data["total_found"] > 0
        pack = workspace.evidence_packs[data["packs"][0]["pack_id"]]
        assert "[Draft" in pack.preview_excerpt
        assert any(issue in pack.preview_excerpt for issue in ("Missing description", "No aliases", "No attributes"))

    def test_tool_find_whole_book_prioritizes_world_rows(self, db, novel, entities, chapters):
        from app.core.copilot import Workspace, _tool_find
        workspace = Workspace()
        result = _tool_find("张三", "world_rows", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        import json
        data = json.loads(result)
        assert data["total_found"] > 0
        # World row packs should have entity-based pack IDs
        assert any("ent_" in p["pack_id"] for p in data["packs"])

    def test_tool_find_unknown_query_falls_back_to_story_text(self, db, novel, entities, chapters):
        from app.core.copilot import Workspace, _tool_find
        workspace = Workspace()
        # Search for something in chapter content but not in entity names
        result = _tool_find("宗门修行", "story_text", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        import json
        data = json.loads(result)
        assert data["total_found"] > 0

    def test_tool_find_all_scope_can_return_chapter_only_results(self, db, novel, entities, chapters):
        from app.core.copilot import Workspace, _tool_find

        chapters[0].content = "第一章写到远古星门重新开启。"
        db.commit()

        workspace = Workspace()
        result = _tool_find("远古星门", "all", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        import json
        data = json.loads(result)

        assert data["total_found"] > 0
        pack_id = data["packs"][0]["pack_id"]
        pack = workspace.evidence_packs[pack_id]
        assert pack.source_refs[0]["type"] == "chapter"
        assert pack.source_refs[0]["chapter_number"] == 1

    def test_tool_find_story_text_keyword_bag_scans_whole_book_not_just_latest_chapters(self, db, novel, entities, chapters):
        from app.core.copilot import Workspace, _tool_find

        db.add_all([
            Chapter(novel_id=novel.id, chapter_number=4, title="第4章", content="这是后续章节，没有目标词。"),
            Chapter(novel_id=novel.id, chapter_number=5, title="第5章", content="这是后续章节，仍然没有目标词。"),
            Chapter(novel_id=novel.id, chapter_number=6, title="第6章", content="这是最新章节，也没有目标词。"),
        ])
        chapters[0].content = "第一章写到远古星门重新开启，帝国军团开始调动。"
        db.commit()

        workspace = Workspace()
        result = _tool_find("帝国 远古星门", "story_text", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        import json
        data = json.loads(result)

        assert data["total_found"] > 0
        pack_id = data["packs"][0]["pack_id"]
        pack = workspace.evidence_packs[pack_id]
        assert pack.source_refs[0]["chapter_number"] == 1
        assert set(pack.anchor_terms) >= {"帝国", "远古星门"}

    def test_tool_find_world_rows_supports_multi_term_queries(self, db, novel, entities, chapters):
        from app.core.copilot import Workspace, _tool_find

        entities[1].description = "帝国军团中的统帅人物"
        db.commit()

        workspace = Workspace()
        result = _tool_find("帝国 军团", "world_rows", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        import json
        data = json.loads(result)

        assert data["total_found"] > 0
        assert any("ent_" in p["pack_id"] for p in data["packs"])

    def test_tool_open_expands_known_pack(self, db, novel, entities, chapters):
        from app.core.copilot import Workspace, _tool_find, _tool_open
        workspace = Workspace()
        # First find to populate packs
        _tool_find("张三", "all", db, novel.id, novel, self._make_snapshot(db, novel), workspace)
        assert len(workspace.evidence_packs) > 0
        pack_id = next(iter(workspace.evidence_packs))
        result = _tool_open(pack_id, 2000, db, novel, workspace)
        import json
        data = json.loads(result)
        assert data["pack_id"] == pack_id
        assert "error" not in data

    def test_tool_open_rejects_unknown_pack(self, db, novel, entities, chapters):
        from app.core.copilot import Workspace, _tool_open
        workspace = Workspace()
        result = _tool_open("nonexistent_pack", 2000, db, novel, workspace)
        import json
        data = json.loads(result)
        assert "error" in data

    def test_tool_open_rejects_unknown_pack_in_english(self, db, novel, entities, chapters):
        from app.core.copilot import Workspace, _tool_open

        workspace = Workspace()
        result = _tool_open("nonexistent_pack", 2000, db, novel, workspace, interaction_locale="en")
        import json
        data = json.loads(result)

        assert data["error"] == "Unknown pack_id: nonexistent_pack. Use find() first."

    def test_tool_read_returns_live_entity_state(self, db, novel, entities, attributes):
        from app.core.copilot import _tool_read
        snapshot = self._make_snapshot(db, novel)
        result = _tool_read([{"type": "entity", "id": entities[0].id}], db, novel.id, snapshot)
        import json
        data = json.loads(result)
        assert len(data["results"]) == 1
        assert data["results"][0]["name"] == "张三"
        assert data["results"][0]["type"] == "entity"

    def test_tool_read_returns_live_relationship_state(self, db, novel, entities, relationships):
        from app.core.copilot import _tool_read
        snapshot = self._make_snapshot(db, novel)
        result = _tool_read([{"type": "relationship", "id": relationships[0].id}], db, novel.id, snapshot)
        import json
        data = json.loads(result)
        assert len(data["results"]) == 1
        assert data["results"][0]["label"] == "对手"


# ===========================================================================
# EvidencePack tests
# ===========================================================================


class TestEvidencePack:
    def test_pack_id_includes_content_hash(self):
        from app.core.copilot import _make_pack_id
        id1 = _make_pack_id("pk_ent_1", "content A")
        id2 = _make_pack_id("pk_ent_1", "content B")
        assert id1 != id2
        # Same content → same ID
        id3 = _make_pack_id("pk_ent_1", "content A")
        assert id1 == id3

    def test_overlapping_windows_deduplicate(self):
        from app.core.copilot import EvidencePack, _deduplicate_packs
        p1 = EvidencePack(pack_id="pk_1", source_refs=[], preview_excerpt="a", anchor_terms=[], support_count=2, related_targets=[])
        p2 = EvidencePack(pack_id="pk_1", source_refs=[], preview_excerpt="a", anchor_terms=[], support_count=1, related_targets=[])
        p3 = EvidencePack(pack_id="pk_2", source_refs=[], preview_excerpt="b", anchor_terms=[], support_count=1, related_targets=[])
        result = _deduplicate_packs([p1, p2, p3])
        assert len(result) == 2
        # Should keep the one with higher support_count
        by_id = {p.pack_id: p for p in result}
        assert by_id["pk_1"].support_count == 2


# ===========================================================================
# Agent loop tests (mock generate_with_tools)
# ===========================================================================


class TestAgentLoop:
    @pytest.fixture
    def mock_setup(self, db, novel, entities, chapters):
        """Set up session and run for agent loop tests."""
        from app.core.copilot import open_or_reuse_session, create_run
        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")
        run = create_run(db, session, 1, "分析张三")
        session_data = {
            "mode": session.mode, "scope": session.scope,
            "context_json": run.context_json, "interaction_locale": session.interaction_locale,
        }
        return session_data, run.prompt, session, run

    @pytest.mark.asyncio
    async def test_happy_path_auto_preload_then_find_then_answer(self, db, novel, entities, chapters, mock_setup, monkeypatch):
        from app.core.copilot import _run_tool_loop
        from app.core.ai_client import ToolLLMResponse, ToolCall

        session_data, prompt, session, run = mock_setup
        from app.core.copilot import load_scope_snapshot, gather_evidence, derive_scenario
        snapshot = load_scope_snapshot(db, novel, session.mode, session.scope, session.context_json)
        evidence = gather_evidence(db, novel, snapshot, session.context_json)
        scenario = derive_scenario(session.mode, session.scope, session.context_json)

        call_count = 0

        async def mock_generate_with_tools(self_client, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: agent uses find tool
                return ToolLLMResponse(
                    content=None,
                    tool_calls=[ToolCall(id="call_1", name="find", arguments='{"query": "张三"}')],
                    finish_reason="tool_calls",
                )
            else:
                # Second call: final answer
                return ToolLLMResponse(
                    content='{"answer": "张三是主角", "suggestions": []}',
                    tool_calls=[],
                    finish_reason="stop",
                )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate_with_tools)
        monkeypatch.setattr("app.core.copilot.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.copilot.release_llm_slot", lambda: None)

        def test_db_factory():
            return db

        parsed, tool_evidence, workspace = await _run_tool_loop(
            test_db_factory, novel.id, session_data, prompt, None, 1, snapshot, scenario, evidence, "task_query",
        )
        assert parsed["answer"] == "张三是主角"
        assert workspace.tool_call_count >= 1

    @pytest.mark.asyncio
    async def test_executes_all_tool_calls_from_single_model_turn(self, db, novel, entities, chapters, mock_setup, monkeypatch):
        from app.core.copilot import _run_tool_loop
        from app.core.ai_client import ToolLLMResponse, ToolCall

        session_data, prompt, session, run = mock_setup
        from app.core.copilot import load_scope_snapshot, gather_evidence, derive_scenario
        snapshot = load_scope_snapshot(db, novel, session.mode, session.scope, session.context_json)
        evidence = gather_evidence(db, novel, snapshot, session.context_json)
        scenario = derive_scenario(session.mode, session.scope, session.context_json)

        call_count = 0
        captured_messages = []

        async def mock_generate_with_tools(self_client, **kwargs):
            nonlocal call_count
            call_count += 1
            captured_messages.append(kwargs.get("messages", []))
            if call_count == 1:
                return ToolLLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCall(id="call_1", name="load_scope_snapshot", arguments="{}"),
                        ToolCall(id="call_2", name="find", arguments='{"query": "张三"}'),
                    ],
                    finish_reason="tool_calls",
                )
            return ToolLLMResponse(
                content='{"answer": "done", "suggestions": []}',
                tool_calls=[],
                finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate_with_tools)
        monkeypatch.setattr("app.core.copilot.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.copilot.release_llm_slot", lambda: None)

        parsed, _, workspace = await _run_tool_loop(
            lambda: db, novel.id, session_data, prompt, None, 1, snapshot, scenario, evidence, "task_query",
        )

        assert parsed["answer"] == "done"
        assert workspace.tool_call_count == 2
        assert [entry["tool"] for entry in workspace.tool_journal] == ["load_scope_snapshot", "find"]
        assert len(captured_messages) == 2
        second_turn_messages = captured_messages[1]
        assert len([m for m in second_turn_messages if m["role"] == "tool"]) == 2
        assistant_with_tools = next(m for m in second_turn_messages if m["role"] == "assistant" and "tool_calls" in m)
        assert len(assistant_with_tools["tool_calls"]) == 2

    @pytest.mark.asyncio
    async def test_budget_exhaustion_forces_wrap_up(self, db, novel, entities, chapters, mock_setup, monkeypatch):
        from app.core.copilot import _run_tool_loop
        from app.core.ai_client import ToolLLMResponse, ToolCall

        session_data, prompt, session, run = mock_setup
        from app.core.copilot import load_scope_snapshot, gather_evidence, derive_scenario
        snapshot = load_scope_snapshot(db, novel, session.mode, session.scope, session.context_json)
        evidence = gather_evidence(db, novel, snapshot, session.context_json)
        scenario = derive_scenario(session.mode, session.scope, session.context_json)

        call_count = 0

        async def mock_generate_with_tools(self_client, **kwargs):
            nonlocal call_count
            call_count += 1
            tool_choice = kwargs.get("tool_choice")
            if tool_choice == "none":
                # Forced wrap-up
                return ToolLLMResponse(
                    content='{"answer": "预算用尽", "suggestions": []}',
                    tool_calls=[],
                    finish_reason="stop",
                )
            # Always request a tool call to exhaust budget
            return ToolLLMResponse(
                content=None,
                tool_calls=[ToolCall(id=f"call_{call_count}", name="find", arguments='{"query": "test"}')],
                finish_reason="tool_calls",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate_with_tools)
        monkeypatch.setattr("app.core.copilot.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.copilot.release_llm_slot", lambda: None)

        # Override max rounds to 2 for faster test
        monkeypatch.setattr("app.config.Settings.copilot_max_tool_rounds", 2, raising=False)

        def test_db_factory():
            return db

        parsed, _, workspace = await _run_tool_loop(
            test_db_factory, novel.id, session_data, prompt, None, 1, snapshot, scenario, evidence, "task_query",
        )
        assert parsed["answer"] == "预算用尽"

    @pytest.mark.asyncio
    async def test_workspace_persisted_after_each_step(self, db, novel, entities, chapters, mock_setup, monkeypatch):
        from app.core.copilot import _run_tool_loop
        from app.core.ai_client import ToolLLMResponse, ToolCall

        session_data, prompt, session, run = mock_setup

        from app.core.copilot import load_scope_snapshot, gather_evidence, derive_scenario
        snapshot = load_scope_snapshot(db, novel, session.mode, session.scope, session.context_json)
        evidence = gather_evidence(db, novel, snapshot, session.context_json)
        scenario = derive_scenario(session.mode, session.scope, session.context_json)

        persist_calls = []

        def mock_persist(db_factory, run_id, workspace, **kwargs):
            persist_calls.append(run_id)
            return True

        monkeypatch.setattr("app.core.copilot._persist_workspace", mock_persist)

        call_count = 0

        async def mock_generate_with_tools(self_client, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ToolLLMResponse(
                    content=None,
                    tool_calls=[ToolCall(id="c1", name="find", arguments='{"query": "test"}')],
                    finish_reason="tool_calls",
                )
            return ToolLLMResponse(
                content='{"answer": "done", "suggestions": []}',
                tool_calls=[],
                finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate_with_tools)
        monkeypatch.setattr("app.core.copilot.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.copilot.release_llm_slot", lambda: None)

        def test_db_factory():
            return db

        await _run_tool_loop(
            test_db_factory, novel.id, session_data, prompt, None, 1, snapshot, scenario, evidence, "task_query",
            run_id="test-persist-run",
        )
        assert len(persist_calls) >= 1

    @pytest.mark.asyncio
    async def test_smalltalk_turn_skips_auto_preload_dump(self, db, novel, entities, chapters, monkeypatch):
        from app.core.copilot import _run_tool_loop, derive_scenario, load_scope_snapshot
        from app.core.ai_client import ToolLLMResponse

        snapshot = load_scope_snapshot(
            db, novel, "current_entity", "current_entity",
            {"entity_id": entities[0].id, "surface": "studio", "stage": "entity"},
        )
        scenario = derive_scenario("current_entity", "current_entity", {"entity_id": entities[0].id})
        captured_messages = []

        async def mock_generate_with_tools(self_client, **kwargs):
            captured_messages.append(kwargs.get("messages", []))
            return ToolLLMResponse(
                content='{"answer": "你好，我现在在实体检查界面", "suggestions": []}',
                tool_calls=[],
                finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate_with_tools)
        monkeypatch.setattr("app.core.copilot.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.copilot.release_llm_slot", lambda: None)

        parsed, _, _ = await _run_tool_loop(
            lambda: db,
            novel.id,
            {
                "mode": "current_entity",
                "scope": "current_entity",
                "context_json": {"entity_id": entities[0].id, "surface": "studio", "stage": "entity"},
                "interaction_locale": "zh",
                "display_title": "张三",
            },
            "你好",
            None,
            1,
            snapshot,
            scenario,
            [],
            "smalltalk",
        )

        assert parsed["answer"].startswith("你好")
        assert len(captured_messages) == 1
        assert "[Auto-preloaded world model summary]" not in captured_messages[0][1]["content"]


# ===========================================================================
# Degradation tests (mock AIClient)
# ===========================================================================


class TestDegradation:
    @pytest.fixture
    def mock_session_and_run(self, db, novel, entities, chapters):
        from app.core.copilot import open_or_reuse_session, create_run
        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")
        run = create_run(db, session, 1, "测试降级")
        return session, run

    @pytest.mark.asyncio
    async def test_tool_unsupported_degrades_to_one_shot(self, db, novel, entities, chapters, mock_session_and_run, monkeypatch):
        from app.core.ai_client import ToolCallUnsupportedError

        session, run = mock_session_and_run

        one_shot_called = False

        async def mock_tool_loop(*args, **kwargs):
            raise ToolCallUnsupportedError("tools not supported")

        async def mock_one_shot(snapshot, evidence, scenario, session_data, turn_intent, prompt, llm_config, user_id, **kwargs):
            nonlocal one_shot_called
            one_shot_called = True
            return {"answer": "one-shot fallback", "suggestions": []}, evidence

        monkeypatch.setattr("app.core.copilot._run_tool_loop", mock_tool_loop)
        monkeypatch.setattr("app.core.copilot._run_one_shot", mock_one_shot)
        monkeypatch.setattr("app.core.copilot.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.copilot.release_llm_slot", lambda: None)

        from app.core.copilot import execute_copilot_run
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        await execute_copilot_run(run.run_id, novel.id, 1, None)
        assert one_shot_called
        db.refresh(run)
        assert run.status == "completed"
        assert any(
            step["summary"] == "当前模型不支持分步检索，已切换为直接分析"
            for step in (run.trace_json or [])
        )

        db.close = original_close

    @pytest.mark.asyncio
    async def test_tool_unsupported_degrades_to_one_shot_with_english_trace(self, db, novel, entities, chapters, monkeypatch):
        from app.core.ai_client import ToolCallUnsupportedError
        from app.core.copilot import create_run, execute_copilot_run, open_or_reuse_session

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "en", "")
        run = create_run(db, session, 1, "Summarize the world")

        async def mock_tool_loop(*args, **kwargs):
            raise ToolCallUnsupportedError("tools not supported")

        async def mock_one_shot(snapshot, evidence, scenario, session_data, turn_intent, prompt, llm_config, user_id, **kwargs):
            return {"answer": "one-shot fallback", "suggestions": []}, evidence

        monkeypatch.setattr("app.core.copilot._run_tool_loop", mock_tool_loop)
        monkeypatch.setattr("app.core.copilot._run_one_shot", mock_one_shot)
        monkeypatch.setattr("app.core.copilot.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.copilot.release_llm_slot", lambda: None)
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        await execute_copilot_run(run.run_id, novel.id, 1, None)

        db.refresh(run)
        assert run.status == "completed"
        assert any(
            step["summary"] == "The current model does not support multi-step retrieval, so the run switched to direct analysis"
            for step in (run.trace_json or [])
        )

        db.close = original_close

    @pytest.mark.asyncio
    async def test_both_paths_fail_marks_run_error(self, db, novel, entities, chapters, mock_session_and_run, monkeypatch):
        """When both tool-loop and one-shot fail, run is marked as error."""
        from app.core.ai_client import ToolCallUnsupportedError

        session, run = mock_session_and_run

        async def mock_tool_loop(*args, **kwargs):
            raise ToolCallUnsupportedError("tools not supported")

        async def mock_one_shot(*args, **kwargs):
            raise RuntimeError("one-shot also failed")

        monkeypatch.setattr("app.core.copilot._run_tool_loop", mock_tool_loop)
        monkeypatch.setattr("app.core.copilot._run_one_shot", mock_one_shot)
        monkeypatch.setattr("app.core.copilot.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.copilot.release_llm_slot", lambda: None)
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        from app.core.copilot import execute_copilot_run
        await execute_copilot_run(run.run_id, novel.id, 1, None)

        db.refresh(run)
        assert run.status == "error"
        assert run.error is not None

        db.close = original_close

    @pytest.mark.asyncio
    async def test_tool_loop_llm_error_degrades_to_one_shot(self, db, novel, entities, chapters, mock_session_and_run, monkeypatch):
        """When tool loop fails with a non-tool error (e.g. rate limit),
        execution falls back to one-shot instead of dying."""
        session, run = mock_session_and_run

        one_shot_called = False

        async def mock_tool_loop(*args, **kwargs):
            raise RuntimeError("429 rate limit exceeded")

        async def mock_one_shot(snapshot, evidence, scenario, session_data, turn_intent, prompt, llm_config, user_id, **kwargs):
            nonlocal one_shot_called
            one_shot_called = True
            return {"answer": "one-shot after rate limit", "suggestions": []}, evidence

        monkeypatch.setattr("app.core.copilot._run_tool_loop", mock_tool_loop)
        monkeypatch.setattr("app.core.copilot._run_one_shot", mock_one_shot)
        monkeypatch.setattr("app.core.copilot.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.copilot.release_llm_slot", lambda: None)
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        from app.core.copilot import execute_copilot_run
        await execute_copilot_run(run.run_id, novel.id, 1, None)
        assert one_shot_called

        db.refresh(run)
        assert run.status == "completed"
        assert run.answer == "one-shot after rate limit"
        assert any(
            "已切换为直接分析" in step["summary"]
            for step in (run.trace_json or [])
        )

        db.close = original_close

    @pytest.mark.asyncio
    async def test_completed_run_records_tool_trace_steps(self, db, novel, entities, chapters, mock_session_and_run, monkeypatch):
        from app.core.copilot import Workspace, execute_copilot_run

        session, run = mock_session_and_run

        async def mock_tool_loop(
            db_factory, novel_id, session_data, prompt, llm_config, user_id, snapshot, scenario, evidence,
            turn_intent, run_id="", worker_id="", inherited_workspace=None, **kwargs,
        ):
            workspace = Workspace()
            workspace.tool_call_count = 2
            workspace.tool_journal = [
                {
                    "step_id": "tool_1",
                    "kind": "tool_find",
                    "status": "completed",
                    "summary": "搜索「张三」",
                    "tool": "find",
                    "args": {"query": "张三"},
                    "result_summary": '{"total_found": 2}',
                    "round": 1,
                },
                {
                    "step_id": "tool_2",
                    "kind": "tool_read",
                    "status": "completed",
                    "summary": "读取 1 个设定目标，返回 1 条结果",
                    "tool": "read",
                    "args": {"target_refs": [{"type": "entity", "id": entities[0].id}]},
                    "result_summary": '{"results": [{"type": "entity", "id": 1}]}',
                    "round": 1,
                },
            ]
            return {"answer": "done", "suggestions": []}, evidence, workspace

        monkeypatch.setattr("app.core.copilot._run_tool_loop", mock_tool_loop)
        monkeypatch.setattr("app.core.copilot.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.copilot.release_llm_slot", lambda: None)
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        await execute_copilot_run(run.run_id, novel.id, 1, None)

        db.refresh(run)
        summaries = [step["summary"] for step in (run.trace_json or [])]
        assert run.status == "completed"
        assert "本轮通过分步检索整理信息，共执行 2 步" in summaries
        assert "搜索「张三」" in summaries
        assert "读取 1 个设定目标，返回 1 条结果" in summaries

        db.close = original_close

    @pytest.mark.asyncio
    async def test_capability_query_suppresses_model_suggestions(self, db, novel, entities, chapters, monkeypatch):
        from app.core.copilot import create_run, execute_copilot_run, open_or_reuse_session, Workspace

        session, _ = open_or_reuse_session(
            db,
            novel.id,
            1,
            "current_entity",
            "current_entity",
            {"entity_id": entities[0].id, "surface": "studio", "stage": "entity"},
            "zh",
            "张三",
        )
        run = create_run(db, session, 1, "你现在能做什么？")

        async def mock_tool_loop(
            db_factory, novel_id, session_data, prompt, llm_config, user_id, snapshot, scenario, evidence,
            turn_intent, run_id="", worker_id="", inherited_workspace=None, **kwargs,
        ):
            workspace = Workspace()
            return {
                "answer": "我现在在实体检查界面，可以解释当前实体、补充设定、在你明确要求时生成建议卡。",
                "suggestions": [{
                    "kind": "update_entity",
                    "title": "不该出现的建议",
                    "summary": "这条建议应该被抑制",
                    "target_resource": "entity",
                    "target_id": entities[0].id,
                    "delta": {"description": "x"},
                }],
            }, evidence, workspace

        monkeypatch.setattr("app.core.copilot._run_tool_loop", mock_tool_loop)
        monkeypatch.setattr("app.core.copilot.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.copilot.release_llm_slot", lambda: None)
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        await execute_copilot_run(run.run_id, novel.id, 1, None)

        db.refresh(run)
        assert run.status == "completed"
        assert run.answer.startswith("我现在在实体检查界面")
        assert run.suggestions_json == []
        assert run.evidence_json == []

        db.close = original_close


# ===========================================================================
# Extended admission control
# ===========================================================================


class TestCopilotAdmissionControl:
    def test_copilot_per_user_limit_stricter_than_general(self):
        from app.config import get_settings
        from app.core.copilot import MAX_ACTIVE_RUNS_PER_USER
        settings = get_settings()
        assert settings.copilot_max_runs_per_user <= MAX_ACTIVE_RUNS_PER_USER

    def test_global_limit_enforced(self, db, novel):
        from app.core.copilot import CopilotError, create_run, open_or_reuse_session
        from app.config import reload_settings
        import os

        # Use monkeypatch-like approach: set env before reloading settings
        orig = os.environ.get("COPILOT_MAX_RUNS_GLOBAL")
        os.environ["COPILOT_MAX_RUNS_GLOBAL"] = "1"
        try:
            reload_settings()
            s1, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "g1")
            create_run(db, s1, 1, "run 1")
            # Second run from a different user should be blocked by global limit
            user2 = User(id=2, username="user2", hashed_password="x", role="user", is_active=True, generation_quota=999)
            db.add(user2)
            db.commit()
            s2, _ = open_or_reuse_session(db, novel.id, 2, "research", "whole_book", None, "zh", "g2")
            with pytest.raises(CopilotError) as exc_info:
                create_run(db, s2, 2, "run 2")
            assert exc_info.value.code == "too_many_global_runs"
        finally:
            if orig is None:
                os.environ.pop("COPILOT_MAX_RUNS_GLOBAL", None)
            else:
                os.environ["COPILOT_MAX_RUNS_GLOBAL"] = orig
            reload_settings()


# ===========================================================================
# E2E workflow tests (HTTP endpoints, mocked LLM)
# ===========================================================================


class TestE2EWorkflows:
    """E2E tests that exercise the full HTTP endpoint flow.

    These verify user workflows, not code paths:
    - session open → run create → poll → answer + evidence
    - apply contract through HTTP
    - stale run detection via poll
    """

    def test_whole_book_inquiry_returns_answer_and_evidence(self, client, db, novel, entities, chapters):
        """Whole-book inquiry can return answer + evidence without suggestions.
        This is a normal success result, not an error."""
        # Open session
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={
            "mode": "research", "scope": "whole_book",
        })
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # Create a completed run directly in DB (simulates background execution)
        from app.models import CopilotRun, CopilotSession as CS
        cs = db.query(CS).filter(CS.session_id == session_id).first()
        run = CopilotRun(
            run_id="e2e-run-wb", copilot_session_id=cs.id, novel_id=novel.id, user_id=1,
            status="completed", prompt="全书盘点",
            answer="全书存在3个未收束设定缺口",
            evidence_json=[{
                "evidence_id": "ev_0", "source_type": "chapter_excerpt",
                "source_ref": {"chapter_id": chapters[0].id, "chapter_number": 1, "start_pos": 0, "end_pos": 50},
                "title": "第1章", "excerpt": "宗门修行", "why_relevant": "高频线索",
            }],
            suggestions_json=[],  # inquiry-only — no suggestions
        )
        db.add(run)
        db.commit()

        # Poll
        resp = client.get(f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs/{run.run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["answer"] == "全书存在3个未收束设定缺口"
        assert len(data["evidence"]) == 1
        assert len(data["suggestions"]) == 0  # inquiry-only is normal

    def test_current_entity_enrichment_full_flow(self, client, db, novel, entities, attributes, chapters):
        """Entity enrichment workflow: open session → create run → poll → apply suggestion."""
        # Open session scoped to entity
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={
            "mode": "current_entity", "scope": "current_entity",
            "context": {"entity_id": entities[0].id},
            "display_title": entities[0].name,
        })
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # Simulate completed run with suggestion
        from app.models import CopilotRun, CopilotSession as CS
        cs = db.query(CS).filter(CS.session_id == session_id).first()
        run = CopilotRun(
            run_id="e2e-run-ent", copilot_session_id=cs.id, novel_id=novel.id, user_id=1,
            status="completed", prompt="补完张三",
            answer="张三是宗门弟子，建议补充描述和属性",
            evidence_json=[{
                "evidence_id": "ev_0", "source_type": "chapter_excerpt",
                "source_ref": {"chapter_id": chapters[0].id},
                "title": "第1章", "excerpt": "张三在宗门修行", "why_relevant": "直接提及",
            }],
            suggestions_json=[{
                "suggestion_id": "sg_enrich_0", "kind": "update_entity",
                "title": "补充描述", "summary": "基于章节证据补充",
                "evidence_ids": ["ev_0"],
                "target": {"resource": "entity", "resource_id": entities[0].id, "label": "张三", "tab": "entities", "entity_id": entities[0].id},
                "preview": {"target_label": "张三", "summary": "补充描述", "field_deltas": [{"field": "description", "label": "描述", "before": "主角", "after": "宗门弟子，修行天赋卓越"}], "evidence_quotes": ["张三在宗门修行"], "actionable": True},
                "apply": {"type": "update_entity", "entity_id": entities[0].id, "data": {"description": "宗门弟子，修行天赋卓越"}},
                "status": "pending",
            }],
        )
        db.add(run)
        db.commit()

        # Poll — should see suggestion
        resp = client.get(f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs/{run.run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["preview"]["actionable"] is True

        # Apply — this is the approval boundary
        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs/{run.run_id}/apply",
            json={"suggestion_ids": ["sg_enrich_0"]},
        )
        assert resp.status_code == 200
        assert resp.json()["results"][0]["success"] is True

        # Verify world model was actually mutated
        db.refresh(entities[0])
        assert entities[0].description == "宗门弟子，修行天赋卓越"

    def test_draft_cleanup_rejects_non_draft_through_api(self, client, db, novel, entities, chapters):
        """Draft cleanup applied through API respects the draft-only constraint."""
        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={
            "mode": "draft_cleanup", "scope": "whole_book",
        })
        session_id = resp.json()["session_id"]

        from app.models import CopilotRun, CopilotSession as CS
        cs = db.query(CS).filter(CS.session_id == session_id).first()
        # Suggestion targets a confirmed entity — should be advisory only
        run = CopilotRun(
            run_id="e2e-run-dc", copilot_session_id=cs.id, novel_id=novel.id, user_id=1,
            status="completed", prompt="整理草稿",
            answer="已审查", evidence_json=[],
            suggestions_json=[{
                "suggestion_id": "sg_dc_0", "kind": "update_entity",
                "title": "x", "summary": "x", "evidence_ids": [],
                "target": {"resource": "entity", "resource_id": entities[0].id, "label": "张三", "tab": "review"},
                "preview": {"target_label": "张三", "summary": "x", "field_deltas": [], "evidence_quotes": [], "actionable": False},
                "apply": None, "status": "pending",
            }],
        )
        db.add(run)
        db.commit()

        # Apply advisory suggestion → should fail gracefully
        resp = client.post(
            f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs/{run.run_id}/apply",
            json={"suggestion_ids": ["sg_dc_0"]},
        )
        assert resp.status_code == 200
        assert resp.json()["results"][0]["success"] is False
        assert resp.json()["results"][0]["error_code"] == "not_actionable"

    def test_stale_run_detected_on_poll(self, client, db, novel):
        """Stale running run is marked interrupted when polled."""
        from datetime import datetime, timedelta, timezone
        from app.models import CopilotRun, CopilotSession as CS

        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={
            "mode": "research", "scope": "whole_book",
        })
        session_id = resp.json()["session_id"]
        cs = db.query(CS).filter(CS.session_id == session_id).first()

        # Create a run with old updated_at
        run = CopilotRun(
            run_id="e2e-run-stale", copilot_session_id=cs.id, novel_id=novel.id, user_id=1,
            status="running", prompt="test",
        )
        db.add(run)
        db.commit()

        # Manually set updated_at to 10 minutes ago
        old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.execute(
            db.query(CopilotRun).filter(CopilotRun.run_id == "e2e-run-stale").statement,
        )
        # Use raw SQL for precise control
        from sqlalchemy import text
        db.execute(text("UPDATE copilot_runs SET updated_at = :ts WHERE run_id = :rid"), {"ts": old_time, "rid": "e2e-run-stale"})
        db.commit()
        db.expire_all()

        resp = client.get(f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs/e2e-run-stale")
        assert resp.status_code == 200
        assert resp.json()["status"] == "interrupted"

    def test_stale_queued_run_detected_on_poll(self, client, db, novel):
        """Stale queued run is marked interrupted when polled."""
        from datetime import datetime, timedelta, timezone
        from app.models import CopilotRun, CopilotSession as CS

        resp = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={
            "mode": "research", "scope": "whole_book",
        })
        session_id = resp.json()["session_id"]
        cs = db.query(CS).filter(CS.session_id == session_id).first()

        run = CopilotRun(
            run_id="e2e-run-queued-stale",
            copilot_session_id=cs.id,
            novel_id=novel.id,
            user_id=1,
            status="queued",
            prompt="test",
            lease_expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=60),
        )
        db.add(run)
        db.commit()

        resp = client.get(f"/api/novels/{novel.id}/world/copilot/sessions/{session_id}/runs/e2e-run-queued-stale")
        assert resp.status_code == 200
        assert resp.json()["status"] == "interrupted"

    def test_parallel_sessions_coexist(self, client, db, novel, entities):
        """Multiple sessions can coexist with bounded active runs."""
        # Open two sessions with different scopes
        r1 = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={
            "mode": "research", "scope": "whole_book",
        })
        r2 = client.post(f"/api/novels/{novel.id}/world/copilot/sessions", json={
            "mode": "current_entity", "scope": "current_entity",
            "context": {"entity_id": entities[0].id},
        })
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["session_id"] != r2.json()["session_id"]


# ===========================================================================
# Evidence flow tests
# ===========================================================================


class TestEvidenceFlow:
    def test_workspace_evidence_merges_to_evidence_items(self, db, novel, entities, chapters):
        """Evidence packs discovered by tools flow into the serializable evidence list."""
        from app.core.copilot import EvidenceItem, EvidencePack, Workspace, _evidence_from_workspace

        base = [EvidenceItem(
            evidence_id="ev_base", source_type="chapter_excerpt",
            source_ref={"chapter_id": 1}, title="base", excerpt="text", why_relevant="test",
        )]
        workspace = Workspace()
        workspace.evidence_packs["pk_ent_1_abc12345"] = EvidencePack(
            pack_id="pk_ent_1_abc12345",
            source_refs=[{"type": "entity", "id": entities[0].id}],
            preview_excerpt="张三是主角",
            anchor_terms=["张三"],
            support_count=2,
            related_targets=[],
        )
        merged = _evidence_from_workspace(workspace, base)
        assert len(merged) == 2
        pack_ev = [e for e in merged if e.evidence_id.startswith("pack_")]
        assert len(pack_ev) == 1
        assert pack_ev[0].source_type == "world_entity"
        assert pack_ev[0].pack_id == "pk_ent_1_abc12345"
        assert pack_ev[0].anchor_terms == ["张三"]
        assert pack_ev[0].support_count == 2
        assert pack_ev[0].preview_excerpt == "张三是主角"
        assert pack_ev[0].expanded is False

    def test_workspace_evidence_localizes_reason_to_english(self, db, novel, entities, chapters):
        from app.core.copilot import EvidenceItem, EvidencePack, Workspace, _evidence_from_workspace

        base = [EvidenceItem(
            evidence_id="ev_base", source_type="chapter_excerpt",
            source_ref={"chapter_id": 1}, title="base", excerpt="text", why_relevant="test",
        )]
        workspace = Workspace()
        workspace.evidence_packs["pk_ent_1_abc12345"] = EvidencePack(
            pack_id="pk_ent_1_abc12345",
            source_refs=[{"type": "entity", "id": entities[0].id}],
            preview_excerpt="Zhang San is the protagonist",
            anchor_terms=["Zhang San"],
            support_count=2,
            related_targets=[],
        )

        merged = _evidence_from_workspace(workspace, base, interaction_locale="en")

        pack_ev = [e for e in merged if e.evidence_id.startswith("pack_")]
        assert len(pack_ev) == 1
        assert pack_ev[0].why_relevant == "Compiled from 2 related clues"


# ===========================================================================
# Workspace resume tests
# ===========================================================================


class TestWorkspaceResume:
    """Verify that an interrupted run's workspace is inherited and resumed,
    not restarted from scratch."""

    def test_interrupted_run_workspace_not_inherited_by_default_new_run(self, db, novel, entities, chapters):
        """Fresh runs must not silently inherit interrupted workspace."""
        from app.core.copilot import open_or_reuse_session, create_run, EvidencePack, Workspace

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")

        # Create first run, simulate it getting interrupted with workspace
        run1 = create_run(db, session, 1, "分析全书")
        ws = Workspace()
        ws.evidence_packs["pk_test"] = EvidencePack(
            pack_id="pk_test", source_refs=[{"type": "entity", "id": 1}],
            preview_excerpt="张三是主角", anchor_terms=["张三"],
            support_count=2, related_targets=[],
        )
        ws.round_count = 3
        ws.tool_call_count = 3
        ws.messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "分析全书"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "find", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "results"},
        ]
        run1.status = "interrupted"
        run1.workspace_json = ws.to_dict()
        db.commit()

        # Fresh follow-up should start clean unless caller explicitly resumes run1.
        run2 = create_run(db, session, 1, "继续分析")
        assert run2.workspace_json is None

    def test_explicit_resume_inherits_interrupted_workspace(self, db, novel, entities, chapters):
        """Explicit resume requests may inherit interrupted workspace."""
        from app.core.copilot import open_or_reuse_session, create_run, EvidencePack, Workspace

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")

        run1 = create_run(db, session, 1, "分析全书")
        ws = Workspace()
        ws.evidence_packs["pk_test"] = EvidencePack(
            pack_id="pk_test", source_refs=[{"type": "entity", "id": 1}],
            preview_excerpt="张三是主角", anchor_terms=["张三"],
            support_count=2, related_targets=[],
        )
        ws.round_count = 3
        ws.tool_call_count = 3
        ws.messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "分析全书"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "find", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "results"},
        ]
        run1.status = "interrupted"
        run1.workspace_json = ws.to_dict()
        db.commit()

        run2 = create_run(db, session, 1, "分析全书", resume_run_id=run1.run_id)
        assert run2.workspace_json is not None
        inherited = run2.workspace_json
        assert "pk_test" in inherited["evidence_packs"]
        assert inherited["round_count"] == 3
        assert len(inherited["messages"]) == 4

    def test_explicit_resume_requires_matching_prompt(self, db, novel, entities, chapters):
        from app.core.copilot import CopilotError, open_or_reuse_session, create_run, Workspace

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")

        run1 = create_run(db, session, 1, "分析全书")
        run1.status = "interrupted"
        run1.workspace_json = Workspace(messages=[{"role": "user", "content": "分析全书"}]).to_dict()
        db.commit()

        with pytest.raises(CopilotError) as exc_info:
            create_run(db, session, 1, "继续分析", resume_run_id=run1.run_id)
        assert exc_info.value.code == "resume_prompt_mismatch"

    def test_completed_run_workspace_not_inherited(self, db, novel, entities, chapters):
        """Only interrupted runs donate their workspace, not completed ones."""
        from app.core.copilot import open_or_reuse_session, create_run, Workspace

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")

        run1 = create_run(db, session, 1, "分析全书")
        run1.status = "completed"
        run1.workspace_json = Workspace().to_dict()
        db.commit()

        run2 = create_run(db, session, 1, "新问题")
        assert run2.workspace_json is None

    @pytest.mark.asyncio
    async def test_completed_follow_up_run_uses_prior_conversation_and_workspace_seed(self, db, novel, entities, chapters, monkeypatch):
        import app.core.copilot as copilot_mod

        from app.core.copilot import EvidencePack, Workspace, create_run, execute_copilot_run, open_or_reuse_session

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")

        run1 = create_run(db, session, 1, "先总结张三")
        ws = Workspace()
        ws.evidence_packs["pk_prev"] = EvidencePack(
            pack_id="pk_prev",
            source_refs=[{"type": "entity", "id": entities[0].id}],
            preview_excerpt="张三是主角",
            anchor_terms=["张三"],
            support_count=2,
            related_targets=[],
        )
        ws.opened_pack_ids = ["pk_prev"]
        run1.status = "completed"
        run1.answer = "张三目前是主角，和宗门联系密切。"
        run1.workspace_json = ws.to_dict()
        db.commit()

        run2 = create_run(db, session, 1, "继续分析宗门线索")
        captured: dict[str, object] = {}

        async def mock_tool_loop(
            db_factory, novel_id, session_data, prompt, llm_config, user_id, snapshot, scenario, evidence,
            turn_intent, run_id="", worker_id="", inherited_workspace=None, prior_messages=None, workspace_seed=None,
        ):
            captured["inherited_workspace"] = inherited_workspace
            captured["prior_messages"] = prior_messages
            captured["workspace_seed"] = workspace_seed
            return {"answer": "follow-up", "suggestions": []}, evidence, Workspace()

        monkeypatch.setattr(copilot_mod, "_run_tool_loop", mock_tool_loop)
        monkeypatch.setattr(copilot_mod, "gather_evidence", lambda *_args, **_kwargs: [])
        monkeypatch.setattr(copilot_mod, "compile_suggestions", lambda *_args, **_kwargs: [])
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        await execute_copilot_run(run2.run_id, novel.id, 1, None)

        assert captured["inherited_workspace"] is None
        assert captured["prior_messages"] == [
            {"role": "user", "content": "先总结张三"},
            {"role": "assistant", "content": "张三目前是主角，和宗门联系密切。"},
        ]
        workspace_seed = captured["workspace_seed"]
        assert isinstance(workspace_seed, dict)
        assert workspace_seed["evidence_packs"]["pk_prev"]["pack_id"] == "pk_prev"
        assert workspace_seed["opened_pack_ids"] == ["pk_prev"]
        assert workspace_seed["round_count"] == 0
        assert workspace_seed["tool_call_count"] == 0
        assert workspace_seed["pending_tool_calls"] == []

        db.close = original_close

    @pytest.mark.asyncio
    async def test_interrupted_follow_up_run_uses_new_prompt_instead_of_resuming(self, db, novel, entities, chapters, monkeypatch):
        import app.core.copilot as copilot_mod

        from app.core.copilot import EvidencePack, Workspace, create_run, execute_copilot_run, open_or_reuse_session

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")

        run1 = create_run(db, session, 1, "旧问题")
        ws = Workspace()
        ws.evidence_packs["pk_prev"] = EvidencePack(
            pack_id="pk_prev",
            source_refs=[{"type": "entity", "id": entities[0].id}],
            preview_excerpt="张三是主角",
            anchor_terms=["张三"],
            support_count=2,
            related_targets=[],
        )
        ws.messages = [
            {"role": "system", "content": "previous system prompt"},
            {"role": "user", "content": "旧问题"},
        ]
        run1.status = "interrupted"
        run1.workspace_json = ws.to_dict()
        db.commit()

        run2 = create_run(db, session, 1, "新问题")
        captured: dict[str, object] = {}

        async def mock_tool_loop(
            db_factory, novel_id, session_data, prompt, llm_config, user_id, snapshot, scenario, evidence,
            turn_intent, run_id="", worker_id="", inherited_workspace=None, prior_messages=None, workspace_seed=None,
        ):
            captured["prompt"] = prompt
            captured["inherited_workspace"] = inherited_workspace
            captured["prior_messages"] = prior_messages
            captured["workspace_seed"] = workspace_seed
            return {"answer": "fresh follow-up", "suggestions": []}, evidence, Workspace()

        monkeypatch.setattr(copilot_mod, "_run_tool_loop", mock_tool_loop)
        monkeypatch.setattr(copilot_mod, "gather_evidence", lambda *_args, **_kwargs: [])
        monkeypatch.setattr(copilot_mod, "compile_suggestions", lambda *_args, **_kwargs: [])
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        await execute_copilot_run(run2.run_id, novel.id, 1, None)

        assert captured["prompt"] == "新问题"
        assert captured["inherited_workspace"] is None
        assert captured["prior_messages"] == []
        assert captured["workspace_seed"] is None

        db.close = original_close


class TestLeaseRecovery:
    @pytest.mark.asyncio
    async def test_lease_loss_during_execution_preserves_interrupted_state(self, db, novel, entities, chapters, monkeypatch):
        from app.core.copilot.messages import CopilotTextKey, get_copilot_text
        from app.core.copilot import (
            RunLeaseLostError,
            _interrupt_run,
            _utcnow_naive,
            create_run,
            execute_copilot_run,
            open_or_reuse_session,
        )

        session, _ = open_or_reuse_session(db, novel.id, 1, "research", "whole_book", None, "zh", "")
        run = create_run(db, session, 1, "分析全书")
        interrupted_message = get_copilot_text(CopilotTextKey.RUN_INTERRUPTED, locale="zh")

        async def mock_tool_loop(
            db_factory, novel_id, session_data, prompt, llm_config, user_id, snapshot, scenario, evidence,
            turn_intent, run_id="", worker_id="", inherited_workspace=None, **kwargs,
        ):
            interrupted_run = db.query(CopilotRun).filter(CopilotRun.run_id == run_id).first()
            _interrupt_run(interrupted_run, message=interrupted_message, now=_utcnow_naive())
            db.commit()
            raise RunLeaseLostError(run_id)

        monkeypatch.setattr("app.core.copilot._run_tool_loop", mock_tool_loop)
        monkeypatch.setattr("app.database.SessionLocal", lambda: db)
        original_close = db.close
        monkeypatch.setattr(db, "close", lambda: None)

        await execute_copilot_run(run.run_id, novel.id, 1, None)

        db.refresh(run)
        assert run.status == "interrupted"
        assert run.error == interrupted_message
        assert run.finished_at is not None

        db.close = original_close

    @pytest.mark.asyncio
    async def test_resumed_loop_uses_inherited_messages_and_reduced_budget(self, db, novel, entities, chapters, monkeypatch):
        """When _run_tool_loop receives inherited_workspace, it:
        1. Starts from the inherited messages (not fresh system prompt)
        2. Has reduced round budget (max_rounds - rounds_used)
        3. Preserves inherited evidence packs in workspace
        """
        from app.core.copilot import (
            _run_tool_loop, load_scope_snapshot, gather_evidence, derive_scenario,
            Workspace, EvidencePack,
        )
        from app.core.ai_client import ToolLLMResponse

        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)
        scenario = derive_scenario("research", "whole_book", None)
        session_data = {"mode": "research", "scope": "whole_book", "context_json": None, "interaction_locale": "zh"}

        # Build an inherited workspace that used 6 of 8 rounds
        prev_ws = Workspace()
        prev_ws.round_count = 6
        prev_ws.tool_call_count = 6
        prev_ws.evidence_packs["pk_prev"] = EvidencePack(
            pack_id="pk_prev", source_refs=[{"type": "entity", "id": 1}],
            preview_excerpt="已有证据", anchor_terms=["张三"],
            support_count=1, related_targets=[],
        )
        prev_ws.messages = [
            {"role": "system", "content": "previous system prompt"},
            {"role": "user", "content": "original question"},
        ]

        received_messages = []

        async def mock_generate(self_client, **kwargs):
            received_messages.append(kwargs.get("messages", []))
            # Return final answer immediately
            return ToolLLMResponse(
                content='{"answer": "resumed answer", "suggestions": []}',
                tool_calls=[], finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate)
        monkeypatch.setattr("app.core.copilot.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.copilot.release_llm_slot", lambda: None)

        parsed, final_ev, workspace = await _run_tool_loop(
            lambda: db, novel.id, session_data, "继续", None, 1,
            snapshot, scenario, evidence, "task_query",
            inherited_workspace=prev_ws.to_dict(),
        )

        # 1. Answer came through
        assert parsed["answer"] == "resumed answer"

        # 2. LLM received the inherited messages (not fresh system prompt)
        assert len(received_messages) == 1
        msgs = received_messages[0]
        assert msgs[0]["content"] == "previous system prompt"  # inherited, not rebuilt
        assert msgs[1]["content"] == "original question"

        # 3. Inherited evidence packs preserved
        assert "pk_prev" in workspace.evidence_packs

        # 4. Round count continues from inherited
        assert workspace.round_count >= 7  # was 6, now at least 7

    @pytest.mark.asyncio
    async def test_resumed_loop_finishes_pending_tool_batch_before_next_llm_call(self, db, novel, entities, chapters, monkeypatch):
        from app.core.copilot import _run_tool_loop, load_scope_snapshot, gather_evidence, derive_scenario, Workspace
        from app.core.ai_client import ToolLLMResponse

        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)
        scenario = derive_scenario("research", "whole_book", None)
        session_data = {"mode": "research", "scope": "whole_book", "context_json": None, "interaction_locale": "zh"}

        prev_ws = Workspace()
        prev_ws.round_count = 2
        prev_ws.tool_call_count = 1
        prev_ws.messages = [
            {"role": "system", "content": "previous system prompt"},
            {"role": "user", "content": "original question"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "load_scope_snapshot", "arguments": "{}"}},
                    {"id": "c2", "type": "function", "function": {"name": "find", "arguments": '{"query": "张三"}'}},
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": '{"profile": "broad_exploration"}'},
        ]
        prev_ws.pending_tool_calls = [{"id": "c2", "name": "find", "arguments": '{"query": "张三"}'}]

        received_messages = []

        async def mock_generate(self_client, **kwargs):
            received_messages.append(kwargs.get("messages", []))
            return ToolLLMResponse(
                content='{"answer": "resumed answer", "suggestions": []}',
                tool_calls=[],
                finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate)
        monkeypatch.setattr("app.core.copilot.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.copilot.release_llm_slot", lambda: None)

        parsed, _, workspace = await _run_tool_loop(
            lambda: db,
            novel.id,
            session_data,
            "继续",
            None,
            1,
            snapshot,
            scenario,
            evidence,
            "task_query",
            inherited_workspace=prev_ws.to_dict(),
        )

        assert parsed["answer"] == "resumed answer"
        assert workspace.tool_call_count == 2
        assert workspace.pending_tool_calls == []
        assert len(received_messages) == 1
        resumed_messages = received_messages[0]
        assert len([m for m in resumed_messages if m["role"] == "tool"]) == 2
        assistant_with_tools = next(m for m in resumed_messages if m["role"] == "assistant" and "tool_calls" in m)
        assert len(assistant_with_tools["tool_calls"]) == 2

    @pytest.mark.asyncio
    async def test_follow_up_loop_uses_prior_conversation_but_fresh_budget(self, db, novel, entities, chapters, monkeypatch):
        from app.core.copilot import _run_tool_loop, load_scope_snapshot, gather_evidence, derive_scenario, Workspace, EvidencePack
        from app.core.ai_client import ToolLLMResponse

        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)
        scenario = derive_scenario("research", "whole_book", None)
        session_data = {"mode": "research", "scope": "whole_book", "context_json": None, "interaction_locale": "zh"}

        prior_workspace = Workspace()
        prior_workspace.round_count = 6
        prior_workspace.tool_call_count = 6
        prior_workspace.pending_tool_calls = [{"id": "stale", "name": "find", "arguments": "{}"}]
        prior_workspace.evidence_packs["pk_prev"] = EvidencePack(
            pack_id="pk_prev",
            source_refs=[{"type": "entity", "id": 1}],
            preview_excerpt="已有证据",
            anchor_terms=["张三"],
            support_count=1,
            related_targets=[],
        )
        prior_workspace.opened_pack_ids = ["pk_prev"]

        received_messages = []

        async def mock_generate(self_client, **kwargs):
            received_messages.append(kwargs.get("messages", []))
            return ToolLLMResponse(
                content='{"answer": "follow-up answer", "suggestions": []}',
                tool_calls=[],
                finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate)
        monkeypatch.setattr("app.core.copilot.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.copilot.release_llm_slot", lambda: None)

        parsed, _, workspace = await _run_tool_loop(
            lambda: db,
            novel.id,
            session_data,
            "继续分析张三和宗门的联系",
            None,
            1,
            snapshot,
            scenario,
            evidence,
            "task_query",
            prior_messages=[
                {"role": "user", "content": "先总结一下张三"},
                {"role": "assistant", "content": "张三目前是主角。"},
            ],
            workspace_seed=prior_workspace.to_dict(),
        )

        assert parsed["answer"] == "follow-up answer"
        assert len(received_messages) == 1
        msgs = received_messages[0]
        assert msgs[0]["role"] == "system"
        assert msgs[1] == {"role": "user", "content": "先总结一下张三"}
        assert msgs[2] == {"role": "assistant", "content": "张三目前是主角。"}
        assert "继续分析张三和宗门的联系" in msgs[3]["content"]
        assert "pk_prev" in workspace.evidence_packs
        assert workspace.opened_pack_ids == ["pk_prev"]
        assert workspace.round_count >= 1
        assert workspace.tool_call_count == 0
        assert workspace.pending_tool_calls == []

    @pytest.mark.asyncio
    async def test_resumed_loop_budget_exhaustion_still_forces_wrapup(self, db, novel, entities, chapters, monkeypatch):
        """If inherited workspace already used all rounds, the loop immediately
        forces a wrap-up call (tool_choice=none)."""
        from app.core.copilot import (
            _run_tool_loop, load_scope_snapshot, gather_evidence, derive_scenario,
            Workspace,
        )
        from app.core.ai_client import ToolLLMResponse

        snapshot = load_scope_snapshot(db, novel, "research", "whole_book", None)
        evidence = gather_evidence(db, novel, snapshot, None)
        scenario = derive_scenario("research", "whole_book", None)
        session_data = {"mode": "research", "scope": "whole_book", "context_json": None, "interaction_locale": "zh"}

        # Workspace used all 8 rounds
        prev_ws = Workspace()
        prev_ws.round_count = 8
        prev_ws.messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q"},
        ]

        tool_choice_seen = []

        async def mock_generate(self_client, **kwargs):
            tool_choice_seen.append(kwargs.get("tool_choice"))
            return ToolLLMResponse(
                content='{"answer": "budget done", "suggestions": []}',
                tool_calls=[], finish_reason="stop",
            )

        monkeypatch.setattr("app.core.ai_client.AIClient.generate_with_tools", mock_generate)
        monkeypatch.setattr("app.core.copilot.acquire_llm_slot", lambda: _noop_coro())
        monkeypatch.setattr("app.core.copilot.release_llm_slot", lambda: None)

        parsed, _, _ = await _run_tool_loop(
            lambda: db, novel.id, session_data, "继续", None, 1,
            snapshot, scenario, evidence, "task_query",
            inherited_workspace=prev_ws.to_dict(),
        )

        assert parsed["answer"] == "budget done"
        # The loop had 0 remaining rounds, so it went straight to wrap-up
        assert "none" in tool_choice_seen


# ===========================================================================
# LLM response parsing tests
# ===========================================================================


class TestParseLLMResponse:
    """Verify _parse_llm_response handles real LLM output patterns."""

    def test_pure_json(self):
        from app.core.copilot import _parse_llm_response
        result = _parse_llm_response('{"answer": "hello", "suggestions": []}')
        assert result["answer"] == "hello"
        assert result["suggestions"] == []

    def test_json_in_code_block(self):
        from app.core.copilot import _parse_llm_response
        text = 'Here is my analysis:\n```json\n{"answer": "hello", "suggestions": [{"kind": "update_entity"}]}\n```\nDone.'
        result = _parse_llm_response(text)
        assert result["answer"] == "hello"
        assert len(result["suggestions"]) == 1

    def test_json_in_bare_code_block(self):
        from app.core.copilot import _parse_llm_response
        text = '```\n{"answer": "bare block", "suggestions": []}\n```'
        result = _parse_llm_response(text)
        assert result["answer"] == "bare block"

    def test_json_embedded_in_text(self):
        """LLM sometimes wraps JSON in natural language without code blocks."""
        from app.core.copilot import _parse_llm_response
        text = '根据分析结果：\n{"answer": "嵌入在文本中", "suggestions": [{"kind": "update_entity", "title": "test"}]}\n以上是建议。'
        result = _parse_llm_response(text)
        assert result["answer"] == "嵌入在文本中"
        assert len(result["suggestions"]) == 1

    def test_pure_text_fallback(self):
        """When no JSON is found, entire text becomes the answer."""
        from app.core.copilot import _parse_llm_response
        result = _parse_llm_response("Just some natural language response with no JSON.")
        assert "natural language" in result["answer"]
        assert result["suggestions"] == []

    def test_malformed_json_fallback(self):
        from app.core.copilot import _parse_llm_response
        result = _parse_llm_response('{"answer": "incomplete json')
        assert "incomplete json" in result["answer"]

    def test_mixed_markdown_with_json_block(self):
        """Real LLM pattern: markdown analysis followed by JSON block."""
        from app.core.copilot import _parse_llm_response
        text = """## 分析

孙悟空的设定需要补完。

### 建议

```json
{
  "answer": "孙悟空需要补完法宝和约束设定。",
  "cited_evidence_indices": [0, 1],
  "suggestions": [
    {
      "kind": "update_entity",
      "title": "补完法宝",
      "summary": "增加如意金箍棒属性",
      "target_resource": "entity",
      "target_id": 1,
      "delta": {"attributes": [{"key": "法宝", "surface": "如意金箍棒"}]}
    }
  ]
}
```

以上为补完建议。"""
        result = _parse_llm_response(text)
        assert "法宝" in result["answer"]
        assert len(result["suggestions"]) == 1
        assert result["suggestions"][0]["kind"] == "update_entity"


# ===========================================================================
# Helpers
# ===========================================================================


async def _noop_coro():
    """Async no-op for monkeypatching acquire_llm_slot."""
    pass
