from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core import cache as cache_module
from app.core.cache import CacheManager, invalidate_novel_language_caches
from app.core.indexing import (
    ChapterText,
    WINDOW_INDEX_REBUILD_FAILED_MESSAGE,
    WINDOW_INDEX_STATUS_FAILED,
    WINDOW_INDEX_STATUS_FRESH,
    WINDOW_INDEX_STATUS_MISSING,
    WINDOW_INDEX_STATUS_STALE,
    WindowIndexArtifacts,
    build_window_index_artifacts,
    mark_window_index_build_succeeded,
    mark_window_index_inputs_changed,
    run_window_index_rebuild_for_latest_revision,
)
from app.core.indexing.window_index import NovelIndex
from app.database import Base
from app.models import Chapter, Novel


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


@pytest.fixture(autouse=True)
def reset_cache_singleton():
    CacheManager._instance = None
    cache_module.cache_manager = CacheManager()
    yield
    CacheManager._instance = None
    cache_module.cache_manager = CacheManager()


def _build_artifacts() -> WindowIndexArtifacts:
    return WindowIndexArtifacts(
        language="en",
        tokens=["Alice", "Bob"],
        candidates={"Alice": 1},
        index=NovelIndex(),
        importance={"Alice": 1},
        cooccurrence_pairs=[],
    )


def test_mark_inputs_changed_transitions_fresh_to_stale():
    novel = Novel(title="T", author="A", file_path="/tmp/t.txt")
    mark_window_index_build_succeeded(
        novel,
        index_payload=b"index-bytes",
        revision=1,
    )

    mark_window_index_inputs_changed(novel)

    assert novel.window_index_status == WINDOW_INDEX_STATUS_STALE
    assert novel.window_index_revision == 2
    assert novel.window_index_built_revision == 1
    assert novel.window_index is None
    assert novel.window_index_error is None


def test_language_invalidation_marks_window_index_stale_and_clears_lore(db):
    novel = Novel(title="T", author="A", file_path="/tmp/t.txt")
    db.add(novel)
    db.commit()
    db.refresh(novel)
    mark_window_index_build_succeeded(
        novel,
        index_payload=b"index-bytes",
        revision=1,
    )
    db.commit()

    cache_module.cache_manager.set_lore(novel.id, MagicMock())

    invalidate_novel_language_caches(db, novel.id)

    assert cache_module.cache_manager.get_lore(novel.id) is None
    assert novel.window_index_status == WINDOW_INDEX_STATUS_STALE
    assert novel.window_index_revision == 2
    assert novel.window_index_built_revision == 1
    assert novel.window_index is None


def test_rebuild_runner_marks_fresh_from_missing_state(db):
    novel = Novel(title="T", author="A", file_path="/tmp/t.txt")
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content="Alice met Bob in the city."))
    mark_window_index_inputs_changed(novel)
    db.commit()

    run_window_index_rebuild_for_latest_revision(
        novel.id,
        session_factory=TestingSessionLocal,
    )

    db.refresh(novel)
    assert novel.window_index_status == WINDOW_INDEX_STATUS_FRESH
    assert novel.window_index_revision == 1
    assert novel.window_index_built_revision == 1
    assert novel.window_index is not None
    assert novel.window_index_error is None


def test_rebuild_runner_marks_failed_on_builder_error(db, monkeypatch):
    novel = Novel(title="T", author="A", file_path="/tmp/t.txt")
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content="Alice met Bob in the city."))
    mark_window_index_inputs_changed(novel)
    db.commit()

    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.core.indexing.lifecycle.build_window_index_artifacts", _raise)

    run_window_index_rebuild_for_latest_revision(
        novel.id,
        session_factory=TestingSessionLocal,
    )

    db.refresh(novel)
    assert novel.window_index_status == WINDOW_INDEX_STATUS_FAILED
    assert novel.window_index_revision == 1
    assert novel.window_index_built_revision is None
    assert novel.window_index is None
    assert novel.window_index_error == WINDOW_INDEX_REBUILD_FAILED_MESSAGE


