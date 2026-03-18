"""
Tests for novel upload endpoint (multipart file import).

Focus: product flow contract — user uploads .txt → backend parses → persists Novel + Chapters.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import Chapter, Novel, User


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


def _make_app(db, router) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    return app


def _novel_txt_bytes() -> bytes:
    # Two chapters; titles must appear at line start to match parser regex.
    text = "\n".join(
        [
            "第一章 开端",
            "这里是第一章内容。",
            "",
            "第二章 继续",
            "这里是第二章内容。",
            "",
        ]
    )
    return text.encode("utf-8")


def _english_novel_txt_bytes() -> bytes:
    text = "\n".join(
        [
            "Chapter 1 Beginning",
            "Alice walked into the city.",
            "",
            "Chapter 2 Return",
            "Bob returned home.",
            "",
        ]
    )
    return text.encode("utf-8")


def _japanese_novel_txt_bytes() -> bytes:
    text = "\n".join(
        [
            "プロローグ",
            "勇者は城へ向かった。",
            "",
            "第1話 出会い",
            "アリスは町で彼を待っていた。",
            "",
        ]
    )
    return text.encode("utf-8")


def _korean_novel_txt_bytes() -> bytes:
    text = "\n".join(
        [
            "프롤로그",
            "민수는 집으로 돌아갔다.",
            "",
            "제1장 만남",
            "지현은 역 앞에서 기다리고 있었다.",
            "",
        ]
    )
    return text.encode("utf-8")


class TestUploadNovel:
    def test_selfhost_upload_persists_novel_and_chapters(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        # Isolate filesystem writes.
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.txt", _novel_txt_bytes(), "text/plain")},
                data={
                    "title": "T",
                    "author": "A",
                    "consent_acknowledged": "true",
                    "consent_version": novels_api.UPLOAD_CONSENT_VERSION,
                },
            )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total_chapters"] == 2

        novel = db.get(Novel, payload["novel_id"])
        assert novel is not None
        assert novel.title == "T"
        assert novel.author == "A"
        assert novel.language == "zh"
        assert novel.owner_id == user.id
        assert novel.window_index_status == "fresh"
        assert novel.window_index_revision == 1
        assert novel.window_index_built_revision == 1
        assert novel.window_index is not None
        assert novel.window_index_error is None

        # File path is persisted and should point into the isolated upload dir.
        assert novel.file_path
        assert Path(novel.file_path).exists()
        assert str(upload_dir) in novel.file_path

        chapters = (
            db.query(Chapter)
            .filter(Chapter.novel_id == novel.id)
            .order_by(Chapter.chapter_number.asc())
            .all()
        )
        assert [ch.chapter_number for ch in chapters] == [1, 2]
        assert chapters[0].title.startswith("第一章")
        assert "第一章内容" in chapters[0].content

    def test_upload_normalizes_explicit_language(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.txt", _novel_txt_bytes(), "text/plain")},
                data={
                    "title": "T",
                    "author": "A",
                    "language": "EN_US",
                    "consent_acknowledged": "true",
                    "consent_version": novels_api.UPLOAD_CONSENT_VERSION,
                },
            )

        assert resp.status_code == 200
        novel = db.get(Novel, resp.json()["novel_id"])
        assert novel is not None
        assert novel.language == "en-us"

    def test_get_novel_exposes_window_index_lifecycle_contract(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default
        from app.core.indexing import enqueue_window_index_rebuild_job, mark_window_index_inputs_changed

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        novel = Novel(
            title="T",
            author="A",
            language="zh",
            file_path=str(upload_dir / "t.txt"),
            total_chapters=1,
            owner_id=user.id,
        )
        db.add(novel)
        db.commit()
        db.refresh(novel)
        db.add(Chapter(novel_id=novel.id, chapter_number=1, title="第一章", content="这里是第一章内容。"))
        db.commit()

        revision = mark_window_index_inputs_changed(novel)
        enqueue_window_index_rebuild_job(db, novel_id=novel.id, target_revision=revision)
        db.commit()
        detail_path = f"/api/novels/{novel.id}"

        queries = {"novels": []}

        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            _ = (conn, cursor, parameters, context, executemany)
            normalized = " ".join(statement.lower().split())
            if normalized.startswith("select") and " from novels " in normalized:
                queries["novels"].append(normalized)

        event.listen(engine, "before_cursor_execute", before_cursor_execute)
        try:
            with TestClient(app) as c:
                response = c.get(detail_path)
        finally:
            event.remove(engine, "before_cursor_execute", before_cursor_execute)

        assert response.status_code == 200
        payload = response.json()
        assert payload["window_index"] == {
            "status": "missing",
            "revision": 1,
            "built_revision": None,
            "error": None,
            "job": {
                "status": "queued",
                "target_revision": 1,
                "completed_revision": None,
                "error": None,
            },
        }
        assert len(queries["novels"]) == 1
        assert "window_index as novels_window_index" not in queries["novels"][0]
        assert "window_index is not null" in queries["novels"][0]

    def test_list_novels_batches_window_index_job_reads(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default
        from app.core.indexing import enqueue_window_index_rebuild_job, mark_window_index_inputs_changed

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        novels: list[Novel] = []
        for idx in range(3):
            novel = Novel(
                title=f"T{idx}",
                author="A",
                language="zh",
                file_path=str(upload_dir / f"t{idx}.txt"),
                total_chapters=1,
                owner_id=user.id,
            )
            db.add(novel)
            db.flush()
            db.add(
                Chapter(
                    novel_id=novel.id,
                    chapter_number=1,
                    title="第一章",
                    content="这里是第一章内容。",
                )
            )
            revision = mark_window_index_inputs_changed(novel)
            enqueue_window_index_rebuild_job(db, novel_id=novel.id, target_revision=revision)
            novels.append(novel)
        db.commit()

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        query_counts = {"derived_asset_jobs": 0, "novels": []}

        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            _ = (conn, cursor, parameters, context, executemany)
            normalized = " ".join(statement.lower().split())
            if "from derived_asset_jobs" in normalized:
                query_counts["derived_asset_jobs"] += 1
            if normalized.startswith("select") and " from novels " in normalized:
                query_counts["novels"].append(normalized)

        event.listen(engine, "before_cursor_execute", before_cursor_execute)
        try:
            with TestClient(app) as c:
                query_counts["derived_asset_jobs"] = 0
                query_counts["novels"].clear()
                response = c.get("/api/novels")
        finally:
            event.remove(engine, "before_cursor_execute", before_cursor_execute)

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 3
        assert query_counts["derived_asset_jobs"] == 1
        assert len(query_counts["novels"]) == 1
        assert "window_index as novels_window_index" not in query_counts["novels"][0]
        assert "window_index is not null" in query_counts["novels"][0]
        assert {item["window_index"]["job"]["status"] for item in payload} == {"queued"}

    def test_upload_auto_detects_english_language_when_omitted(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.txt", _english_novel_txt_bytes(), "text/plain")},
                data={
                    "title": "T",
                    "author": "A",
                    "consent_acknowledged": "true",
                    "consent_version": novels_api.UPLOAD_CONSENT_VERSION,
                },
            )

        assert resp.status_code == 200
        novel = db.get(Novel, resp.json()["novel_id"])
        assert novel is not None
        assert novel.language == "en"

    def test_upload_auto_detects_japanese_language_when_omitted(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.txt", _japanese_novel_txt_bytes(), "text/plain")},
                data={
                    "title": "T",
                    "author": "A",
                    "consent_acknowledged": "true",
                    "consent_version": novels_api.UPLOAD_CONSENT_VERSION,
                },
            )

        assert resp.status_code == 200
        novel = db.get(Novel, resp.json()["novel_id"])
        assert novel is not None
        assert novel.language == "ja"

    def test_upload_auto_detects_korean_language_when_omitted(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.txt", _korean_novel_txt_bytes(), "text/plain")},
                data={
                    "title": "T",
                    "author": "A",
                    "consent_acknowledged": "true",
                    "consent_version": novels_api.UPLOAD_CONSENT_VERSION,
                },
            )

        assert resp.status_code == 200
        novel = db.get(Novel, resp.json()["novel_id"])
        assert novel is not None
        assert novel.language == "ko"

    def test_upload_passes_normalized_language_to_parser(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        seen: dict[str, str | None] = {"language": None}

        def fake_parse(path: str, *, language: str | None = None):
            seen["language"] = language
            return [(1, "Chapter 1", "content")]

        monkeypatch.setattr(novels_api, "parse_novel_file", fake_parse)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.txt", b"plain body", "text/plain")},
                data={
                    "title": "T",
                    "author": "A",
                    "language": "JA_JP",
                    "consent_acknowledged": "true",
                    "consent_version": novels_api.UPLOAD_CONSENT_VERSION,
                },
            )

        assert resp.status_code == 200
        assert seen["language"] == "ja-jp"

    def test_upload_passes_detected_language_to_parser_when_language_omitted(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        seen: dict[str, str | None] = {"language": None}

        def fake_read_text(path: str):
            assert path.endswith(".txt")
            return "Chapter 1 Beginning\nAlice walked home."

        def fake_parse(path: str, *, language: str | None = None):
            seen["language"] = language
            return [(1, "Chapter 1", "content")]

        monkeypatch.setattr(novels_api, "read_novel_file_text", fake_read_text)
        monkeypatch.setattr(novels_api, "parse_novel_file", fake_parse)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.txt", b"plain body", "text/plain")},
                data={
                    "title": "T",
                    "author": "A",
                    "consent_acknowledged": "true",
                    "consent_version": novels_api.UPLOAD_CONSENT_VERSION,
                },
            )

        assert resp.status_code == 200
        assert seen["language"] == "en"

    def test_upload_rejects_non_txt(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.md", b"# hi", "text/markdown")},
                data={
                    "title": "T",
                    "author": "A",
                    "consent_acknowledged": "true",
                    "consent_version": novels_api.UPLOAD_CONSENT_VERSION,
                },
            )

        assert resp.status_code == 400

    def test_upload_rejects_too_large(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        # 30MB + 1 byte
        too_big = b"a" * (30 * 1024 * 1024 + 1)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.txt", too_big, "text/plain")},
                data={
                    "title": "T",
                    "author": "A",
                    "consent_acknowledged": "true",
                    "consent_version": novels_api.UPLOAD_CONSENT_VERSION,
                },
            )

        assert resp.status_code == 413
        # Regression: partial writes are cleaned up when the upload is rejected.
        assert list(upload_dir.iterdir()) == []

    def test_hosted_upload_requires_auth(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        import app.core.auth as auth_core

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        # Hosted mode requires an Authorization token; we don't provide one here.
        monkeypatch.setattr(auth_core, "get_settings", lambda: MagicMock(deploy_mode="hosted"))

        app = _make_app(db, novels_api.router)

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.txt", _novel_txt_bytes(), "text/plain")},
                data={
                    "title": "T",
                    "author": "A",
                    "consent_acknowledged": "true",
                    "consent_version": novels_api.UPLOAD_CONSENT_VERSION,
                },
            )

        assert resp.status_code == 401

    def test_upload_requires_consent(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.txt", _novel_txt_bytes(), "text/plain")},
                data={"title": "T", "author": "A", "consent_version": novels_api.UPLOAD_CONSENT_VERSION},
            )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "upload_consent_required"

    def test_upload_rejects_stale_consent_version(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.txt", _novel_txt_bytes(), "text/plain")},
                data={
                    "title": "T",
                    "author": "A",
                    "consent_acknowledged": "true",
                    "consent_version": "outdated-version",
                },
            )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "upload_consent_version_mismatch"