def test_rebuild_runner_retries_until_latest_revision(db, monkeypatch):
    novel = Novel(title="T", author="A", file_path="/tmp/t.txt")
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content="Alice met Bob in the city."))
    mark_window_index_inputs_changed(novel)
    db.commit()

    calls = {"count": 0}

    def _build(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            update_db = TestingSessionLocal()
            try:
                current = update_db.get(Novel, novel.id)
                assert current is not None
                mark_window_index_inputs_changed(current)
                update_db.commit()
            finally:
                update_db.close()
        return _build_artifacts()

    monkeypatch.setattr("app.core.indexing.lifecycle.build_window_index_artifacts", _build)

    run_window_index_rebuild_for_latest_revision(
        novel.id,
        session_factory=TestingSessionLocal,
    )

    db.refresh(novel)
    assert calls["count"] == 2
    assert novel.window_index_status == WINDOW_INDEX_STATUS_FRESH
    assert novel.window_index_revision == 2
    assert novel.window_index_built_revision == 2
    assert novel.window_index is not None


def test_rebuild_runner_marks_missing_when_no_chapter_text(db):
    novel = Novel(title="T", author="A", file_path="/tmp/t.txt")
    db.add(novel)
    db.commit()
    db.refresh(novel)
    mark_window_index_inputs_changed(novel)
    db.commit()

    run_window_index_rebuild_for_latest_revision(
        novel.id,
        session_factory=TestingSessionLocal,
    )

    db.refresh(novel)
    assert novel.window_index_status == WINDOW_INDEX_STATUS_MISSING
    assert novel.window_index_revision == 1
    assert novel.window_index_built_revision is None
    assert novel.window_index is None


def test_rebuild_runner_uses_pure_python_matcher_path(db, monkeypatch):
    novel = Novel(title="T", author="A", file_path="/tmp/t.txt")
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content="Alice met Bob in the city."))
    mark_window_index_inputs_changed(novel)
    db.commit()

    seen: dict[str, bool | None] = {"use_automaton": None}

    def _build(*args, **kwargs):
        seen["use_automaton"] = kwargs.get("use_automaton")
        return _build_artifacts()

    monkeypatch.setattr("app.core.indexing.lifecycle.build_window_index_artifacts", _build)

    run_window_index_rebuild_for_latest_revision(
        novel.id,
        session_factory=TestingSessionLocal,
    )

    assert seen["use_automaton"] is False


def test_build_window_index_artifacts_serializes_builder_usage(monkeypatch):
    chapters = [ChapterText(chapter_id=1, text="Alice met Bob in the city.")]
    settings = SimpleNamespace(
        bootstrap_common_words_dir=".",
        bootstrap_window_size=32,
        bootstrap_window_step=16,
        bootstrap_min_window_count=1,
        bootstrap_min_window_ratio=0.0,
    )
    state_lock = threading.Lock()
    start = threading.Event()
    errors: list[Exception] = []
    active = 0
    max_active = 0

    def _tokenize_text(text: str, *, language: str | None = None):
        nonlocal active, max_active
        with state_lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with state_lock:
            active -= 1
        return language or "en", ["alice", "bob"]

    monkeypatch.setattr("app.core.indexing.rebuild.tokenize_text", _tokenize_text)
    monkeypatch.setattr(
        "app.core.indexing.rebuild.load_common_words",
        lambda language, *, common_words_dir: set(),
    )
    monkeypatch.setattr(
        "app.core.indexing.rebuild.extract_candidates",
        lambda tokens, common_words, *, language=None: {"alice": 2},
    )
    monkeypatch.setattr(
        "app.core.indexing.rebuild.build_window_index",
        lambda chapters, candidates, **kwargs: (NovelIndex(), {"alice": 2}),
    )

    def _worker():
        start.wait()
        try:
            build_window_index_artifacts(
                chapters,
                novel_language="en",
                settings=settings,
            )
        except Exception as exc:  # pragma: no cover - defensive test plumbing
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    start.set()
    for thread in threads:
        thread.join(timeout=1)

    assert errors == []
    assert all(not thread.is_alive() for thread in threads)
    assert max_active == 1
